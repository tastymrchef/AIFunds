"""
test_index_comparison.py
Compares PyMuPDF vs Sarvam on ICICI index page (pages 2-4)
Just asks GPT: list all fund names you see under Equity and Debt.
Run from project root: python test_index_comparison.py
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

INDEX_SYSTEM = """You are reading the index/table of contents page of an Indian mutual fund factsheet.

Your job is simple: list all the mutual fund names you can see, grouped by their category.

Group them into:
- equity: all equity fund names (Large Cap, Mid Cap, Flexi Cap, ELSS, Sector funds, etc.)
- debt: all debt fund names (Liquid, Short Duration, Credit Risk, Gilt, etc.)
- hybrid: hybrid/balanced fund names
- other: anything else (ETFs, Index funds, FoFs, international, etc.)

Rules:
- Only list actual fund names, not categories/headers
- Do not invent or guess — only include names you can clearly read
- If a category has no funds, return an empty list for it

Return ONLY valid JSON. No markdown, no explanation.
Format:
{
  "equity": ["Fund Name 1", "Fund Name 2"],
  "debt": ["Fund Name A", "Fund Name B"],
  "hybrid": ["Fund Name X"],
  "other": ["Fund Name Y"]
}"""


def clean_sarvam_md(raw_md: str) -> str:
    """Strip base64 image blobs and image description italics from Sarvam markdown."""
    clean = re.sub(r'!\[.*?\]\(data:image/[^)]{20,}\)', '', raw_md)
    clean = re.sub(r'\*The image (?:displays|contains|shows).*?\*\n?', '', clean, flags=re.DOTALL)
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
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": INDEX_SYSTEM},
            {"role": "user", "content": (
                f"AMC: ICICI Prudential\n\n"
                f"Index page text ({label}):\n---\n{text}\n---\n"
                f"List all fund names you can see, grouped by equity/debt/hybrid/other."
            )}
        ],
        temperature=0,
        max_tokens=3000
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


def print_result(label: str, result: dict):
    print(f"\n{'='*60}")
    print(f"RESULT: {label}")
    print(f"{'='*60}")
    total = 0
    for category in ["equity", "debt", "hybrid", "other"]:
        funds = result.get(category, [])
        total += len(funds)
        print(f"\n{category.upper()} ({len(funds)} funds):")
        for f in funds:
            print(f"  - {f}")
    print(f"\nTOTAL: {total} funds found")


# ── Download ICICI PDF and extract index pages 2-4 ───────────────────────────
print("Downloading ICICI PDF...")
url = "https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-january-2026.pdf"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=60)
doc = fitz.open(stream=resp.content, filetype="pdf")

os.makedirs("cache", exist_ok=True)

# Index pages: 2-4 (0-indexed: 1-3)
INDEX_PAGES = [1, 2, 3]

mini_pdf_path = "cache/test_icici_index.pdf"
mini_doc = fitz.open()
mini_doc.insert_pdf(doc, from_page=INDEX_PAGES[0], to_page=INDEX_PAGES[-1])
mini_doc.save(mini_pdf_path)
mini_doc.close()
print(f"Saved index pages {[p+1 for p in INDEX_PAGES]} to {mini_pdf_path}")

# ── TEST 1: GPT on raw PyMuPDF text ──────────────────────────────────────────
print(f"\n{'='*60}")
print("TEST 1: GPT-4o-mini on raw PyMuPDF text")
print(f"{'='*60}")

raw_text = ""
for p in INDEX_PAGES:
    page_text = doc[p].get_text("text")
    raw_text += f"\n\n--- PAGE {p+1} ---\n\n{page_text}"

print(f"PyMuPDF raw text length: {len(raw_text)} chars")
print("\nRaw text (first 2000 chars):")
print("-" * 40)
print(raw_text[:2000])
print("-" * 40)

gpt_result = None
try:
    gpt_result = call_gpt(raw_text, "PyMuPDF raw text")
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
    print("\nCleaned MD (first 2000 chars):")
    print("-" * 40)
    print(sarvam_clean[:2000])
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

gpt_total = sum(len(gpt_result.get(c, [])) for c in ["equity","debt","hybrid","other"]) if gpt_result else "error"
sarvam_total = sum(len(sarvam_result.get(c, [])) for c in ["equity","debt","hybrid","other"]) if sarvam_result else "error"

print(f"GPT (PyMuPDF) total funds found : {gpt_total}")
print(f"Sarvam + GPT  total funds found : {sarvam_total}")

if isinstance(gpt_total, int) and isinstance(sarvam_total, int):
    if sarvam_total > gpt_total:
        print(f"\n✓ Sarvam found {sarvam_total - gpt_total} MORE funds than PyMuPDF")
    elif gpt_total > sarvam_total:
        print(f"\n✓ PyMuPDF found {gpt_total - sarvam_total} MORE funds than Sarvam")
    else:
        print(f"\n= Both methods found the same number of funds ({gpt_total})")

    # Show funds found by one but not the other
    if gpt_result and sarvam_result:
        all_cats = ["equity", "debt", "hybrid", "other"]
        gpt_funds = set(f.lower() for c in all_cats for f in gpt_result.get(c, []))
        sarvam_funds = set(f.lower() for c in all_cats for f in sarvam_result.get(c, []))

        only_in_gpt = gpt_funds - sarvam_funds
        only_in_sarvam = sarvam_funds - gpt_funds

        if only_in_gpt:
            print(f"\nFound by PyMuPDF only ({len(only_in_gpt)}):")
            for f in sorted(only_in_gpt):
                print(f"  - {f}")

        if only_in_sarvam:
            print(f"\nFound by Sarvam only ({len(only_in_sarvam)}):")
            for f in sorted(only_in_sarvam):
                print(f"  - {f}")

# Save results
if gpt_result:
    with open("cache/index_gpt_pymupdf_result.json", "w") as f:
        json.dump(gpt_result, f, indent=2)
    print("\nSaved: cache/index_gpt_pymupdf_result.json")

if sarvam_result:
    with open("cache/index_sarvam_gpt_result.json", "w") as f:
        json.dump(sarvam_result, f, indent=2)
    print("Saved: cache/index_sarvam_gpt_result.json")