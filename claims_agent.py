#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

DATE_RE = (
    r"(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12]\d|3[01])[\/\-](?:\d{2}|\d{4})|"
    r"(?:\d{4}[\/\-](?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12]\d|3[01]))|"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Sept|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Sept|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}"
)

TIME_RE = r"(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[AP]M)?|(?:1[0-2]|0?[1-9])\s*[AP]M"

AMOUNT_RE = r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{2})?|[0-9]+(?:\.\d{2})?)"

MISSING_TOKENS = {"n/a", "na", "none", "null", "not provided", "unknown", "-"}

PLACEHOLDER_PATTERNS = [
    r"\bfirst\b.*\bmiddle\b.*\blast\b",
    r"\bcity\b.*\bstate\b.*\bzip\b",
    r"\bname\s*of\s*insured\b",
    r"\binsured'?s\s*mailing\s*address\b",
    r"\bphone\b.*\bcell\b",
    r"\bphone\b",
    r"\bfax\b",
    r"\be-?mail\b",
    r"\bdate\s*of\s*birth\b",
    r"\bdrivers?\s*license\b",
    r"\bpolicy\s*number\b",
    r"\bclaim\s*type\b",
    r"\bestimate\s*amount\b",
    r"\bestimated\s*damage\b",
]

STOP_LABELS = [
    r"Policy\s*(?:Number|No\.?|#)",
    r"Policyholder\s*Name",
    r"Policy\s*Holder",
    r"Named\s*Insured",
    r"Insured\s*Name",
    r"Name\s*of\s*Insured",
    r"Incident\s*Date",
    r"Date\s*of\s*Loss",
    r"Loss\s*Date",
    r"Incident\s*Time",
    r"Time\s*of\s*Loss",
    r"Incident\s*Location",
    r"Location\s*of\s*Loss",
    r"Loss\s*Location",
    r"Accident\s*Location",
    r"Street\s*:?,?\s*Location\s*of\s*Loss",
    r"City\s*,?\s*State\s*,?\s*Zip",
    r"Describe\s*Location\s*of\s*Loss",
    r"Incident\s*Description",
    r"Description\s*of\s*Loss",
    r"Description\s*of\s*Accident",
    r"Claim\s*Type",
    r"Type\s*of\s*Claim",
    r"Loss\s*Type",
    r"Estimated\s*Damage",
    r"Estimated\s*Loss",
    r"Estimated\s*Amount",
    r"Estimate\s*Amount",
    r"Damage\s*Estimate",
    r"Initial\s*Estimate",
    r"Attachments?",
    r"Attachment\(s\)",
    r"Documents\s*Attached",
]


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        if pdfplumber is None:
            raise RuntimeError("pdfplumber is required to parse PDF files.")
        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise ValueError("Unsupported file type. Use PDF or TXT.")


def normalize_text(text):
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def clean_value(val):
    if val is None:
        return None
    val = re.sub(r"\s+", " ", val).strip()
    val = val.strip(" :;-\t")
    if not val:
        return None
    if val.lower() in MISSING_TOKENS:
        return None
    return val


def looks_like_label(value):
    if value is None:
        return False
    v = value.strip()
    if not v:
        return False
    v_lower = v.lower()
    for pat in PLACEHOLDER_PATTERNS:
        if re.search(pat, v_lower):
            return True
    letters = [c for c in v if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        words = re.findall(r"[A-Z]{2,}", v)
        if upper_ratio > 0.95 and len(words) >= 3:
            return True
    return False


def is_noise_value(value, max_len=200, label_hit_threshold=3):
    if value is None:
        return False
    v = value.strip()
    if not v:
        return False
    if len(v) > max_len:
        return True
    if re.search(r"\bACORD\b", v, re.IGNORECASE):
        return True
    hits = sum(1 for label in STOP_LABELS if re.search(label, v, re.IGNORECASE))
    if hits >= label_hit_threshold:
        return True
    return False


def validate_policy_number(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if not re.search(r"\d", value):
        return None
    return value


def validate_policyholder_name(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if re.search(r"\b(first|middle|last)\b", value, re.IGNORECASE):
        return None
    words = re.findall(r"[A-Za-z]+", value)
    if len(words) < 2:
        return None
    if any(w.lower() in {"insured", "policy", "name"} for w in words):
        return None
    return value


def validate_location(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if is_noise_value(value, max_len=180, label_hit_threshold=2):
        return None
    return value


def validate_description(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if is_noise_value(value, max_len=400, label_hit_threshold=3):
        return None
    return value


def validate_claim_type(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if is_noise_value(value, max_len=60, label_hit_threshold=2):
        return None
    return value


def validate_attachments(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if re.search(r"\bmay be attached\b|\bschedule\b", value, re.IGNORECASE):
        return None
    if is_noise_value(value, max_len=120, label_hit_threshold=2):
        return None
    return value


def validate_amount_field(value):
    if value is None:
        return None
    if looks_like_label(value):
        return None
    if is_noise_value(value, max_len=80, label_hit_threshold=2):
        return None
    if parse_amount(value) is None:
        return None
    return value


def extract_with_patterns(patterns, text, flat_text=None, flags=re.IGNORECASE | re.MULTILINE):
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            val = clean_value(m.group(1))
            if val and looks_like_label(val):
                continue
            return val
    if flat_text:
        for pat in patterns:
            m = re.search(pat, flat_text, flags)
            if m:
                val = clean_value(m.group(1))
                if val and looks_like_label(val):
                    continue
                return val
    return None


def extract_labeled_line(text, labels):
    patterns = [rf"^\s*{label}\s*[:\-]?\s*([^\n]+)" for label in labels]
    return extract_with_patterns(patterns, text, None, flags=re.IGNORECASE | re.MULTILINE)


def extract_labeled_block(text, labels, stop_labels):
    stop = "|".join(stop_labels)
    for label in labels:
        pat = rf"{label}\s*[:\-]?\s*(.+?)(?=\n\s*(?:{stop})\b|\Z)"
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            val = clean_value(m.group(1))
            if val and looks_like_label(val):
                return None
            return val
    return None


def parse_amount(val):
    if val is None:
        return None
    m = re.search(AMOUNT_RE, val)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


def extract_combined_datetime(text):
    pat = (
        rf"(?:Date\s*/\s*Time\s*of\s*Loss|Loss\s*Date\s*/\s*Time|Date\s*and\s*Time\s*of\s*Loss|"
        rf"Incident\s*Date\s*/\s*Time|Date\s*Time\s*of\s*Incident)\s*[:\-]?\s*({DATE_RE})"
        rf"(?:\s+|,?\s*)({TIME_RE})?"
    )
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        return clean_value(m.group(1)), clean_value(m.group(2))
    return None, None


def extract_fields(text):
    normalized = normalize_text(text)
    flat_text = re.sub(r"\s+", " ", normalized).strip()

    fields = {
        "Policy Number": None,
        "Policyholder Name": None,
        "Incident Date": None,
        "Incident Time": None,
        "Incident Location": None,
        "Incident Description": None,
        "Claim Type": None,
        "Estimated Damage": None,
        "Attachments": None,
        "Initial Estimate": None,
    }

    fields["Policy Number"] = extract_with_patterns(
        [
            r"\bPolicy\s*(?:Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*)",
            r"\bPOLICY\s+NUMBER\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]*)",
        ],
        normalized,
        flat_text,
    )

    fields["Policyholder Name"] = extract_with_patterns(
        [
            r"\bPolicyholder\s*Name\s*[:\-]?\s*([A-Z][A-Za-z ,.'-]+)",
            r"\bPolicy\s*Holder\s*Name\s*[:\-]?\s*([A-Z][A-Za-z ,.'-]+)",
            r"\bName\s*of\s*Insured(?:\s*\(.*?\))?\s*[:\-]?\s*([A-Z][A-Za-z ,.'-]+)",
            r"\bNamed\s*Insured\s*[:\-]?\s*([A-Z][A-Za-z ,.'-]+)",
            r"\bInsured\s*Name\s*[:\-]?\s*([A-Z][A-Za-z ,.'-]+)",
        ],
        normalized,
        flat_text,
    )

    fields["Incident Date"] = extract_with_patterns(
        [
            rf"\b(?:Date\s*of\s*Loss|Loss\s*Date|Incident\s*Date|Accident\s*Date|Date\s*of\s*Incident)\s*[:\-]?\s*({DATE_RE})",
        ],
        normalized,
        flat_text,
    )

    fields["Incident Time"] = extract_with_patterns(
        [
            rf"\b(?:Time\s*of\s*Loss|Loss\s*Time|Incident\s*Time|Accident\s*Time|Time\s*of\s*Incident)\s*[:\-]?\s*({TIME_RE})",
        ],
        normalized,
        flat_text,
    )

    if fields["Incident Date"] is None or fields["Incident Time"] is None:
        combo_date, combo_time = extract_combined_datetime(normalized)
        if fields["Incident Date"] is None:
            fields["Incident Date"] = combo_date
        if fields["Incident Time"] is None:
            fields["Incident Time"] = combo_time

    location_labels = [
        r"Incident\s*Location",
        r"Location\s*of\s*Loss",
        r"Loss\s*Location",
        r"Accident\s*Location",
        r"Street\s*:?,?\s*Location\s*of\s*Loss",
        r"Address\s*of\s*Loss",
        r"Loss\s*Address",
    ]
    street = extract_labeled_line(normalized, location_labels)
    city_state = extract_labeled_line(normalized, [r"City\s*,?\s*State\s*,?\s*Zip"])
    desc_loc = extract_labeled_block(
        normalized,
        [
            r"Describe\s*Location\s*of\s*Loss\s*If\s*Not\s*At\s*Specific\s*Street\s*Address",
            r"Describe\s*Location\s*of\s*Loss",
        ],
        STOP_LABELS,
    )
    if street or city_state or desc_loc:
        parts = [p for p in [street, city_state, desc_loc] if p]
        fields["Incident Location"] = ", ".join(parts) if parts else None
    else:
        fields["Incident Location"] = extract_labeled_block(normalized, location_labels, STOP_LABELS)

    description_labels = [
        r"Incident\s*Description",
        r"Description\s*of\s*Loss",
        r"Description\s*of\s*Accident",
        r"Description\s*of\s*Incident",
        r"Describe\s*Damage",
        r"Describe\s*Property",
    ]
    fields["Incident Description"] = extract_labeled_block(normalized, description_labels, STOP_LABELS)

    claim_labels = [
        r"Claim\s*Type",
        r"Type\s*of\s*Claim",
        r"Loss\s*Type",
        r"Coverage\s*Type",
        r"Type\s*of\s*Loss",
    ]
    fields["Claim Type"] = extract_labeled_line(normalized, claim_labels)
    if fields["Claim Type"] is None:
        m = re.search(
            r"\b(?:claim\s*type|type\s*of\s*claim|loss\s*type)\b[^\n]{0,40}\b(injury|bodily\s*injury|property\s*damage|collision|comprehensive|theft|fire|liability|vandalism|medical)\b",
            flat_text,
            re.IGNORECASE,
        )
        if m:
            fields["Claim Type"] = clean_value(m.group(1))

    fields["Estimated Damage"] = extract_with_patterns(
        [
            r"\b(?:Estimated\s*Damage|Estimated\s*Loss|Estimated\s*Amount|Damage\s*Estimate|Estimated\s*Cost|Total\s*Estimated\s*Damage|Estimate\s*Amount)\s*[:\-]?\s*([^\n]+)",
            r"\bESTIMATE\s*AMOUNT\s*[:\-]?\s*([^\n]+)",
        ],
        normalized,
        flat_text,
    )

    fields["Initial Estimate"] = extract_with_patterns(
        [
            r"\b(?:Initial\s*Estimate|Initial\s*Loss\s*Estimate|Initial\s*Damage\s*Estimate)\s*[:\-]?\s*([^\n]+)",
        ],
        normalized,
        flat_text,
    )

    attachment_labels = [
        r"Attachments?",
        r"Attachment\(s\)",
        r"Documents\s*Attached",
    ]
    fields["Attachments"] = extract_labeled_line(normalized, attachment_labels)
    if fields["Attachments"] is None:
        fields["Attachments"] = extract_labeled_block(normalized, attachment_labels, STOP_LABELS)

    fields["Policy Number"] = validate_policy_number(fields["Policy Number"])
    fields["Policyholder Name"] = validate_policyholder_name(fields["Policyholder Name"])
    fields["Incident Location"] = validate_location(fields["Incident Location"])
    fields["Incident Description"] = validate_description(fields["Incident Description"])
    fields["Claim Type"] = validate_claim_type(fields["Claim Type"])
    fields["Estimated Damage"] = validate_amount_field(fields["Estimated Damage"])
    fields["Initial Estimate"] = validate_amount_field(fields["Initial Estimate"])
    fields["Attachments"] = validate_attachments(fields["Attachments"])

    return fields


def route_claim(fields):
    mandatory = [
        "Policy Number",
        "Policyholder Name",
        "Incident Date",
        "Incident Location",
        "Claim Type",
        "Estimated Damage",
    ]

    missing_fields = [f for f in mandatory if not fields.get(f)]

    if missing_fields:
        return missing_fields, "Manual Review", "Missing mandatory field(s): " + ", ".join(missing_fields)

    desc = (fields.get("Incident Description") or "").lower()
    claim_type = (fields.get("Claim Type") or "").lower()
    est_damage_value = parse_amount(fields.get("Estimated Damage"))

    if re.search(r"\b(fraud|staged|inconsistent)\b", desc, re.IGNORECASE):
        return missing_fields, "Investigation Flag", "Incident description contains fraud indicators."

    if "injury" in claim_type:
        return missing_fields, "Specialist Queue", "Claim type is injury."

    if est_damage_value is not None and est_damage_value < 25000:
        return missing_fields, "Fast-track", "Estimated damage below 25000."

    return missing_fields, "Standard Processing", "All mandatory fields present and no special routing rules matched."


def main():
    ap = argparse.ArgumentParser(description="Rule-based FNOL claims processing agent")
    ap.add_argument("input_path", help="Path to FNOL PDF or TXT")
    args = ap.parse_args()

    if not os.path.isfile(args.input_path):
        print("Input file not found.", file=sys.stderr)
        sys.exit(1)

    try:
        raw_text = extract_text(args.input_path)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    fields = extract_fields(raw_text)
    missing_fields, route, reasoning = route_claim(fields)

    output = {
        "extractedFields": fields,
        "missingFields": missing_fields,
        "recommendedRoute": route,
        "reasoning": reasoning,
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
