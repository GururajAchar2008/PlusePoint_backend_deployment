# PulsePoint Backend API

Backend service for PulsePoint healthcare workflows and PharmaGuard pharmacogenomic analysis.

## Backend Name
`PulsePoint Backend API`

## Deployed Link
- Live Backend URL: https://plusepoint-backend-deployment.onrender.com
- Main Repository: `https://github.com/GururajAchar2008/PlusePoint.git`

Replace the placeholder with your deployed backend API URL.

## Core Responsibilities
- Serve hospital reference data
- Handle patient profile operations
- Process precision medicine VCF uploads
- Return structured pharmacogenomic reports

## Tech Stack
- Python 3
- Flask
- Flask-MySQLdb
- MySQL / Aiven MySQL

## Main File
- `app.py` (all API routes + DB init + business logic)
- `requirements.txt` (Python dependencies)

## Key Backend Features
1. Database bootstrapping on startup
- Creates tables if not present
- Seeds departments, symptoms, and testimonials

2. Precision Medicine (PharmaGuard)
- Endpoint: `POST /api/pharmacogenomics/analyze`
- Accepts VCF file + drugs
- Parses variants for supported genes
- Predicts risk labels with confidence/severity
- Generates explainable recommendation payload
- Stores report in `pharmacogenomic_reports`

## Supported Pharmacogenes
- CYP2D6
- CYP2C19
- CYP2C9
- SLCO1B1
- TPMT
- DPYD

## Supported Drugs
- CODEINE
- WARFARIN
- CLOPIDOGREL
- SIMVASTATIN
- AZATHIOPRINE
- FLUOROURACIL

## Database Tables (Created Automatically)
- `departments`
- `symptoms`
- `testimonials`
- `patients`
- `pharmacogenomic_reports`

## Environment Variables
Use `Backend/.env.example` as the template.

```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=Helthteck

# Optional TLS for managed MySQL
MYSQL_SSL_MODE=REQUIRED
MYSQL_SSL_CA=/absolute/path/to/ca.pem

# Optional external LLM
PHARMAGUARD_USE_LLM=false
OPENAI_API_KEY=
PHARMAGUARD_LLM_MODEL=gpt-4o-mini
OPENAI_API_URL=https://api.openai.com/v1/chat/completions
```

## Run Locally
```bash
cd Backend
pip install -r requirements.txt
python3 app.py
```
Default URL: `http://localhost:5000`

## API Endpoints
### Health
- `GET /`

### Reference Data
- `GET /api/reference-data`

### Patients
- `GET /api/patients/latest`
- `POST /api/patients`

### Precision Medicine
- `GET /api/pharmacogenomics/meta`
- `POST /api/pharmacogenomics/analyze`

## Precision Medicine Request Example
`multipart/form-data`:
- `vcf_file`: `.vcf` file (max 5 MB)
- `drugs`: `CODEINE, WARFARIN`
- `patient_id` (optional)

## Precision Medicine Response
Returns:
- `patient_id`
- `reports[]` (one report per drug)
- `quality_summary`
- `report` shortcut when single drug is requested

Each report contains:
- `risk_assessment`
- `pharmacogenomic_profile`
- `clinical_recommendation`
- `llm_generated_explanation`
- `quality_metrics`

## Test Files
- `sample_vcfs/patient_demo_001.vcf`
- `sample_vcfs/patient_demo_002.vcf`

## Deployment
### Recommended
- Backend host: Render/Railway
- DB: Aiven MySQL

### Checklist
1. Set all DB env vars.
2. Set SSL vars for managed DB.
3. Deploy service and verify `GET /`.
4. Verify precision endpoint with sample VCF.
