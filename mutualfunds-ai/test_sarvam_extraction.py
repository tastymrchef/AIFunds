"""
test_sarvam.py
Test Sarvam html vs md output on ICICI Large & Mid Cap page 16
Run: python test_sarvam.py
"""

import fitz
import requests
import zipfile
import os
from sarvamai import SarvamAI
from dotenv import load_dotenv

load_dotenv()
sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

# Download and save pages 16-17 as mini PDF
print("Downloading ICICI PDF...")
url = "https://digitalfactsheet.icicipruamc.com/fact/pdf/fund-factsheet-for-january-2026.pdf"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=60)
doc = fitz.open(stream=resp.content, filetype="pdf")

os.makedirs("cache", exist_ok=True)
mini_pdf_path = "cache/test_icici_large_midcap.pdf"
mini_doc = fitz.open()
mini_doc.insert_pdf(doc, from_page=15, to_page=16)
mini_doc.save(mini_pdf_path)
mini_doc.close()
print(f"Saved pages 16-17 to {mini_pdf_path}")

def run_sarvam(output_format: str) -> str:
    print(f"\nRunning Sarvam with output_format='{output_format}'...")
    job = sarvam_client.document_intelligence.create_job(
        language="en-IN",
        output_format=output_format
    )
    job.upload_file(mini_pdf_path)
    job.start()
    status = job.wait_until_complete()
    print(f"Status: {status.job_state}")

    zip_path = f"cache/test_sarvam_{output_format}.zip"
    job.download_output(zip_path)

    full_text = ""
    with zipfile.ZipFile(zip_path, "r") as z:
        files = sorted([f for f in z.namelist()])
        print(f"Files in zip: {files}")
        for fname in files:
            with z.open(fname) as f:
                full_text += f.read().decode("utf-8") + "\n\n"

    return full_text

# Test markdown
md_output = run_sarvam("md")
print("\n" + "="*60)
print("MARKDOWN OUTPUT:")
print("="*60)
print(md_output)

# Test html
html_output = run_sarvam("html")
print("\n" + "="*60)
print("HTML OUTPUT:")
print("="*60)
print(html_output)

# Add this at the end of test_sarvam.py

with open("cache/sarvam_md_output.txt", "w", encoding="utf-8") as f:
    f.write(md_output)

with open("cache/sarvam_html_output.txt", "w", encoding="utf-8") as f:
    f.write(html_output)

print("Saved to cache/sarvam_md_output.txt and cache/sarvam_html_output.txt")