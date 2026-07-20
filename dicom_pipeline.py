#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import nibabel as nib
except ImportError:
    sys.exit("Missing dependency: run `pip install nibabel --break-system-packages`")

# Hardcoded Paths for Testing
INPUT_DIR = r"C:\Users\malhotsm\UC_GBM\DICOM Files\02008471"
OUTPUT_DIR = r"C:\Users\malhotsm\Dicom_extraction_pipeline\Test_Output"
DCM2NIIX_PATH = r"C:\Users\malhotsm\Downloads\dcm2niix_win\dcm2niix.exe"

class SeriesClassifier:
    """Handles the classification of MRI series based on DICOM metadata."""
    
    EXCLUDE_KEYWORDS = [
        "LOCALIZER", "SCOUT", "CALIBRATION", "SCREEN SAVE", "SCREENSAVE",
        "DWI", "DIFFUSION", "ADC", "TRACEW", "SWI", "SWAN", "PERFUSION",
        "DSC", "DCE", "MPR", "REFORMAT", "SUBTRACTION", "PHASE",
        "ASL", "MIP", "REPORT", "DOSE", "SECONDARY",
    ]
    FLAIR_INCLUDE = ["FLAIR", "FALIR"]
    T2_INCLUDE = ["T2"]
    T2_EXCLUDE = FLAIR_INCLUDE  
    T1_INCLUDE = ["T1", "MPRAGE", "BRAVO", "SPGR"]
    CONTRAST_KEYWORDS = [
        "+C", "C+", "POST", "POST-CONTRAST", "POSTCONTRAST", "GAD", "GADOLINIUM",
        "CE", "CONTRAST", "W/C", "WC", "ENHANCED", "PC"
    ]
    NO_CONTRAST_KEYWORDS = [
        "PRE-CONTRAST", "PRECONTRAST", "W/O", "NON-CONTRAST", "NONCONTRAST"
    ]

    @classmethod
    def classify(cls, description: str, protocol: str, sequence: str) -> str:
        text = f"{description} {protocol} {sequence}".upper()
        
        if any(kw in text for kw in cls.EXCLUDE_KEYWORDS):
            return "unclassified"
        if any(kw in text for kw in cls.FLAIR_INCLUDE):
            return "t2f"
        if any(kw in text for kw in cls.T2_INCLUDE) and not any(kw in text for kw in cls.T2_EXCLUDE):
            return "t2w"
        
        if any(kw in text for kw in cls.T1_INCLUDE):
            has_contrast = any(kw in text for kw in cls.CONTRAST_KEYWORDS)
            has_no_contrast = any(kw in text for kw in cls.NO_CONTRAST_KEYWORDS)
            if has_contrast and not has_no_contrast:
                return "t1c"
            if has_no_contrast and not has_contrast:
                return "t1n"
                
        return "unclassified"


class NiftiAnalyzer:
    """Handles operations related to NIfTI files."""
    
    @staticmethod
    def get_slice_count(nifti_path: Path) -> int:
        try:
            img = nib.load(nifti_path)
            if len(img.shape) >= 3:
                return img.shape[2]
            return img.shape[0] 
        except Exception:
            return 0


class ConversionLogger:
    """Manages the CSV logging for the conversion pipeline."""
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.rows: List[List[Any]] = []

    def log_entry(self, patient_id: str, date: str, desc: str, category: str, slices: int, status: str, filepath: str):
        self.rows.append([patient_id, date, desc, category, slices, status, filepath])

    def save(self):
        with open(self.log_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["PatientID", "StudyDate", "SeriesDescription", "Category", "NumSlices", "Status", "OutputFile"])
            writer.writerows(self.rows)


class PatientProcessor:
    """Handles the DICOM to NIfTI conversion and sorting for a single patient."""
    
    def __init__(self, dcm2niix_path: str, categories: List[str], logger: ConversionLogger):
        self.dcm2niix = dcm2niix_path
        self.categories = categories
        self.logger = logger

    def process(self, in_dir: Path, out_dir: Path):
        patient_id = in_dir.name
        print(f"\nProcessing Patient: {patient_id}")
        
        patient_out_dir = out_dir / patient_id
        temp_dir = out_dir / f"temp_{patient_id}"
        patient_out_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Execute dcm2niix
        cmd = [
            str(self.dcm2niix),
            "-z", "y", "-b", "y",
            "-f", "%p_%t_%s", 
            "-o", str(temp_dir),
            str(in_dir)
        ]
        subprocess.run(cmd, capture_output=True, text=True)

        self._evaluate_and_move(patient_id, temp_dir, patient_out_dir)
        shutil.rmtree(temp_dir)

    def _evaluate_and_move(self, patient_id: str, temp_dir: Path, patient_out_dir: Path):
        classified_files = defaultdict(list)
        
        for json_file in temp_dir.glob("*.json"):
            nifti_file = json_file.with_suffix(".nii.gz")
            if not nifti_file.exists():
                continue
                
            with open(json_file, 'r') as f:
                meta = json.load(f)
                
            desc = meta.get("SeriesDescription", "")
            protocol = meta.get("ProtocolName", "")
            seq = meta.get("SequenceName", "")
            
            category = SeriesClassifier.classify(desc, protocol, seq)
            
            if category in self.categories:
                slices = NiftiAnalyzer.get_slice_count(nifti_file)
                study_date = meta.get("StudyDate", "UnknownDate")
                classified_files[category].append({
                    "nifti": nifti_file, "slices": slices, "date": study_date, "desc": desc
                })

        for category in self.categories:
            candidates = classified_files.get(category, [])
            if not candidates:
                print(f"    [{category}] No scans found.")
                self.logger.log_entry(patient_id, "Unknown", "N/A", category, 0, "NOT_FOUND", "")
                continue
                
            # Sort by slice count to get the highest resolution scan
            candidates.sort(key=lambda x: x["slices"], reverse=True)
            best_scan = candidates[0]
            
            final_filename = f"{patient_id}_{best_scan['date']}_{category}.nii.gz"
            final_path = patient_out_dir / final_filename
            
            shutil.move(str(best_scan["nifti"]), str(final_path))
            print(f"    [{category}] SAVED: {best_scan['desc']} ({best_scan['slices']} slices)")
            self.logger.log_entry(patient_id, best_scan['date'], best_scan['desc'], category, best_scan['slices'], "SAVED", str(final_path))
            
            if len(candidates) > 1:
                print(f"        -> Ignored {len(candidates)-1} smaller conflicting scans.")
                for ignored in candidates[1:]:
                    self.logger.log_entry(patient_id, ignored['date'], ignored['desc'], category, ignored['slices'], "IGNORED_SMALLER_SLICE_COUNT", "")


class PipelineOrchestrator:
    """Main orchestrator for the DICOM extraction pipeline."""
    
    def __init__(self, in_root: str, out_root: str, dcm2niix_path: str, categories: List[str]):
        self.in_root = Path(in_root)
        self.out_root = Path(out_root)
        self.out_root.mkdir(parents=True, exist_ok=True)
        self.dcm2niix_path = dcm2niix_path
        self.categories = categories
        self.logger = ConversionLogger(self.out_root / "review_log.csv")

    def run(self):
        processor = PatientProcessor(self.dcm2niix_path, self.categories, self.logger)
        
        # Check if the input is a direct patient folder or a root directory
        subdirs = [p for p in self.in_root.iterdir() if p.is_dir()]
        
        if not subdirs:
            # It's likely a single patient folder (e.g., .../02008471)
            processor.process(self.in_root, self.out_root)
        else:
            # It's a root directory containing multiple patient folders
            for in_dir in sorted(subdirs):
                processor.process(in_dir, self.out_root)
            
        self.logger.save()
        print("\n" + "="*40)
        print(f"Pipeline Complete. Log file generated at: {self.logger.log_path}")
        print("="*40)


if __name__ == "__main__":
    # Bypassing argparse to use hardcoded variables
    print("Starting pipeline using hardcoded test variables...")
    
    pipeline = PipelineOrchestrator(
        in_root=INPUT_DIR, 
        out_root=OUTPUT_DIR, 
        dcm2niix_path=DCM2NIIX_PATH, 
        categories=["t1c", "t2f"]  
    )
    
    pipeline.run()