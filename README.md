
# Claims Agent – FNOL Processing System

This project is a **rule-based First Notice of Loss (FNOL) claims processing agent** for automobile insurance.  
It extracts structured claim information from ACORD-style PDF or TXT documents and determines the appropriate claim routing.

## Features

- Parses **PDF and TXT** FNOL documents
- Extracts key insurance claim fields:
  - Policy Number
  - Policyholder Name
  - Incident Date & Time
  - Incident Location
  - Incident Description
  - Claim Type
  - Estimated Damage
  - Attachments
- Validates extracted fields to remove noise and placeholders
- Applies routing rules to recommend:
  - Fast-track
  - Standard Processing
  - Specialist Queue
  - Manual Review
  - Investigation Flag
- Outputs clean **JSON** for downstream systems

  ## Images
  ### Not filled form
  <img width="873" height="338" alt="image" src="https://github.com/user-attachments/assets/503578ac-639b-40a8-877e-4bb2b4d07a88" />

  ### filled pdf
  <img width="1293" height="263" alt="image" src="https://github.com/user-attachments/assets/3be29552-19e7-4396-9075-ed311bb1e340" />

  ### text file
  <img width="975" height="254" alt="image" src="https://github.com/user-attachments/assets/fef9ecda-c08d-4fea-accb-8dd70e6faa8c" />

## Project Structure

```
.
├── claims_agent.py
├── filled-fnol.txt
├── filled.pdf
├── ACORD-Automobile-Loss-Notice-12.05.16.pdf
├── Assessment_Brief_Synapx.pdf
├── __pycache__/
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.8+
- Dependencies:
  ```bash
  pip3 install -r requirements.txt
```

## Usage

Run the agent with a PDF or TXT FNOL document:

```bash
python3 claims_agent.py <input_file>
```

Example:

```bash
python3 claims_agent.py ACORD-Automobile-Loss-Notice-12.05.16.pdf
```

## Output

The program prints structured JSON to stdout:

```json
{
  "extractedFields": {
    "Policy Number": "...",
    "Policyholder Name": "...",
    "Incident Date": "...",
    "Incident Time": "...",
    "Incident Location": "...",
    "Incident Description": "...",
    "Claim Type": "...",
    "Estimated Damage": "...",
    "Attachments": "..."
  },
  "missingFields": [],
  "recommendedRoute": "Fast-track",
  "reasoning": "Estimated damage below 25000."
}
```

## Claim Routing Logic

* **Manual Review**

  * Missing mandatory fields
* **Investigation Flag**

  * Fraud-related keywords detected
* **Specialist Queue**

  * Injury-related claims
* **Fast-track**

  * Estimated damage < 25,000
* **Standard Processing**

  * All checks passed

## Notes

* Designed as a deterministic, explainable alternative to ML-based claim triage
* Optimized for ACORD Automobile Loss Notice formats
* Intended for assessment, demo, or backend workflow integration

## Author

Ankush
