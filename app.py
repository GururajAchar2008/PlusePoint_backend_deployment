import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone

import MySQLdb.cursors
from flask import Flask, jsonify, request
from flask_mysqldb import MySQL
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

app.config["MYSQL_HOST"] = os.getenv("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.getenv("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.getenv("MYSQL_PASSWORD", "Gururaj@1801")
app.config["MYSQL_DB"] = os.getenv("MYSQL_DB", "Helthteck")
app.config["MYSQL_PORT"] = int(os.getenv("MYSQL_PORT", "3306"))
app.config["MAX_CONTENT_LENGTH"] = 7 * 1024 * 1024

mysql_custom_options = {}
mysql_ssl_ca = os.getenv("MYSQL_SSL_CA", "").strip()
mysql_ssl_mode = os.getenv("MYSQL_SSL_MODE", "").strip()

if mysql_ssl_ca:
    mysql_custom_options["ssl"] = {"ca": mysql_ssl_ca}

if mysql_ssl_mode:
    mysql_custom_options["ssl_mode"] = mysql_ssl_mode

if mysql_custom_options:
    app.config["MYSQL_CUSTOM_OPTIONS"] = mysql_custom_options

mysql = MySQL(app)
DB_INITIALIZED = False

DEPARTMENTS_SEED = [
    ("gen-med", "General Medicine", "stethoscope", 4, 15),
    ("cardio", "Cardiology", "heart-pulse", 2, 45),
    ("ortho", "Orthopedics", "bone", 3, 30),
    ("dental", "Dentistry", "smile", 2, 20),
    ("derma", "Dermatology", "sun", 1, 60),
    ("gastro", "Gastroenterology", "activity", 2, 25),
]

SYMPTOMS_SEED = [
    ("High Fever (>102 F)", "gen-med", "Emergency"),
    ("Mild Fever", "gen-med", "Normal"),
    ("Severe Tooth Pain", "dental", "Normal"),
    ("Bleeding Gums", "dental", "Normal"),
    ("Chest Pain", "cardio", "Emergency"),
    ("Shortness of Breath", "cardio", "Emergency"),
    ("Skin Rash", "derma", "Normal"),
    ("Acne / Pimples", "derma", "Normal"),
    ("Bone Fracture", "ortho", "Emergency"),
    ("Joint Pain", "ortho", "Normal"),
    ("Blurred Vision", "gen-med", "Normal"),
    ("Sudden Vision Loss", "gen-med", "Emergency"),
    ("Stomach Ache", "gastro", "Normal"),
]

DOCTORS_SEED = [
    (
        "Dr. Sarah Johnson",
        "Cardiologist",
        "12 Years Experience",
        "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&q=80&w=400",
        4.9,
    ),
    (
        "Dr. James Wilson",
        "Neurologist",
        "15 Years Experience",
        "https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=400",
        4.8,
    ),
    (
        "Dr. Emily Chen",
        "Pediatrician",
        "8 Years Experience",
        "https://images.unsplash.com/photo-1594824476967-48c8b964273f?auto=format&fit=crop&q=80&w=400",
        4.9,
    ),
    (
        "Dr. Michael Brown",
        "Orthopedic Surgeon",
        "20 Years Experience",
        "https://images.unsplash.com/photo-1622253692010-333f2da6031d?auto=format&fit=crop&q=80&w=400",
        4.7,
    ),
]

VERIFIED_DOCTERS_SEED = [
    ("dr.sarah", "Dr. Sarah Johnson", "cardio", "doctor@123"),
    ("dr.james", "Dr. James Wilson", "gen-med", "doctor@123"),
    ("dr.emily", "Dr. Emily Chen", "dental", "doctor@123"),
    ("dr.michael", "Dr. Michael Brown", "ortho", "doctor@123"),
    ("dr.priya", "Dr. Priya Raman", "derma", "doctor@123"),
]

TESTIMONIALS_SEED = [
    (
        "Robert Fox",
        "The smart queue system saved me hours of waiting. Highly recommended!",
        5,
    ),
    (
        "Jane Cooper",
        "Very professional doctors and the digital token system is a game changer.",
        5,
    ),
    ("Esther Howard", "Emergency guidance helped us when we were in panic. Great app.", 4),
]

MAX_VCF_FILE_SIZE_BYTES = 5 * 1024 * 1024

SUPPORTED_PHARMACOGENES = {
    "CYP2D6",
    "CYP2C19",
    "CYP2C9",
    "SLCO1B1",
    "TPMT",
    "DPYD",
}

SUPPORTED_PHARMACOGENOMIC_DRUGS = (
    "CODEINE",
    "WARFARIN",
    "CLOPIDOGREL",
    "SIMVASTATIN",
    "AZATHIOPRINE",
    "FLUOROURACIL",
)

DRUG_RULES = {
    "CODEINE": {
        "primary_gene": "CYP2D6",
        "cpic_reference": "CPIC Guideline: CYP2D6 and Opioids",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Ineffective",
                "severity": "high",
                "recommendation": "Avoid codeine; choose an analgesic not dependent on CYP2D6 activation.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "moderate",
                "recommendation": "Monitor response closely and consider non-CYP2D6 alternatives if pain control is poor.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "none",
                "recommendation": "Use standard codeine dosing with routine monitoring.",
            },
            "RM": {
                "risk_label": "Adjust Dosage",
                "severity": "moderate",
                "recommendation": "Consider lower starting dose or alternative analgesic due to increased morphine exposure risk.",
            },
            "URM": {
                "risk_label": "Toxic",
                "severity": "critical",
                "recommendation": "Avoid codeine due to high risk of morphine toxicity and respiratory depression.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "Genotype information is insufficient for codeine guidance.",
        },
    },
    "WARFARIN": {
        "primary_gene": "CYP2C9",
        "cpic_reference": "CPIC Guideline: CYP2C9, VKORC1 and Warfarin",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Toxic",
                "severity": "high",
                "recommendation": "Use substantially reduced starting dose with close INR monitoring.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "moderate",
                "recommendation": "Initiate lower dose and titrate carefully with frequent INR checks.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Use standard dosing with routine INR monitoring.",
            },
            "RM": {
                "risk_label": "Adjust Dosage",
                "severity": "moderate",
                "recommendation": "Assess response early; dose may need upward adjustment.",
            },
            "URM": {
                "risk_label": "Adjust Dosage",
                "severity": "moderate",
                "recommendation": "Monitor INR closely and individualize dose based on response.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "Insufficient CYP2C9 information for precise dosing guidance.",
        },
    },
    "CLOPIDOGREL": {
        "primary_gene": "CYP2C19",
        "cpic_reference": "CPIC Guideline: CYP2C19 and Clopidogrel",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Ineffective",
                "severity": "high",
                "recommendation": "Avoid clopidogrel; consider an alternative antiplatelet agent.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "high",
                "recommendation": "Consider alternative antiplatelet therapy due to reduced activation.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "none",
                "recommendation": "Use standard clopidogrel dosing.",
            },
            "RM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing is typically acceptable.",
            },
            "URM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing is generally acceptable with routine monitoring.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "Unable to determine CYP2C19 phenotype-based clopidogrel response.",
        },
    },
    "SIMVASTATIN": {
        "primary_gene": "SLCO1B1",
        "cpic_reference": "CPIC Guideline: SLCO1B1 and Simvastatin",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Toxic",
                "severity": "critical",
                "recommendation": "Avoid simvastatin or use very low dose with close myopathy monitoring.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "high",
                "recommendation": "Use lower dose or consider an alternative statin.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard simvastatin dosing is acceptable.",
            },
            "RM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
            "URM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "Insufficient SLCO1B1 data for simvastatin risk classification.",
        },
    },
    "AZATHIOPRINE": {
        "primary_gene": "TPMT",
        "cpic_reference": "CPIC Guideline: TPMT and Thiopurines",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Toxic",
                "severity": "critical",
                "recommendation": "Avoid or substantially reduce thiopurine dose due to severe myelosuppression risk.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "high",
                "recommendation": "Start with reduced dose and monitor blood counts frequently.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing is acceptable with routine CBC monitoring.",
            },
            "RM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
            "URM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "TPMT status is unclear; use caution and consider phenotyping before treatment.",
        },
    },
    "FLUOROURACIL": {
        "primary_gene": "DPYD",
        "cpic_reference": "CPIC Guideline: DPYD and Fluoropyrimidines",
        "phenotype_rules": {
            "PM": {
                "risk_label": "Toxic",
                "severity": "critical",
                "recommendation": "Avoid fluorouracil or use a drastically reduced dose with specialist supervision.",
            },
            "IM": {
                "risk_label": "Adjust Dosage",
                "severity": "high",
                "recommendation": "Start with reduced dose and escalate only with close toxicity monitoring.",
            },
            "NM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing is acceptable with routine toxicity surveillance.",
            },
            "RM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
            "URM": {
                "risk_label": "Safe",
                "severity": "low",
                "recommendation": "Standard dosing with routine monitoring.",
            },
        },
        "default_rule": {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "DPYD activity cannot be inferred confidently from uploaded variants.",
        },
    },
}

GENE_ALLELE_CLASSIFICATION = {
    "CYP2D6": {
        "normal": {"*1", "*2"},
        "reduced": {"*9", "*10", "*17", "*29", "*41"},
        "no_function": {"*3", "*4", "*5", "*6"},
        "increased": {"*1XN", "*2XN"},
    },
    "CYP2C19": {
        "normal": {"*1"},
        "reduced": set(),
        "no_function": {"*2", "*3"},
        "increased": {"*17"},
    },
    "CYP2C9": {
        "normal": {"*1"},
        "reduced": {"*2", "*3", "*5", "*6", "*8", "*11"},
        "no_function": set(),
        "increased": set(),
    },
    "SLCO1B1": {
        "normal": {"*1A", "*1B", "*1"},
        "reduced": {"*5", "*15", "*17"},
        "no_function": set(),
        "increased": set(),
    },
    "TPMT": {
        "normal": {"*1"},
        "reduced": set(),
        "no_function": {"*2", "*3A", "*3B", "*3C", "*4"},
        "increased": set(),
    },
    "DPYD": {
        "normal": {"*1"},
        "reduced": {"*2A", "*13", "HAPB3", "C.2846A>T"},
        "no_function": set(),
        "increased": set(),
    },
}



@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,OPTIONS"
    return response


@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(_error):
    return jsonify({"error": "Uploaded file is too large. Maximum allowed VCF size is 5 MB."}), 413


def fetch_all(query, params=None):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query, params or ())
    rows = cursor.fetchall()
    cursor.close()
    return rows


def fetch_one(query, params=None):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query, params or ())
    row = cursor.fetchone()
    cursor.close()
    return row


def execute_query(query, params=None):
    cursor = mysql.connection.cursor()
    cursor.execute(query, params or ())
    mysql.connection.commit()
    last_row_id = cursor.lastrowid
    cursor.close()
    return last_row_id


def execute_many(query, values):
    cursor = mysql.connection.cursor()
    cursor.executemany(query, values)
    mysql.connection.commit()
    cursor.close()


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_date(value):
    if not value:
        return date.today()

    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def serialize_department(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "icon": row["icon"],
        "activeDoctors": row["active_doctors"],
        "averageWaitTime": row["average_wait_time"],
    }


def serialize_symptom(row):
    return {
        "id": row["id"],
        "symptom": row["symptom"],
        "departmentId": row["department_id"],
        "department": row["department_name"],
        "urgency": row["urgency"],
    }


def serialize_doctor(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "specialty": row["specialty"],
        "experience": row["experience"],
        "image": row["image"],
        "rating": float(row["rating"]),
    }


def serialize_testimonial(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "comment": row["comment"],
        "rating": row["rating"],
    }


def serialize_patient(row):
    if not row:
        return None

    return {
        "id": row["id"],
        "name": row["name"] or "",
        "age": row["age"] or 0,
        "gender": row["gender"] or "Male",
        "contact": row["contact"] or "",
        "bloodGroup": row["blood_group"] or "",
        "allergies": row["allergies"] or "",
        "chronicConditions": row["chronic_conditions"] or "",
    }


def serialize_appointment(row):
    appointment_date = row.get("appointment_date")
    created_at = row.get("created_at")

    return {
        "id": row["id"],
        "patientName": row["patient_name"],
        "age": row["age"],
        "symptom": row["symptom"],
        "department": row["department_id"],
        "departmentName": row.get("department_name") or row["department_id"],
        "date": appointment_date.isoformat() if appointment_date else None,
        "estimatedTime": row["estimated_time"],
        "urgency": row["urgency"],
        "tokenNumber": row["token_number"],
        "status": row["status"],
        "createdAt": created_at.isoformat() if created_at else None,
    }


def serialize_verified_docter(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["doctor_name"],
        "departmentId": row["department_id"],
        "departmentName": row.get("department_name") or row["department_id"],
    }


def normalize_gene_symbol(value):
    if not value:
        return ""
    return str(value).split(",")[0].strip().upper()


def normalize_star_allele(value):
    if not value:
        return "Unknown"

    allele = str(value).split(",")[0].strip().upper().replace(" ", "")

    if allele in {"", ".", "-", "NA", "N/A"}:
        return "Unknown"

    if allele.startswith("*"):
        return allele

    if allele.startswith("C.") or allele.startswith("HAP"):
        return allele

    if re.match(r"^\d+[A-Z]*$", allele):
        return f"*{allele}"

    return allele


def parse_info_field(info_field):
    parsed = {}
    for token in str(info_field or "").split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            parsed[key.strip().upper()] = value.strip()
        else:
            parsed[token.strip().upper()] = True
    return parsed


def split_drug_names(raw_input):
    if isinstance(raw_input, list):
        candidates = raw_input
    else:
        candidates = re.split(r"[,\n;]+", str(raw_input or ""))

    seen = set()
    normalized = []
    for item in candidates:
        drug = str(item).strip().upper()
        if not drug or drug in seen:
            continue
        seen.add(drug)
        normalized.append(drug)
    return normalized


def parse_vcf_content(vcf_content):
    lines = [line.strip() for line in str(vcf_content or "").splitlines() if line.strip()]
    has_header = False
    fileformat_detected = False
    total_variant_lines = 0
    supported_variants = []
    unique_supported_genes = set()
    annotation_hits = 0
    parse_failures = 0

    for line in lines:
        if line.upper().startswith("##FILEFORMAT=VCF"):
            fileformat_detected = True
            continue
        if line.startswith("##"):
            continue
        if line.startswith("#CHROM"):
            has_header = True
            continue
        if line.startswith("#"):
            continue

        total_variant_lines += 1
        columns = line.split("\t")
        if len(columns) < 8:
            columns = re.split(r"\s+", line)
        if len(columns) < 8:
            parse_failures += 1
            continue

        chrom, pos, variant_id, ref, alt, _qual, _filt, info = columns[:8]
        info_map = parse_info_field(info)

        gene = normalize_gene_symbol(info_map.get("GENE"))
        star = normalize_star_allele(info_map.get("STAR"))
        rsid = info_map.get("RS") or info_map.get("RSID")

        if not rsid and str(variant_id).lower().startswith("rs"):
            rsid = str(variant_id)

        genotype = ""
        if len(columns) > 9:
            format_keys = columns[8].split(":")
            sample_values = columns[9].split(":")
            if "GT" in format_keys:
                gt_index = format_keys.index("GT")
                genotype = sample_values[gt_index] if gt_index < len(sample_values) else ""

        if gene and star != "Unknown" and rsid:
            annotation_hits += 1

        if gene not in SUPPORTED_PHARMACOGENES:
            continue

        unique_supported_genes.add(gene)
        supported_variants.append(
            {
                "rsid": rsid or "Unknown",
                "gene": gene,
                "star_allele": star,
                "chromosome": chrom,
                "position": parse_int(pos, 0),
                "ref": ref,
                "alt": alt,
                "genotype": genotype,
            }
        )

    return supported_variants, {
        "vcf_parsing_success": bool(fileformat_detected and has_header and total_variant_lines > 0),
        "fileformat_detected": fileformat_detected,
        "header_detected": has_header,
        "total_variant_lines": total_variant_lines,
        "supported_variant_lines": len(supported_variants),
        "unique_supported_genes": len(unique_supported_genes),
        "gene_coverage_ratio": round(
            (len(unique_supported_genes) / len(SUPPORTED_PHARMACOGENES)) if SUPPORTED_PHARMACOGENES else 0.0,
            2,
        ),
        "variant_annotation_completeness": round(
            (annotation_hits / total_variant_lines) if total_variant_lines else 0.0,
            2,
        ),
        "parse_failure_count": parse_failures,
    }


def group_variants_by_gene(variants):
    grouped = {}
    for variant in variants:
        grouped.setdefault(variant["gene"], []).append(variant)
    return grouped


def build_diplotype(variants_for_gene):
    if not variants_for_gene:
        return "Unknown"

    for variant in variants_for_gene:
        star = normalize_star_allele(variant.get("star_allele"))
        if "/" in star or "|" in star:
            normalized = star.replace("|", "/")
            left, right = normalized.split("/", 1)
            left = left or "Unknown"
            right = right or "Unknown"
            return f"{left}/{right}"

    alleles = []
    for variant in variants_for_gene:
        star = normalize_star_allele(variant.get("star_allele"))
        if star == "Unknown":
            continue
        alleles.append(star)

    if len(alleles) >= 2:
        return f"{alleles[0]}/{alleles[1]}"
    if len(alleles) == 1:
        return f"{alleles[0]}/Unknown"
    return "Unknown"


def classify_allele(gene, allele):
    allele = normalize_star_allele(allele)
    if allele == "Unknown":
        return "unknown"

    gene_rules = GENE_ALLELE_CLASSIFICATION.get(gene)
    if not gene_rules:
        return "unknown"

    if allele in gene_rules["no_function"]:
        return "no_function"
    if allele in gene_rules["reduced"]:
        return "reduced"
    if allele in gene_rules["increased"] or "XN" in allele:
        return "increased"
    if allele in gene_rules["normal"] or allele.startswith("*1"):
        return "normal"
    return "unknown"


def infer_phenotype_from_diplotype(gene, diplotype):
    if not gene or not diplotype or diplotype == "Unknown":
        return "Unknown"

    if "/" not in diplotype:
        return "Unknown"

    left, right = diplotype.split("/", 1)
    statuses = [classify_allele(gene, left), classify_allele(gene, right)]

    if gene == "CYP2D6":
        if statuses.count("no_function") == 2:
            return "PM"
        if "no_function" in statuses and ("normal" in statuses or "reduced" in statuses):
            return "IM"
        if statuses.count("reduced") == 2 or ("reduced" in statuses and "normal" in statuses):
            return "IM"
        if "increased" in statuses and all(status in {"normal", "increased"} for status in statuses):
            return "URM"
        if statuses.count("normal") == 2:
            return "NM"
        if "increased" in statuses:
            return "RM"
        return "Unknown"

    if gene == "CYP2C19":
        if statuses.count("no_function") == 2:
            return "PM"
        if "no_function" in statuses:
            return "IM"
        if statuses.count("increased") == 2:
            return "URM"
        if "increased" in statuses and "normal" in statuses:
            return "RM"
        if statuses.count("normal") == 2:
            return "NM"
        if "reduced" in statuses:
            return "IM"
        return "Unknown"

    impaired_count = sum(1 for status in statuses if status in {"no_function", "reduced"})
    normal_count = statuses.count("normal")
    increased_count = statuses.count("increased")

    if impaired_count == 2:
        return "PM"
    if impaired_count == 1 and normal_count == 1:
        return "IM"
    if normal_count == 2:
        return "NM"
    if increased_count >= 1 and normal_count >= 1:
        return "RM"
    if increased_count == 2:
        return "URM"
    return "Unknown"


def calculate_confidence_score(has_variants, diplotype, phenotype, risk_label, supported_drug):
    score = 0.1
    if has_variants:
        score += 0.35
    if diplotype != "Unknown":
        score += 0.2
    if phenotype != "Unknown":
        score += 0.2
    if supported_drug:
        score += 0.15

    if risk_label == "Unknown":
        score = min(score, 0.55)

    return round(min(score, 0.99), 2)


def build_clinical_recommendation(drug, risk_label, phenotype, recommendation, cpic_reference):
    alternative_options = {
        "CODEINE": ["Morphine", "Hydromorphone"],
        "WARFARIN": ["Frequent INR-guided dosing", "Alternative anticoagulation assessment"],
        "CLOPIDOGREL": ["Prasugrel", "Ticagrelor"],
        "SIMVASTATIN": ["Pravastatin", "Rosuvastatin"],
        "AZATHIOPRINE": ["Dose-reduced thiopurine", "Non-thiopurine immunosuppressant"],
        "FLUOROURACIL": ["Dose-reduced fluoropyrimidine", "Non-fluoropyrimidine regimen"],
    }

    risk_action = {
        "Safe": "Proceed with standard initiation and routine monitoring.",
        "Adjust Dosage": "Initiate therapy with genotype-informed dose modification.",
        "Toxic": "Avoid standard dosing; use alternative or strongly reduced dose.",
        "Ineffective": "Prefer alternative therapy due to likely treatment failure.",
        "Unknown": "Use caution, consider confirmatory pharmacogenomic testing.",
    }

    return {
        "recommendation": recommendation,
        "action": risk_action.get(risk_label, risk_action["Unknown"]),
        "monitoring_plan": "Monitor clinical response and adverse effects during early therapy.",
        "alternative_options": alternative_options.get(drug, []),
        "cpic_guideline_reference": cpic_reference,
        "phenotype_context": phenotype,
    }


def try_external_llm_explanation(context, fallback_payload):
    use_external = str(os.getenv("PHARMAGUARD_USE_LLM", "false")).lower() in {"1", "true", "yes"}
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not use_external or not api_key:
        return fallback_payload

    model = os.getenv("PHARMAGUARD_LLM_MODEL", "gpt-4o-mini")
    api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

    prompt = (
        "You are a clinical pharmacogenomics assistant. Produce concise JSON with keys: "
        "summary, biological_mechanism, variant_significance, clinical_impact, citations. "
        "Use only evidence in the context. Avoid hallucinations.\n\n"
        f"Context: {json.dumps(context)}"
    )

    request_body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return strictly valid JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 350,
    }

    req = urllib.request.Request(
        api_url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))
            model_text = (
                raw_payload.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not model_text:
                return fallback_payload

            parsed = json.loads(model_text)
            if not isinstance(parsed, dict):
                return fallback_payload

            required_keys = {
                "summary",
                "biological_mechanism",
                "variant_significance",
                "clinical_impact",
                "citations",
            }
            if not required_keys.issubset(parsed.keys()):
                return fallback_payload

            parsed["model"] = model
            return parsed
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
        return fallback_payload


def generate_explanation(drug, primary_gene, diplotype, phenotype, risk_label, variants, recommendation):
    variant_citations = []
    for variant in variants[:5]:
        rsid = variant.get("rsid") or "Unknown"
        star = variant.get("star_allele") or "Unknown"
        variant_citations.append(f"{rsid} ({primary_gene} {star})")

    if not variant_citations:
        variant_citations.append("No actionable pharmacogenomic variant annotations detected for this gene.")

    mechanism_lookup = {
        "CYP2D6": "CYP2D6 converts codeine into active morphine. Altered enzyme activity changes efficacy and toxicity.",
        "CYP2C19": "CYP2C19 activates clopidogrel to its antiplatelet metabolite. Reduced function lowers platelet inhibition.",
        "CYP2C9": "CYP2C9 metabolizes warfarin. Reduced metabolism can increase exposure and bleeding risk.",
        "SLCO1B1": "SLCO1B1 controls hepatic statin uptake. Reduced transporter function raises simvastatin plasma levels.",
        "TPMT": "TPMT inactivates thiopurines. Low activity elevates active metabolites and marrow toxicity risk.",
        "DPYD": "DPYD catabolizes fluoropyrimidines. Reduced activity causes severe drug accumulation toxicity.",
    }

    fallback_payload = {
        "summary": (
            f"For {drug}, the detected {primary_gene} diplotype {diplotype} maps to phenotype {phenotype}, "
            f"which is associated with a {risk_label} response profile."
        ),
        "biological_mechanism": mechanism_lookup.get(
            primary_gene,
            "The uploaded genotype did not provide a clear pharmacogene mechanism for this drug.",
        ),
        "variant_significance": (
            f"Detected pharmacogenomic variants indicate {primary_gene} activity pattern consistent with {phenotype}."
        ),
        "clinical_impact": recommendation,
        "citations": variant_citations,
        "model": "pharmaguard-explainer-v1",
    }

    return try_external_llm_explanation(
        {
            "drug": drug,
            "primary_gene": primary_gene,
            "diplotype": diplotype,
            "phenotype": phenotype,
            "risk_label": risk_label,
            "recommendation": recommendation,
            "citations": variant_citations,
        },
        fallback_payload,
    )


def build_quality_metrics(
    parsing_metrics,
    primary_gene,
    primary_variants,
    phenotype,
    supported_drug,
    explanation_payload,
):
    return {
        "vcf_parsing_success": parsing_metrics["vcf_parsing_success"],
        "fileformat_detected": parsing_metrics["fileformat_detected"],
        "header_detected": parsing_metrics["header_detected"],
        "total_variant_lines": parsing_metrics["total_variant_lines"],
        "supported_variant_lines": parsing_metrics["supported_variant_lines"],
        "unique_supported_genes": parsing_metrics["unique_supported_genes"],
        "variant_annotation_completeness": parsing_metrics["variant_annotation_completeness"],
        "primary_gene_variants_found": len(primary_variants),
        "gene_coverage_ratio": parsing_metrics["gene_coverage_ratio"],
        "primary_gene_detected": bool(primary_gene != "Unknown" and primary_variants),
        "phenotype_resolved": phenotype != "Unknown",
        "supported_drug": supported_drug,
        "llm_response_valid": bool(explanation_payload and explanation_payload.get("summary")),
    }


def create_pharmacogenomic_report(patient_id, drug, grouped_variants, parsing_metrics):
    normalized_drug = drug.upper()
    drug_rule = DRUG_RULES.get(normalized_drug)
    supported_drug = bool(drug_rule)

    primary_gene = drug_rule["primary_gene"] if drug_rule else "Unknown"
    primary_variants = grouped_variants.get(primary_gene, []) if primary_gene != "Unknown" else []

    diplotype = build_diplotype(primary_variants)
    phenotype = infer_phenotype_from_diplotype(primary_gene, diplotype) if primary_gene != "Unknown" else "Unknown"

    if supported_drug:
        phenotype_rule = drug_rule["phenotype_rules"].get(phenotype, drug_rule["default_rule"])
        cpic_reference = drug_rule["cpic_reference"]
    else:
        phenotype_rule = {
            "risk_label": "Unknown",
            "severity": "moderate",
            "recommendation": "Drug is not in the current PharmaGuard support set.",
        }
        cpic_reference = "No CPIC mapping configured for this drug."

    risk_label = phenotype_rule["risk_label"]
    severity = phenotype_rule["severity"]
    recommendation_text = phenotype_rule["recommendation"]
    confidence_score = calculate_confidence_score(
        bool(primary_variants),
        diplotype,
        phenotype,
        risk_label,
        supported_drug,
    )

    clinical_recommendation = build_clinical_recommendation(
        normalized_drug,
        risk_label,
        phenotype,
        recommendation_text,
        cpic_reference,
    )
    explanation_payload = generate_explanation(
        normalized_drug,
        primary_gene,
        diplotype,
        phenotype,
        risk_label,
        primary_variants,
        recommendation_text,
    )
    quality_metrics = build_quality_metrics(
        parsing_metrics,
        primary_gene,
        primary_variants,
        phenotype,
        supported_drug,
        explanation_payload,
    )

    return {
        "patient_id": patient_id,
        "drug": normalized_drug,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "risk_assessment": {
            "risk_label": risk_label,
            "confidence_score": confidence_score,
            "severity": severity,
        },
        "pharmacogenomic_profile": {
            "primary_gene": primary_gene,
            "diplotype": diplotype,
            "phenotype": phenotype,
            "detected_variants": primary_variants,
        },
        "clinical_recommendation": clinical_recommendation,
        "llm_generated_explanation": explanation_payload,
        "quality_metrics": quality_metrics,
    }


def store_pharmacogenomic_report(report):
    execute_query(
        """
        INSERT INTO pharmacogenomic_reports (patient_id, drug, risk_label, phenotype, report_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            report["patient_id"],
            report["drug"],
            report["risk_assessment"]["risk_label"],
            report["pharmacogenomic_profile"]["phenotype"],
            json.dumps(report),
        ),
    )


def upsert_patient(data):
    name = str(data.get("name", "")).strip()
    age = parse_int(data.get("age"), 0)
    gender = str(data.get("gender") or "Male")
    contact = str(data.get("contact", "")).strip()
    blood_group = str(data.get("bloodGroup", "")).strip()
    allergies = str(data.get("allergies", "")).strip()
    chronic_conditions = str(data.get("chronicConditions", "")).strip()

    contact_for_db = contact if contact else None
    patient_id = parse_int(data.get("id"), 0)

    if patient_id > 0:
        execute_query(
            """
            UPDATE patients
            SET name = %s, age = %s, gender = %s, contact = %s,
                blood_group = %s, allergies = %s, chronic_conditions = %s
            WHERE id = %s
            """,
            (name, age, gender, contact_for_db, blood_group, allergies, chronic_conditions, patient_id),
        )
        return patient_id

    existing = None
    if contact_for_db:
        existing = fetch_one("SELECT id FROM patients WHERE contact = %s", (contact_for_db,))

    if existing:
        patient_id = existing["id"]
        execute_query(
            """
            UPDATE patients
            SET name = %s, age = %s, gender = %s,
                blood_group = %s, allergies = %s, chronic_conditions = %s
            WHERE id = %s
            """,
            (name, age, gender, blood_group, allergies, chronic_conditions, patient_id),
        )
        return patient_id

    return execute_query(
        """
        INSERT INTO patients (name, age, gender, contact, blood_group, allergies, chronic_conditions)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (name, age, gender, contact_for_db, blood_group, allergies, chronic_conditions),
    )


def get_or_create_patient_for_appointment(patient_name, age, contact):
    contact_for_db = contact if contact else None

    if contact_for_db:
        existing = fetch_one("SELECT id FROM patients WHERE contact = %s", (contact_for_db,))
        if existing:
            execute_query(
                """
                UPDATE patients
                SET name = %s, age = %s
                WHERE id = %s
                """,
                (patient_name, age, existing["id"]),
            )
            return existing["id"]

    return execute_query(
        """
        INSERT INTO patients (name, age, contact)
        VALUES (%s, %s, %s)
        """,
        (patient_name, age, contact_for_db),
    )


def initialize_database():
    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS departments (
            id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            icon VARCHAR(50) NOT NULL,
            active_doctors INT NOT NULL DEFAULT 0,
            average_wait_time INT NOT NULL DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS symptoms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            symptom VARCHAR(200) NOT NULL UNIQUE,
            department_id VARCHAR(50) NOT NULL,
            urgency VARCHAR(20) NOT NULL DEFAULT 'Normal',
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL UNIQUE,
            specialty VARCHAR(120) NOT NULL,
            experience VARCHAR(120) NOT NULL,
            image TEXT,
            rating DECIMAL(2,1) NOT NULL DEFAULT 4.5
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS verified_docters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            doctor_name VARCHAR(120) NOT NULL,
            department_id VARCHAR(50) NOT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS testimonials (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            comment VARCHAR(500) NOT NULL,
            rating INT NOT NULL,
            UNIQUE KEY testimonial_unique (name, comment)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(120),
            age INT,
            gender VARCHAR(20) DEFAULT 'Male',
            contact VARCHAR(40) UNIQUE,
            blood_group VARCHAR(10),
            allergies TEXT,
            chronic_conditions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NULL,
            patient_name VARCHAR(120) NOT NULL,
            age INT,
            symptom TEXT,
            department_id VARCHAR(50) NOT NULL,
            appointment_date DATE NOT NULL,
            contact VARCHAR(40),
            estimated_time VARCHAR(20) NOT NULL DEFAULT '20 mins',
            urgency VARCHAR(20) NOT NULL DEFAULT 'Normal',
            token_number VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pharmacogenomic_reports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id VARCHAR(80) NOT NULL,
            drug VARCHAR(80) NOT NULL,
            risk_label VARCHAR(40) NOT NULL,
            phenotype VARCHAR(40) NOT NULL,
            report_json LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    mysql.connection.commit()
    cursor.close()

    execute_many(
        """
        INSERT IGNORE INTO departments (id, name, icon, active_doctors, average_wait_time)
        VALUES (%s, %s, %s, %s, %s)
        """,
        DEPARTMENTS_SEED,
    )

    execute_many(
        """
        INSERT IGNORE INTO symptoms (symptom, department_id, urgency)
        VALUES (%s, %s, %s)
        """,
        SYMPTOMS_SEED,
    )

    execute_many(
        """
        INSERT IGNORE INTO doctors (name, specialty, experience, image, rating)
        VALUES (%s, %s, %s, %s, %s)
        """,
        DOCTORS_SEED,
    )

    execute_many(
        """
        INSERT IGNORE INTO verified_docters (username, password_hash, doctor_name, department_id)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (username, generate_password_hash(password), doctor_name, department_id)
            for username, doctor_name, department_id, password in VERIFIED_DOCTERS_SEED
        ],
    )

    execute_many(
        """
        INSERT IGNORE INTO testimonials (name, comment, rating)
        VALUES (%s, %s, %s)
        """,
        TESTIMONIALS_SEED,
    )


def ensure_database_initialized():
    global DB_INITIALIZED
    if DB_INITIALIZED:
        return
    initialize_database()
    DB_INITIALIZED = True


@app.before_request
def initialize_before_request():
    if request.method == "OPTIONS":
        return ("", 204)
    ensure_database_initialized()


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Running", "manager": "Flask", "service": "PulsePoint API"})


@app.route("/api/reference-data", methods=["GET"])
def get_reference_data():
    departments = fetch_all(
        """
        SELECT id, name, icon, active_doctors, average_wait_time
        FROM departments
        ORDER BY name
        """
    )

    symptoms = fetch_all(
        """
        SELECT s.id, s.symptom, s.department_id, s.urgency, d.name AS department_name
        FROM symptoms s
        JOIN departments d ON d.id = s.department_id
        ORDER BY s.symptom
        """
    )

    doctors = fetch_all(
        """
        SELECT id, name, specialty, experience, image, rating
        FROM doctors
        ORDER BY id
        """
    )

    testimonials = fetch_all(
        """
        SELECT id, name, comment, rating
        FROM testimonials
        ORDER BY id
        """
    )

    return jsonify(
        {
            "departments": [serialize_department(row) for row in departments],
            "symptoms": [serialize_symptom(row) for row in symptoms],
            "doctors": [serialize_doctor(row) for row in doctors],
            "testimonials": [serialize_testimonial(row) for row in testimonials],
        }
    )


@app.route("/api/pharmacogenomics/meta", methods=["GET"])
def get_pharmacogenomics_meta():
    return jsonify(
        {
            "supported_genes": sorted(SUPPORTED_PHARMACOGENES),
            "supported_drugs": list(SUPPORTED_PHARMACOGENOMIC_DRUGS),
            "max_vcf_size_mb": 5,
        }
    )


@app.route("/api/pharmacogenomics/analyze", methods=["POST"])
def analyze_pharmacogenomics():
    payload = request.get_json(silent=True) if request.is_json else {}

    patient_id = str(
        request.form.get("patient_id")
        or payload.get("patient_id")
        or f"PATIENT_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    ).strip()
    if not patient_id:
        patient_id = f"PATIENT_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    raw_drugs = request.form.get("drugs") or request.form.get("drug_names") or payload.get("drugs") or ""
    drugs = split_drug_names(raw_drugs)
    if not drugs:
        return jsonify({"error": "At least one drug name is required."}), 400

    vcf_file = request.files.get("vcf_file")
    vcf_content = ""
    input_filename = ""

    if vcf_file:
        input_filename = (vcf_file.filename or "").strip()
        if not input_filename.lower().endswith(".vcf"):
            return jsonify({"error": "Invalid file type. Please upload a .vcf file."}), 400

        file_bytes = vcf_file.read()
        if not file_bytes:
            return jsonify({"error": "Uploaded VCF file is empty."}), 400
        if len(file_bytes) > MAX_VCF_FILE_SIZE_BYTES:
            return jsonify({"error": "VCF file exceeds 5 MB limit."}), 413

        try:
            vcf_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            vcf_content = file_bytes.decode("latin-1")
    else:
        fallback_content = payload.get("vcf_content") or payload.get("vcf")
        if not fallback_content:
            return jsonify({"error": "VCF file upload is required."}), 400
        vcf_content = str(fallback_content)
        if len(vcf_content.encode("utf-8")) > MAX_VCF_FILE_SIZE_BYTES:
            return jsonify({"error": "VCF content exceeds 5 MB limit."}), 413

    variants, parsing_metrics = parse_vcf_content(vcf_content)
    if not parsing_metrics["vcf_parsing_success"]:
        return (
            jsonify(
                {
                    "error": (
                        "Invalid VCF structure. Ensure file includes standard VCF headers and variant rows."
                    )
                }
            ),
            400,
        )

    grouped_variants = group_variants_by_gene(variants)
    reports = []

    for drug in drugs:
        report = create_pharmacogenomic_report(patient_id, drug, grouped_variants, parsing_metrics)
        reports.append(report)
        try:
            store_pharmacogenomic_report(report)
        except Exception:
            # Report persistence should not block risk analysis responses.
            pass

    response_payload = {
        "patient_id": patient_id,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_drugs": drugs,
        "input_file": input_filename,
        "reports": reports,
        "quality_summary": {
            "vcf_parsing_success": parsing_metrics["vcf_parsing_success"],
            "fileformat_detected": parsing_metrics["fileformat_detected"],
            "total_variant_lines": parsing_metrics["total_variant_lines"],
            "supported_variant_lines": parsing_metrics["supported_variant_lines"],
            "gene_coverage_ratio": parsing_metrics["gene_coverage_ratio"],
        },
    }
    if len(reports) == 1:
        response_payload["report"] = reports[0]

    return jsonify(response_payload)


@app.route("/api/queue", methods=["GET"])
def get_queue():
    departments = fetch_all(
        """
        SELECT id, name, icon, active_doctors, average_wait_time
        FROM departments
        ORDER BY name
        """
    )

    today = date.today()
    queue_data = []

    for dept in departments:
        waiting_row = fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM appointments
            WHERE department_id = %s
              AND appointment_date = %s
              AND status IN ('Pending', 'In Progress')
            """,
            (dept["id"], today),
        )

        served_row = fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM appointments
            WHERE department_id = %s
              AND appointment_date = %s
              AND status = 'Completed'
            """,
            (dept["id"], today),
        )

        queue_data.append(
            {
                **serialize_department(dept),
                "currentToken": parse_int(served_row["total"], 0) + 1,
                "totalWaiting": parse_int(waiting_row["total"], 0),
            }
        )

    return jsonify({"queue": queue_data})


@app.route("/api/patients/latest", methods=["GET"])
def get_latest_patient():
    row = fetch_one(
        """
        SELECT id, name, age, gender, contact, blood_group, allergies, chronic_conditions
        FROM patients
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )

    return jsonify({"patient": serialize_patient(row)})


@app.route("/api/patients", methods=["POST"])
def save_patient():
    data = request.get_json(silent=True) or {}
    patient_id = upsert_patient(data)

    row = fetch_one(
        """
        SELECT id, name, age, gender, contact, blood_group, allergies, chronic_conditions
        FROM patients
        WHERE id = %s
        """,
        (patient_id,),
    )

    return jsonify({"patient": serialize_patient(row)})


@app.route("/api/appointments", methods=["GET"])
def get_appointments():
    rows = fetch_all(
        """
        SELECT
            a.id,
            a.patient_name,
            a.age,
            a.symptom,
            a.department_id,
            a.appointment_date,
            a.estimated_time,
            a.urgency,
            a.token_number,
            a.status,
            a.created_at,
            d.name AS department_name
        FROM appointments a
        LEFT JOIN departments d ON d.id = a.department_id
        ORDER BY a.created_at DESC
        """
    )

    return jsonify({"appointments": [serialize_appointment(row) for row in rows]})


@app.route("/api/docter/login", methods=["POST"])
@app.route("/api/doctor/login", methods=["POST"])
def doctor_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    row = fetch_one(
        """
        SELECT
            vd.id,
            vd.username,
            vd.password_hash,
            vd.doctor_name,
            vd.department_id,
            d.name AS department_name
        FROM verified_docters vd
        LEFT JOIN departments d ON d.id = vd.department_id
        WHERE vd.username = %s AND vd.is_active = 1
        LIMIT 1
        """,
        (username,),
    )

    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"doctor": serialize_verified_docter(row)})


@app.route("/api/appointments", methods=["POST"])
def create_appointment():
    data = request.get_json(silent=True) or {}

    patient_name = str(data.get("patientName", "")).strip()
    age = parse_int(data.get("age"), 0)
    symptom = str(data.get("symptom", "")).strip()
    department_id = str(data.get("department", "")).strip()
    contact = str(data.get("contact", "")).strip()
    urgency = str(data.get("urgency") or "Normal")

    if not patient_name or not department_id or not symptom:
        return jsonify({"error": "patientName, department and symptom are required"}), 400

    department = fetch_one("SELECT id, average_wait_time FROM departments WHERE id = %s", (department_id,))
    if not department:
        return jsonify({"error": "Invalid department"}), 400

    appointment_date = parse_date(data.get("date"))

    patient_id = get_or_create_patient_for_appointment(patient_name, age, contact)

    token_count_row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM appointments
        WHERE department_id = %s AND appointment_date = %s
        """,
        (department_id, appointment_date),
    )

    token_sequence = parse_int(token_count_row["total"], 0) + 1
    token_prefix = department_id[:2].upper()
    token_number = f"{token_prefix}-{token_sequence:03d}"
    estimated_time = f"{parse_int(department['average_wait_time'], 20)} mins"

    appointment_id = execute_query(
        """
        INSERT INTO appointments (
            patient_id,
            patient_name,
            age,
            symptom,
            department_id,
            appointment_date,
            contact,
            estimated_time,
            urgency,
            token_number,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
        """,
        (
            patient_id,
            patient_name,
            age,
            symptom,
            department_id,
            appointment_date,
            contact if contact else None,
            estimated_time,
            urgency,
            token_number,
        ),
    )

    row = fetch_one(
        """
        SELECT
            a.id,
            a.patient_name,
            a.age,
            a.symptom,
            a.department_id,
            a.appointment_date,
            a.estimated_time,
            a.urgency,
            a.token_number,
            a.status,
            a.created_at,
            d.name AS department_name
        FROM appointments a
        LEFT JOIN departments d ON d.id = a.department_id
        WHERE a.id = %s
        """,
        (appointment_id,),
    )

    return jsonify({"appointment": serialize_appointment(row)}), 201


@app.route("/api/appointments/<int:appointment_id>/status", methods=["PATCH"])
def update_appointment_status(appointment_id):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()

    allowed_statuses = {"Pending", "In Progress", "Completed", "Cancelled"}
    if status not in allowed_statuses:
        return jsonify({"error": "Invalid status"}), 400

    existing = fetch_one("SELECT id FROM appointments WHERE id = %s", (appointment_id,))
    if not existing:
        return jsonify({"error": "Appointment not found"}), 404

    execute_query("UPDATE appointments SET status = %s WHERE id = %s", (status, appointment_id))

    row = fetch_one(
        """
        SELECT
            a.id,
            a.patient_name,
            a.age,
            a.symptom,
            a.department_id,
            a.appointment_date,
            a.estimated_time,
            a.urgency,
            a.token_number,
            a.status,
            a.created_at,
            d.name AS department_name
        FROM appointments a
        LEFT JOIN departments d ON d.id = a.department_id
        WHERE a.id = %s
        """,
        (appointment_id,),
    )

    return jsonify({"appointment": serialize_appointment(row)})


@app.route("/api/demo/reset", methods=["POST"])
def reset_demo_data():
    execute_query("DELETE FROM appointments")
    execute_query("DELETE FROM patients")

    return jsonify({"message": "Demo data reset complete"})


@app.route("/api/emergency", methods=["POST"])
def emergency():
    data = request.get_json(silent=True) or {}
    return jsonify({"message": "Emergency data received", "data": data})


@app.route("/emrgency", methods=["POST", "GET"])
def emergency_legacy():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        return jsonify({"message": "Emergency data received", "data": data})

    return jsonify({"message": "Use POST to submit emergency data"})


if __name__ == "__main__":
    with app.app_context():
        ensure_database_initialized()
    app.run(debug=True)
