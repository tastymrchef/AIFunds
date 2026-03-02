"""
build_holdings_index.py

Builds cache/holdings_index.json — the backbone of thematic fund search.
Powers: type "Zomato" → find all funds holding it.

Pipeline per AMC:
1. Skip Pattern C AMCs (random hash URLs — need manual update)
2. Download PDF
3. PyMuPDF reads first INDEX_SCAN_PAGES pages, passes combined text to GPT
4. GPT parses index → {fund_name: page_number} (handles any AMC format)
5. If no index found → skip AMC, log for manual review
6. Ollama llama3.1:8b classifies each fund name (keep/skip)
7. GPT-4o-mini extracts full holdings (stock + weight + sector) for kept funds
8. Save to cache/holdings_index.json after each AMC (resume-safe)

Run: python utils/build_holdings_index.py
"""

import json
import os
import re
import time
import requests
import fitz  # PyMuPDF
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
AMC_URLS_PATH         = "cache/amc_factsheet_urls.json"
OUTPUT_PATH           = "cache/holdings_index.json"
SKIPPED_LOG_PATH      = "cache/holdings_index_skipped.json"
OLLAMA_MODEL          = "llama3.1:8b"
OLLAMA_URL            = "http://localhost:11434/api/generate"
GPT_MODEL             = "gpt-4o-mini"
INDEX_SCAN_PAGES      = 6   # how many pages to read looking for the index
MIN_INDEX_FUNDS       = 3   # minimum funds GPT must find to confirm it's an index
PAGES_PER_FUND        = 3   # pages to extract per fund for holdings
REQUEST_TIMEOUT       = 60
DELAY_BETWEEN_AMCS    = 2

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── File I/O ──────────────────────────────────────────────────────────────────

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── PDF Download ──────────────────────────────────────────────────────────────

def download_pdf(url: str) -> bytes | None:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MutualFundResearch/1.0)"}
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code == 200 and resp.content[:4] == b"%PDF":
            return resp.content
        print(f"    X Bad response {resp.status_code} or not a PDF")
        return None
    except Exception as e:
        print(f"    X Download error: {e}")
        return None

# ── Index Page Detection (LLM-based) ─────────────────────────────────────────

INDEX_PARSE_PROMPT = """This is raw text extracted from the first few pages of an Indian mutual fund factsheet.
These pages contain a table of contents / index listing all fund schemes with their page numbers.

Your job: extract every fund/scheme name and its starting page number.

Rules:
- Only include actual mutual fund / scheme names
- Ignore: category headers, descriptions, "Economic Overview", "Annexure", "SIP Performance", "IDCW History", disclaimers
- Page number = the FIRST page where that fund's data appears
- If a range is given like "14-16", use 14
- Fund names often start with the AMC name, e.g. "ICICI Prudential Large Cap Fund"

Return ONLY a JSON object. No markdown, no explanation.
Format: {"Fund Name One": 14, "Fund Name Two": 16, "Fund Name Three": 20}

If you cannot find any fund index in this text, return: {}"""

def parse_index_with_llm(combined_text: str) -> dict:
    """
    Pass combined text from first N pages to GPT-4o-mini.
    Returns {fund_name: page_number} or {} if no index found.
    """
    try:
        resp = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "user", "content": (
                    f"{INDEX_PARSE_PROMPT}\n\n"
                    f"Factsheet text (first {INDEX_SCAN_PAGES} pages):\n---\n"
                    f"{combined_text[:8000]}\n---"
                )}
            ],
            temperature=0,
            max_tokens=2000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        # Validate: must be dict of str -> positive int
        return {k: int(v) for k, v in result.items() if isinstance(v, (int, float)) and int(v) > 0}
    except Exception as e:
        print(f"    X LLM index parsing failed: {e}")
        return {}

def find_index_page(doc: fitz.Document) -> dict:
    """
    Read first INDEX_SCAN_PAGES pages, combine text, send to GPT to parse index.
    Returns {fund_name: page_number} or {} if no index found.
    """
    pages_to_scan = min(INDEX_SCAN_PAGES, len(doc))
    combined_text = ""
    for page_num in range(pages_to_scan):
        page_text = doc[page_num].get_text("text")
        combined_text += f"\n\n--- PDF PAGE {page_num + 1} ---\n\n{page_text}"

    print(f"    -> Scanning first {pages_to_scan} pages with LLM index parser...")
    fund_page_map = parse_index_with_llm(combined_text)

    if len(fund_page_map) >= MIN_INDEX_FUNDS:
        print(f"    + Index found: {len(fund_page_map)} funds parsed")
        return fund_page_map
    else:
        print(f"    X No index found (GPT returned {len(fund_page_map)} entries, need {MIN_INDEX_FUNDS}+)")
        return {}

# ── Ollama Classification ─────────────────────────────────────────────────────

OLLAMA_SYSTEM = """You classify Indian mutual fund names. Decide if we should extract and index their holdings for a thematic search tool.

INDEX = true for:
- Active equity funds (large cap, mid cap, small cap, flexi cap, ELSS, sectoral, thematic, focused)
- Active hybrid funds
- Active debt funds with specific bond/company holdings
- International/global funds
- Commodity or thematic ETFs (gold, silver, pharma, IT sector ETFs)
- Fund of funds investing in international funds

INDEX = false for:
- Pure index trackers (Nifty 50 index fund, Sensex ETF, any broad index fund or plain index ETF)
- Overnight funds, liquid funds, ultra-short duration, money market funds
- Fixed Maturity Plans (FMP), interval funds
- Arbitrage funds
- Segregated portfolios

Return ONLY a JSON array. No markdown, no explanation, no extra text.
Format: [{"name": "fund name exactly as given", "index": true}, ...]"""

def classify_funds_ollama(fund_names: list) -> dict:
    """
    Classify fund names using Ollama. Returns {fund_name: bool}
    Falls back to True (index everything) if Ollama fails.
    """
    results = {}
    chunk_size = 25

    for i in range(0, len(fund_names), chunk_size):
        chunk = fund_names[i:i + chunk_size]
        prompt = "Classify these Indian mutual funds:\n" + "\n".join(f"- {n}" for n in chunk)

        for attempt in range(2):
            try:
                resp = requests.post(
                    OLLAMA_URL,
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": OLLAMA_SYSTEM + "\n\n" + prompt,
                        "stream": False
                    },
                    timeout=120
                )
                raw = resp.json().get("response", "").strip()
                raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
                parsed = json.loads(raw)
                for item in parsed:
                    results[item["name"]] = item.get("index", True)
                break

            except Exception as e:
                if attempt == 0:
                    print(f"      ! Ollama attempt 1 failed: {e}. Retrying...")
                    time.sleep(2)
                else:
                    print(f"      X Ollama failed. Defaulting chunk to index=True")
                    for name in chunk:
                        results[name] = True

        time.sleep(0.5)

    return results

# ── GPT-4o-mini Holdings Extraction ──────────────────────────────────────────

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

def extract_holdings_gpt(fund_name: str, pdf_text: str, amc_name: str, as_of: str) -> dict | None:
    prompt = f"""Fund: {fund_name}
AMC: {amc_name}
Factsheet month: {as_of}

Extracted PDF text:
---
{pdf_text[:6000]}
---

Extract ALL holdings and fund details. Do not stop early."""

    try:
        resp = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=6000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)

        if "error" in result:
            print(f"      X GPT: no holdings found for {fund_name}")
            return None

        return result

    except Exception as e:
        print(f"      X GPT extraction failed for {fund_name}: {e}")
        return None

def extract_pages_text(doc: fitz.Document, start_page_1indexed: int, num_pages: int = PAGES_PER_FUND) -> str:
    texts = []
    start = start_page_1indexed - 1  # convert to 0-indexed
    for p in range(start, min(start + num_pages, len(doc))):
        texts.append(doc[p].get_text("text"))
    return "\n\n--- PAGE BREAK ---\n\n".join(texts)

# ── Main Pipeline ─────────────────────────────────────────────────────────────

def process_amc(amc_name: str, amc_data: dict, existing_index: dict, skipped_log: dict) -> dict:
    url = amc_data["url"]
    as_of = amc_data.get("month", "Unknown")
    new_entries = {}

    print(f"\n{'='*60}")
    print(f"  AMC: {amc_name}")
    print(f"  Month: {as_of}")

    # Download PDF
    print(f"  -> Downloading PDF...")
    pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        skipped_log[amc_name] = {"reason": "PDF download failed", "url": url}
        return new_entries

    # Open with PyMuPDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        print(f"  -> PDF opened: {len(doc)} pages")
    except Exception as e:
        print(f"  X Could not open PDF: {e}")
        skipped_log[amc_name] = {"reason": f"PyMuPDF error: {e}", "url": url}
        return new_entries

    # Find index (LLM-based — handles any AMC format, multi-page indexes)
    fund_page_map = find_index_page(doc)
    if not fund_page_map:
        print(f"  X No index found — skipping AMC")
        skipped_log[amc_name] = {"reason": "No index page found", "url": url}
        doc.close()
        return new_entries

    fund_names = list(fund_page_map.keys())
    print(f"  -> {len(fund_names)} funds in index")

    # Ollama classification
    print(f"  -> Classifying with Ollama...")
    classification = classify_funds_ollama(fund_names)
    to_index = [n for n, v in classification.items() if v]
    skipped_count = len(fund_names) - len(to_index)
    print(f"  -> Indexing {len(to_index)} funds, skipping {skipped_count} (index ETFs, liquid etc.)")

    # GPT extraction for each qualifying fund
    for fund_name in to_index:
        if fund_name in existing_index:
            print(f"    >> Already indexed: {fund_name}")
            continue

        page_num = fund_page_map.get(fund_name)
        if not page_num:
            print(f"    X No page number for: {fund_name}")
            continue

        print(f"    -> {fund_name} (PDF page {page_num})")
        pdf_text = extract_pages_text(doc, page_num, PAGES_PER_FUND)

        if not pdf_text.strip():
            print(f"    X Empty text for: {fund_name}")
            continue

        holdings_data = extract_holdings_gpt(fund_name, pdf_text, amc_name, as_of)
        if holdings_data:
            new_entries[fund_name] = {
                "amc": amc_name,
                "as_of": as_of,
                **holdings_data
            }
            count = len(holdings_data.get("holdings", []))
            print(f"    + {count} holdings extracted")

        time.sleep(0.3)

    doc.close()
    return new_entries


def main():
    print("\nHoldings Index Builder")
    print("=" * 60)

    amc_urls = load_json(AMC_URLS_PATH)
    if not amc_urls:
        print(f"X Could not load {AMC_URLS_PATH}")
        return

    # Filter out Pattern C
    processable = {k: v for k, v in amc_urls.items() if v.get("pattern") != "C"}
    pattern_c = [k for k, v in amc_urls.items() if v.get("pattern") == "C"]

    print(f"Total AMCs in database : {len(amc_urls)}")
    print(f"Processing             : {len(processable)}")
    print(f"Skipping (Pattern C)   : {len(pattern_c)}")
    print(f"Pattern C AMCs         : {pattern_c}")

    # Load existing (resume safety)
    holdings_index = load_json(OUTPUT_PATH)
    skipped_log = load_json(SKIPPED_LOG_PATH)
    already_done = {v.get("amc") for v in holdings_index.values()}

    print(f"Already indexed        : {len(already_done)} AMCs")
    print("=" * 60)

    for amc_name, amc_data in list(processable.items())[:3]:
        if amc_name in already_done:
            print(f"\n  >> Already done: {amc_name}")
            continue

        new_entries = process_amc(amc_name, amc_data, holdings_index, skipped_log)
        holdings_index.update(new_entries)

        save_json(OUTPUT_PATH, holdings_index)
        save_json(SKIPPED_LOG_PATH, skipped_log)
        print(f"  Saved. Total indexed: {len(holdings_index)} funds")

        time.sleep(DELAY_BETWEEN_AMCS)

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print(f"   Funds indexed : {len(holdings_index)}")
    print(f"   AMCs skipped  : {len(skipped_log)}")
    if skipped_log:
        print("\nNeeds manual review:")
        for amc, info in skipped_log.items():
            print(f"   - {amc}: {info['reason']}")


if __name__ == "__main__":
    main()