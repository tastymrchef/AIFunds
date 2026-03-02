"""
test_extraction_comparison.py
Compares GPT-4o-mini vs Sarvam on ICICI Large & Mid Cap Fund (page 16)
Run from project root: python test_extraction_comparison.py
"""

import fitz
import requests
import json
import re
import os
import zipfile
from openai import OpenAI
from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

EXTRACTION_SYSTEM = """You extract mutual fund portfolio data from Indian AMC factsheet text.

The portfolio table may be laid out in TWO COLUMNS side by side (left column + right column).
Company names sometimes wrap across two rows — join them into one name.
Sector headers (like "Banks", "Auto Components") are NOT holdings — skip them.
Only extract actual company/instrument names with a % to NAV weight.

Extract the COMPLETE list of holdings. For each holding return:
- stock: company/bond/instrument name (clean, no bullet points, no sector headers)
- weight: percentage weight in portfolio (e.g. "8.24%") — null if not found
- sector: the sector this stock falls under (e.g. "Banks", "Auto Components") — null if not found

Also extract at the fund level:
- category: fund category (e.g. "Large & Mid Cap", "Flexi Cap", "ELSS")
- aum: Assets Under Management with units (e.g. "27,544.45 Cr") — null if not found
- expense_ratio: expense ratio (e.g. "1.54%") — null if not found
- fund_manager: fund manager name(s) as a string — null if not found

Return ONLY valid JSON. No markdown, no explanation.
Format:
{
  "category": "...",
  "aum": "...",
  "expense_ratio": "...",
  "fund_manager": "...",
  "holdings": [
    {"stock": "Infosys Ltd", "weight": "8.24%", "sector": "IT"}
  ]
}
If you cannot find any holdings data, return: {"error": "no holdings found"}"""


def clean_sarvam_md(raw_md: str) -> str:
    """Strip base64 image blobs and image description italics from Sarvam markdown output."""
    # Remove inline base64 images: ![...](data:image/...long base64...)
    clean = re.sub(r'!\[.*?\]\(data:image/[^)]{20,}\)', '', raw_md)
    # Remove italicised image descriptions Sarvam adds: *The image displays ...*
    clean = re.sub(r'\*The image (?:displays|contains|shows).*?\*\n?', '', clean, flags=re.DOTALL)
    # Collapse excessive blank lines
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    return clean.strip()


def extract_with_sarvam(pdf_path: str) -> str | None:
    try:
        print("Running Sarvam document intelligence...")
        job = sarvam_client.document_intelligence.create_job(
            language="en-IN",
            output_format="md"
        )
        job.upload_file(pdf_path)
        job.start()
        status = job.wait_until_complete()

        if status.job_state not in ["Completed", "PartiallyCompleted"]:
            print(f"Sarvam job failed: {status.job_state}")
            return None

        output_zip_path = pdf_path.replace(".pdf", "_sarvam_output.zip")
        job.download_output(output_zip_path)

        with zipfile.ZipFile(output_zip_path, "r") as z:
            md_files = sorted([f for f in z.namelist() if f.endswith(".md")])
            if not md_files:
                return None
            full_text = ""
            for md_file in md_files:
                with z.open(md_file) as f:
                    full_text += f.read().decode("utf-8") + "\n\n"

        return full_text

    except Exception as e:
        print(f"Sarvam error: {e}")
        return None


def call_gpt(text: str, label: str) -> dict:
    """Send text to GPT-4o-mini and return parsed JSON result."""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": (
                f"Fund: ICICI Prudential Large & Mid Cap Fund\n"
                f"AMC: ICICI Prudential\n\n"
                f"PDF text ({label}):\n---\n{text}\n---\n"
                f"Extract ALL holdings. Do not stop early."
            )}
        ],
        temperature=0,
        max_tokens=6000   # increased — full holdings list needs space
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def print_result(label: str, result: dict):
    print(f"\n{'='*60}")
    print(f"RESULT: {label}")
    print(f"{'='*60}")
    print(f"Category     : {result.get('category')}")
    print(f"AUM          : {result.get('aum')}")
    print(f"Expense Ratio: {result.get('expense_ratio')}")
    print(f"Fund Manager : {result.get('fund_manager')}")
    holdings = result.get("holdings", [])
    print(f"Holdings     : {len(holdings)} stocks")
    print(f"\nFirst 15 holdings:")
    for h in holdings[:15]:
        print(f"  {h['stock']:<45} {str(h.get('weight','?')):<8}  {h.get('sector') or '-'}")
    if len(holdings) > 15:
        print(f"  ... and {len(holdings) - 15} more")


# ── Download ICICI PDF and extract pages 16-17 ───────────────────────────────
print("Downloading ICICI PDF...")
url = "https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-january-2026.pdf"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=60)
doc = fitz.open(stream=resp.content, filetype="pdf")

os.makedirs("cache", exist_ok=True)
mini_pdf_path = "cache/test_icici_large_midcap.pdf"
mini_doc = fitz.open()
mini_doc.insert_pdf(doc, from_page=15, to_page=16)  # 0-indexed → pages 16-17
mini_doc.save(mini_pdf_path)
mini_doc.close()
print(f"Saved pages 16-17 to {mini_pdf_path}")

# ── TEST 1: GPT-4o-mini on raw PyMuPDF text ──────────────────────────────────
print(f"\n{'='*60}")
print("TEST 1: GPT-4o-mini on raw PyMuPDF text")
print(f"{'='*60}")

raw_text = ""
for p in [15, 16]:
    raw_text += doc[p].get_text("text") + "\n\n--- PAGE BREAK ---\n\n"

print(f"PyMuPDF raw text length: {len(raw_text)} chars")
print("\nFirst 1000 chars of raw text:")
print("-" * 40)
print(raw_text[:1000])
print("-" * 40)

gpt_result = None
try:
    gpt_result = call_gpt(raw_text[:8000], "PyMuPDF raw text")
    print_result("GPT-4o-mini (PyMuPDF)", gpt_result)
except Exception as e:
    print(f"GPT (PyMuPDF) failed: {e}")

# ── TEST 2: Sarvam → clean → GPT ─────────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 2: Sarvam → clean → GPT-4o-mini")
print(f"{'='*60}")

sarvam_result = None
sarvam_raw = extract_with_sarvam(mini_pdf_path)

if sarvam_raw:
    sarvam_clean = clean_sarvam_md(sarvam_raw)
    print(f"Sarvam raw MD length  : {len(sarvam_raw)} chars")
    print(f"Sarvam cleaned length : {len(sarvam_clean)} chars  (saved {len(sarvam_raw)-len(sarvam_clean)} chars)")
    print("\nFirst 1500 chars of cleaned MD:")
    print("-" * 40)
    print(sarvam_clean[:1500])
    print("-" * 40)

    try:
        sarvam_result = call_gpt(sarvam_clean, "Sarvam markdown")
        print_result("Sarvam + GPT-4o-mini", sarvam_result)
    except Exception as e:
        print(f"GPT (Sarvam) failed: {e}")
else:
    print("Sarvam returned no output — skipping test 2")

# ── FINAL COMPARISON ──────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("FINAL COMPARISON")
print(f"{'='*60}")
gpt_count = len(gpt_result.get("holdings", [])) if gpt_result else "error"
sarvam_count = len(sarvam_result.get("holdings", [])) if sarvam_result else "error"
print(f"GPT (PyMuPDF) holdings count : {gpt_count}")
print(f"Sarvam + GPT  holdings count : {sarvam_count}")

if isinstance(gpt_count, int) and isinstance(sarvam_count, int):
    if sarvam_count > gpt_count:
        print(f"\n✓ Sarvam extracted {sarvam_count - gpt_count} MORE holdings than PyMuPDF")
    elif gpt_count > sarvam_count:
        print(f"\n✓ PyMuPDF extracted {gpt_count - sarvam_count} MORE holdings than Sarvam")
    else:
        print("\n= Both methods extracted the same number of holdings")

# Save both outputs for inspection
if gpt_result:
    with open("cache/gpt_pymupdf_result.json", "w") as f:
        json.dump(gpt_result, f, indent=2)
    print("\nSaved: cache/gpt_pymupdf_result.json")

if sarvam_result:
    with open("cache/sarvam_gpt_result.json", "w") as f:
        json.dump(sarvam_result, f, indent=2)
    print("Saved: cache/sarvam_gpt_result.json")