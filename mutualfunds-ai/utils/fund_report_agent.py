import os
import json
import fitz  # PyMuPDF
import requests
import tempfile
import re
import zipfile
from datetime import datetime
from dotenv import load_dotenv
import openai
from sarvamai import SarvamAI

load_dotenv()

openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sarvam_client = SarvamAI(api_subscription_key=os.getenv("SARVAM_API_KEY"))

CACHE_DIR = "cache/factsheets"
QUALITY_THRESHOLD = 70

AMC_FACTSHEET_URLS = {
    "ppfas": "https://amc.ppfas.com/downloads/factsheet/2026/ppfas-mf-factsheet-for-January-2026.pdf",
}

# ── CACHE ──────────────────────────────────────────────────────────────────

def get_cache_path(scheme_code):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return f"{CACHE_DIR}/{scheme_code}.json"

def is_cache_valid(cache_path):
    if not os.path.exists(cache_path):
        return False
    try:
        with open(cache_path, "r") as f:
            cache = json.load(f)
        cached_date = datetime.strptime(cache["cached_at"], "%Y-%m-%d")
        return (datetime.today() - cached_date).days < 30
    except Exception:
        return False

def save_to_cache(scheme_code, scheme_name, factsheet_url, 
                  fund_page, structured_data, engine, quality_score, reasoning):
    cache = {
        "cached_at": datetime.today().strftime("%Y-%m-%d"),
        "scheme_code": scheme_code,
        "scheme_name": scheme_name,
        "factsheet_url": factsheet_url,
        "fund_page": fund_page,
        "extraction_engine": engine,
        "quality_score": quality_score,
        "quality_reasoning": reasoning,
        "data": structured_data
    }
    with open(get_cache_path(scheme_code), "w") as f:
        json.dump(cache, f, indent=2)
    print(f"Cached using {engine} (quality score: {quality_score})")

# ── STEP 1: FIND FACTSHEET URL ─────────────────────────────────────────────

def find_factsheet_url(fund_house, scheme_name):
    # Check known URLs first
    for key, url in AMC_FACTSHEET_URLS.items():
        if key.lower() in fund_house.lower():
            print(f"Using known URL for {key}")
            return url
    
    # Fall back to web search
    print("Searching for factsheet URL...")
    response = openai_client.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[{
            "role": "user",
            "content": f"Find the direct PDF download URL for the latest monthly factsheet of {scheme_name} from {fund_house} India. Return only the URL."
        }]
    )
    content = response.choices[0].message.content.strip()
    urls = re.findall(r'https?://[^\s]+\.pdf', content)
    return urls[0] if urls else None

# ── STEP 2: DOWNLOAD PDF ───────────────────────────────────────────────────

def download_pdf(url):
    try:
        print(f"Downloading PDF from {url}...")
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"Download failed with status {response.status_code}")
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(response.content)
        tmp.close()
        print("PDF downloaded successfully")
        return tmp.name
    except Exception as e:
        print(f"Download error: {e}")
        return None

# ── STEP 3A: PYMUPDF EXTRACTION ────────────────────────────────────────────

def extract_with_pymupdf(pdf_path, scheme_name):
    try:
        doc = fitz.open(pdf_path)
        print(f"PDF has {len(doc)} pages")
        
        # Read first 2 pages for index
        index_text = doc[0].get_text() + (doc[1].get_text() if len(doc) > 1 else "")
        
        # Find fund page from index
        keywords = [w for w in scheme_name.split()
                   if len(w) > 4
                   and w.lower() not in ["fund", "plan", "growth", "regular", 
                                          "direct", "formerly", "known"]]
        
        lines = index_text.split('\n')
        fund_page = None
        
        for i, line in enumerate(lines):
            if any(kw.lower() in line.lower() for kw in keywords):
                context = ' '.join(lines[max(0, i-2):i+3])
                numbers = re.findall(r'\b(\d{1,3})\b', context)
                if numbers:
                    fund_page = int(numbers[-1])
                    print(f"Found fund on page {fund_page}")
                    break
        
        if not fund_page:
            print("Could not find fund page in index — using full document")
            fund_text = ""
            for page in doc:
                fund_text += page.get_text() + "\n\n"
            return None, fund_text[:15000]
        
        # Extract 3 pages from fund page
        start_idx = fund_page - 1
        end_idx = min(start_idx + 3, len(doc))
        
        fund_text = ""
        for i in range(start_idx, end_idx):
            fund_text += doc[i].get_text() + "\n\n"
        
        return fund_page, fund_text
    
    except Exception as e:
        print(f"PyMuPDF error: {e}")
        return None, None

# ── STEP 3B: SARVAM EXTRACTION (FALLBACK) ─────────────────────────────────

def extract_with_sarvam(pdf_path):
    try:
        print("Falling back to Sarvam Vision...")
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
        
        print("Sarvam extraction complete")
        return full_text
    
    except Exception as e:
        print(f"Sarvam error: {e}")
        return None

# ── STEP 4: LLM QUALITY JUDGE ─────────────────────────────────────────────

def assess_quality(fund_text, scheme_name):
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a quality assessor for financial document extraction. Always respond in valid JSON."
                },
                {
                    "role": "user",
                    "content": f"""Rate the quality of this extracted text from a mutual fund factsheet for {scheme_name}.

Score from 0 to 100 based on:
- Clear stock holdings with percentages present? (30 points)
- Sector allocation visible? (25 points)
- Fund manager names present? (20 points)
- Text is readable and structured? (25 points)

Extracted text:
{fund_text[:3000]}

Respond in this exact JSON format only, no other text:
{{
    "score": <number 0-100>,
    "reasoning": "<one sentence>",
    "has_holdings": <true or false>,
    "has_sectors": <true or false>,
    "has_managers": <true or false>
}}"""
                }
            ]
        )
        
        content = response.choices[0].message.content.strip()
        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)
        print(f"Quality score: {result['score']}/100 — {result['reasoning']}")
        return result
    
    except Exception as e:
        print(f"Quality assessment error: {e}")
        return {"score": 0, "reasoning": "Assessment failed", 
                "has_holdings": False, "has_sectors": False, "has_managers": False}

# ── STEP 5: STRUCTURED DATA EXTRACTION ────────────────────────────────────

def extract_structured_data(fund_text, scheme_name):
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a financial data extractor. Extract information accurately. Never make up data."
            },
            {
                "role": "user",
                "content": f"""Extract the following from this mutual fund factsheet for {scheme_name}.
The factsheet may contain multiple funds — focus ONLY on {scheme_name}.

1. Top 5 holdings with percentage allocation (not 10)
2. Sector allocation with percentages
3. Fund manager names and experience
4. AUM and expense ratio
5. Investment objective
6. Any fund manager commentary or market outlook

Factsheet content:
{fund_text[:15000]}

Return under these exact headers:
TOP HOLDINGS
SECTOR ALLOCATION
FUND MANAGERS
AUM AND EXPENSE RATIO
INVESTMENT OBJECTIVE
MARKET COMMENTARY

Be specific with numbers. Write Not available if a section is missing."""
            }
        ]
    )
    return response.choices[0].message.content

# ── MAIN ORCHESTRATOR ──────────────────────────────────────────────────────

def get_fund_report(scheme_code, fund_house, scheme_name):
    cache_path = get_cache_path(scheme_code)
    
    # Serve from cache if valid
    if is_cache_valid(cache_path):
        print(f"Serving from cache: {scheme_name}")
        with open(cache_path, "r") as f:
            return json.load(f)["data"]
    
    print(f"\nFetching fresh report for: {scheme_name}")
    print("=" * 60)
    
    # Step 1 — Find URL
    factsheet_url = find_factsheet_url(fund_house, scheme_name)
    if not factsheet_url:
        print("Could not find factsheet URL")
        return None
    
    # Step 2 — Download PDF
    pdf_path = download_pdf(factsheet_url)
    if not pdf_path:
        return None
    
    # Step 3A — Try PyMuPDF first
    fund_page, fund_text = extract_with_pymupdf(pdf_path, scheme_name)
    engine = "pymupdf"
    
    # Step 4 — LLM judges quality
    if fund_text:
        quality = assess_quality(fund_text, scheme_name)
        quality_score = quality["score"]
        quality_reasoning = quality["reasoning"]
    else:
        quality_score = 0
        quality_reasoning = "PyMuPDF extraction failed"
    
    # Step 3B — Fall back to Sarvam if quality is poor
    if quality_score < QUALITY_THRESHOLD:
        print(f"Quality too low ({quality_score}). Trying Sarvam...")
        sarvam_text = extract_with_sarvam(pdf_path)
        
        if sarvam_text:
            sarvam_quality = assess_quality(sarvam_text, scheme_name)
            
            # Use Sarvam only if it's actually better
            if sarvam_quality["score"] > quality_score:
                fund_text = sarvam_text
                engine = "sarvam"
                quality_score = sarvam_quality["score"]
                quality_reasoning = sarvam_quality["reasoning"]
                print(f"Sarvam quality: {quality_score}/100 — using Sarvam output")
            else:
                print(f"Sarvam not better. Keeping PyMuPDF output.")
    
    if not fund_text:
        print("Both extraction methods failed")
        return None
    
    # Step 5 — Extract structured data
    print("Extracting structured data with OpenAI...")
    structured_data = extract_structured_data(fund_text, scheme_name)
    
    # Save to cache
    save_to_cache(
        scheme_code, scheme_name, factsheet_url,
        fund_page, structured_data, engine,
        quality_score, quality_reasoning
    )
    
    return structured_data

# ── TEST ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = get_fund_report(
        scheme_code="122640",
        fund_house="PPFAS Mutual Fund",
        scheme_name="Parag Parikh Flexi Cap Fund - Regular Plan - Growth"
    )
    if result:
        print("\n=== EXTRACTED DATA ===")
        print(result)
    else:
        print("Could not fetch report")
