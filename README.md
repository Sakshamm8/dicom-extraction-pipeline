# DICOM to NIfTI Automated Extraction Pipeline

## Overview
This repository contains a production-grade, object-oriented data engineering pipeline designed to automate the conversion of raw clinical DICOM slices into structured 3D NIfTI volumes (`.nii.gz`). 

In clinical and research environments, MRI data is often exported as chaotic directories containing thousands of unclassified 2D slices. This pipeline recursively parses these directories, extracts metadata headers, classifies the imaging modalities (e.g., T1c, T2 FLAIR), and reconstructs the highest-resolution 3D volumes while preserving complex spatial coordinate matrices (affine transformations).

## Architecture & Software Engineering Principles
This system was built utilizing strict Object-Oriented Programming (OOP) paradigms to ensure modularity, extensibility, and robust error handling:

* `SeriesClassifier`: Encapsulates the string-matching logic to categorize sequences based on DICOM metadata headers (e.g., distinguishing Pre-Contrast vs. Post-Contrast T1).
* `NiftiAnalyzer`: Evaluates volumetric dimensions to dynamically select the highest-resolution scan when conflicting series are present.
* `PatientProcessor`: Adheres to the Single Responsibility Principle by managing the isolated execution environment (via `dcm2niix` wrappers) for individual patients.
* `ConversionLogger`: Automates CSV audit trailing, logging successful extractions, ignored lower-resolution duplicates, and missing modalities.
* `PipelineOrchestrator`: The high-level coordinator that manages directory traversal and state execution.

## Requirements
*   Python 3.8+
*   `nibabel` (for spatial metadata analysis)
*   [dcm2niix](https://github.com/rordenlab/dcm2niix) (executable required for backend binary conversion)

## Execution
Paths to the local environment, dataset, and `dcm2niix` executable are configured as variables at the top of the script. To run the extraction pipeline, simply execute:

```bash
python dicom_pipeline.py