"""
CAS (Consolidated Account Statement) PDF Parser
================================================
Parses password-protected CAS PDFs issued by CAMS or NSDL/KFintech.

Returns a structured dict:
{
    "investor": { "name": str, "email": str, "pan": str },
    "holdings": [
        {
            "amc":          str,
            "folio":        str,
            "scheme":       str,           # full scheme name
            "isin":         str,
            "units":        float,
            "avg_nav":      float,         # average cost NAV
            "cost_value":   float,         # total amount invested
            "nav_date":     str,           # date of current NAV
            "current_nav":  float,
            "current_value":float,
            "transactions": [
                {
                    "date":   str,         # DD-MMM-YYYY
                    "type":   str,         # Purchase / Redemption / SIP / Dividend etc.
                    "amount": float,
                    "units":  float,
                    "nav":    float,
                }
            ]
        }
    ]
}
"""

import re
import pdfplumber
from typing import IO

# ── regex patterns ────────────────────────────────────────────────────────────

# Investor name: "Name : JOHN DOE" or "Investor Name: JOHN DOE"
RE_INVESTOR_NAME  = re.compile(r"(?:Investor\s+)?Name\s*:\s*(.+)", re.IGNORECASE)
# Email
RE_EMAIL          = re.compile(r"Email\s*(?:Id|Address)?\s*:\s*([\w.\-+]+@[\w.\-]+)", re.IGNORECASE)
# PAN (masked or full)
RE_PAN            = re.compile(r"\b([A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z])\b")

# Folio line: "Folio No: 12345678 / 12"  or  "Folio No.: 12345678"
RE_FOLIO          = re.compile(r"Folio\s*No\.?\s*:?\s*([\w/\- ]+?)(?:\s{2,}|\t|$)", re.IGNORECASE)

# ISIN line inside scheme heading
RE_ISIN           = re.compile(r"ISIN\s*:\s*(IN[A-Z0-9]{10})", re.IGNORECASE)

# Closing balance / current holding line
# e.g. "Closing Unit Balance: 234.567"  or  "Units: 234.567"
RE_UNITS          = re.compile(r"(?:Closing\s+Unit\s+Balance|Units)\s*[:\-]?\s*([\d,]+\.\d+)", re.IGNORECASE)

# NAV line: "NAV on DD-MMM-YYYY : 89.4500"
RE_NAV_VALUED     = re.compile(r"NAV\s+on\s+([\d\-A-Za-z]+)\s*:\s*([\d,]+\.?\d*)", re.IGNORECASE)

# Market value line: "Market Value as on DD-MMM-YYYY : 20983.23"
RE_MARKET_VALUE   = re.compile(r"Market\s+Value.*?:\s*([\d,]+\.?\d*)", re.IGNORECASE)

# Cost value / invested amount line
RE_COST_VALUE     = re.compile(r"(?:Cost\s+Value|Amount\s+Invested|Purchase\s+Cost)\s*[:\-]?\s*([\d,]+\.?\d*)", re.IGNORECASE)

# Transaction line (very varied — we match the most common patterns):
# "15-Jan-2023  (P)  Purchase                 5000.00   118.200   42.3000"
# "15-Jan-2023  SIP - Instalment              5000.00   113.400   44.1000"
RE_TRANSACTION    = re.compile(
    r"(\d{2}[-/]\w{3}[-/]\d{4})"          # date
    r"\s+"
    r"(?:\(\w+\)\s*)?"                     # optional type code like (P)
    r"([A-Za-z][A-Za-z\s\-/]+?)"          # transaction type (description)
    r"\s{2,}"
    r"([\d,]+\.?\d*)"                      # amount
    r"\s+"
    r"([\d,]+\.?\d*)"                      # units
    r"\s+"
    r"([\d,]+\.?\d*)"                      # NAV
)

# AMC header line — typically ALL CAPS or Title Case followed by "Mutual Fund"
RE_AMC_HEADER     = re.compile(r"^(.{5,60}?(?:Mutual Fund|AMC|Asset Management))\s*$", re.IGNORECASE)

# Scheme name: line containing "Fund" or "Scheme" that follows a folio line
# We use a looser heuristic — captured contextually, not regex-only


def _clean_float(s: str) -> float:
    """Remove commas and convert to float. Returns 0.0 on failure."""
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return 0.0


def parse_cas(file: IO[bytes], password: str) -> dict:
    """
    Parse a CAMS/NSDL CAS PDF.

    Parameters
    ----------
    file     : file-like object (bytes) of the PDF
    password : PDF password (typically PAN+DOB, e.g. ABCDE1234F01011990)

    Returns
    -------
    dict with keys: investor, holdings
    """
    investor = {"name": "", "email": "", "pan": ""}
    holdings: list = []

    # ── open PDF ─────────────────────────────────────────────────────────────
    with pdfplumber.open(file, password=password) as pdf:
        all_lines: list[str] = []
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            all_lines.extend(text.splitlines())

    # ── pass 1: investor info (first 20 lines usually) ───────────────────────
    for line in all_lines[:30]:
        line = line.strip()
        if not investor["name"]:
            m = RE_INVESTOR_NAME.search(line)
            if m:
                investor["name"] = m.group(1).strip()
        if not investor["email"]:
            m = RE_EMAIL.search(line)
            if m:
                investor["email"] = m.group(1).strip()
        if not investor["pan"]:
            m = RE_PAN.search(line)
            if m:
                investor["pan"] = m.group(1).strip()

    # ── pass 2: holdings ─────────────────────────────────────────────────────
    current_amc     = ""
    current_folio   = ""
    current_scheme  = ""
    current_isin    = ""
    current_txns: list = []
    current_units   = 0.0
    current_nav     = 0.0
    current_nav_date= ""
    current_market  = 0.0
    current_cost    = 0.0
    in_txn_block    = False   # True after we see the transaction header row

    def _flush():
        """Save current holding to list if it has meaningful data."""
        nonlocal current_txns, current_units, current_nav, current_nav_date
        nonlocal current_market, current_cost, current_scheme, current_isin
        nonlocal current_folio, in_txn_block

        if current_scheme and current_units > 0:
            avg_nav = (current_cost / current_units) if current_units else 0.0
            holdings.append({
                "amc":           current_amc,
                "folio":         current_folio,
                "scheme":        current_scheme,
                "isin":          current_isin,
                "units":         round(current_units, 4),
                "avg_nav":       round(avg_nav, 4),
                "cost_value":    round(current_cost, 2),
                "nav_date":      current_nav_date,
                "current_nav":   round(current_nav, 4),
                "current_value": round(current_market, 2),
                "transactions":  list(current_txns),
            })
        # reset
        current_txns      = []
        current_units     = 0.0
        current_nav       = 0.0
        current_nav_date  = ""
        current_market    = 0.0
        current_cost      = 0.0
        current_scheme    = ""
        current_isin      = ""
        in_txn_block      = False

    i = 0
    while i < len(all_lines):
        raw = all_lines[i]
        line = raw.strip()
        i += 1

        if not line:
            continue

        # ── AMC header ───────────────────────────────────────────────────────
        m = RE_AMC_HEADER.match(line)
        if m:
            current_amc = m.group(1).strip()
            continue

        # ── Folio line ───────────────────────────────────────────────────────
        if re.search(r"Folio\s*No", line, re.IGNORECASE):
            # flush previous holding before starting new one
            _flush()
            m = RE_FOLIO.search(line)
            if m:
                current_folio = m.group(1).strip()
            # Scheme name is usually on the same line or the next non-empty line
            # Try same line first (after the folio)
            after_folio = RE_FOLIO.sub("", line).strip(" :-/")
            if len(after_folio) > 6:
                current_scheme = after_folio
            else:
                # look ahead for scheme name
                for j in range(i, min(i + 4, len(all_lines))):
                    candidate = all_lines[j].strip()
                    if candidate and not re.search(r"Folio|ISIN|PAN|Registrar", candidate, re.IGNORECASE):
                        current_scheme = candidate
                        break
            continue

        # ── ISIN ─────────────────────────────────────────────────────────────
        m = RE_ISIN.search(line)
        if m:
            current_isin = m.group(1).strip()
            # scheme name sometimes precedes ISIN on same line
            before_isin = line[:m.start()].strip(" :-")
            if len(before_isin) > 6 and not current_scheme:
                current_scheme = before_isin
            continue

        # ── transaction header / start of txn block ──────────────────────────
        if re.search(r"Transaction\s+Date|Date\s+Transaction", line, re.IGNORECASE):
            in_txn_block = True
            continue

        # ── transaction row ──────────────────────────────────────────────────
        if in_txn_block:
            m = RE_TRANSACTION.search(line)
            if m:
                current_txns.append({
                    "date":   m.group(1).strip(),
                    "type":   m.group(2).strip(),
                    "amount": _clean_float(m.group(3)),
                    "units":  _clean_float(m.group(4)),
                    "nav":    _clean_float(m.group(5)),
                })
                continue

        # ── closing units ─────────────────────────────────────────────────────
        m = RE_UNITS.search(line)
        if m:
            current_units = _clean_float(m.group(1))
            continue

        # ── current NAV ───────────────────────────────────────────────────────
        m = RE_NAV_VALUED.search(line)
        if m:
            current_nav_date = m.group(1).strip()
            current_nav      = _clean_float(m.group(2))
            continue

        # ── market value ──────────────────────────────────────────────────────
        m = RE_MARKET_VALUE.search(line)
        if m:
            current_market = _clean_float(m.group(1))
            continue

        # ── cost value ────────────────────────────────────────────────────────
        m = RE_COST_VALUE.search(line)
        if m:
            current_cost = _clean_float(m.group(1))
            continue

    # flush last holding
    _flush()

    return {
        "investor": investor,
        "holdings": holdings,
    }
