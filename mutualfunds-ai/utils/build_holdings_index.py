"""
build_holdings_index.py

Builds cache/holdings_index.json — the backbone of thematic fund search.
Powers: type "Zomato" → find all funds holding it.

Pipeline per AMC:
1. Skip Pattern C AMCs (random hash URLs — need manual update)
2. Download PDF
3. PyMuPDF reads first INDEX_SCAN_PAGES pages, passes combined text to GPT
4. GPT parses index → {fund_name: {"page": N, "broad_category": "equity"|"debt"|...}}
   (handles any AMC format; captures category from the PDF index itself)
5. If no index found → skip AMC, log for manual review
6. Classification — three-layer filter (zero → cheap → expensive):
     a. Keyword pre-filter: obvious skips (liquid, FMP, Nifty index, arbitrage…) → no API cost
     b. broad_category pre-filter: GPT already labelled "liquid"/"debt"/"index" → skip immediately
     c. Ollama llama3.1:8b: only handles genuinely ambiguous cases (hybrid, thematic, etc.)
7. GPT-4o-mini extracts full holdings (stock + weight + sector) for kept funds
8. Save to cache/holdings_index.json after each AMC (resume-safe)

Run: python utils/build_holdings_index.py
"""

import argparse
import json
import os
import re
import sys
import time
import requests
import fitz  # PyMuPDF
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
AMC_URLS_PATH         = "cache/amc_factsheet_urls.json"
OUTPUT_PATH           = "cache/holdings_index.json"
SKIPPED_LOG_PATH      = "cache/holdings_index_skipped.json"
AUDIT_LOG_PATH        = "cache/holdings_index_audit.json"   # per-AMC run audit
OLLAMA_MODEL          = "llama3.1:8b"
OLLAMA_URL            = "http://localhost:11434/api/generate"
GPT_MODEL             = "gpt-4o-mini"
INDEX_SCAN_PAGES      = 6   # how many pages to read looking for the index
MIN_INDEX_FUNDS       = 3   # minimum funds GPT must find to confirm it's an index
PAGES_PER_FUND        = 3   # pages to extract per fund for holdings
REQUEST_TIMEOUT       = 60
DELAY_BETWEEN_AMCS    = 2

# Warn if any single step takes longer than this many seconds
SLOW_STEP_WARN_SECS   = 30

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Logging helpers ───────────────────────────────────────────────────────────

def ts() -> str:
    """Current time as [HH:MM:SS] prefix for every print line."""
    return datetime.now().strftime("[%H:%M:%S]")

def log(msg: str, indent: int = 0) -> None:
    """Print with timestamp. Flush immediately so nothing buffers during long waits."""
    print(f"{ts()} {'  ' * indent}{msg}", flush=True)

def log_step(label: str, indent: int = 1):
    """
    Context manager: prints '-> <label>...' on entry and '   done (Xs)' on exit.
    Warns if the step took longer than SLOW_STEP_WARN_SECS.

    Usage:
        with log_step("Downloading PDF"):
            pdf_bytes = download_pdf(url)
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        log(f"-> {label}...", indent=indent)
        t0 = time.time()
        yield
        elapsed = time.time() - t0
        if elapsed >= SLOW_STEP_WARN_SECS:
            log(f"   ⚠  {label} took {elapsed:.1f}s  (slow — still alive)", indent=indent)
        else:
            log(f"   done ({elapsed:.1f}s)", indent=indent)

    return _ctx()

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
The index is often grouped under category headers like "Equity Funds", "Debt Funds", "Liquid Funds" etc.

Your job: extract every fund/scheme name, its starting page number, AND its broad category.

Rules:
- Only include actual mutual fund / scheme names
- Ignore: descriptions, "Economic Overview", "Annexure", "SIP Performance", "IDCW History", disclaimers
- Page number = the FIRST page where that fund's data appears (if a range like "14-16", use 14)
- broad_category = the section header the fund falls under in the index.
  Use EXACTLY one of these values:
    "equity"   — large/mid/small/flexi/ELSS/sectoral/thematic/focused/international/global equity
    "hybrid"   — balanced, aggressive hybrid, balanced advantage, multi-asset, arbitrage (hybrid type)
    "debt"     — short/medium/long duration, credit risk, corporate bond, gilt, dynamic bond
    "liquid"   — liquid, overnight, money market, ultra-short, low duration
    "index"    — pure index trackers, ETFs tracking broad market indices (Nifty 50 ETF, Sensex ETF)
    "fof"      — fund of funds
    "other"    — anything that doesn't fit the above
  IMPORTANT — how to assign broad_category:
    1. If the fund sits under a clearly labelled section header in the index (e.g. "Equity Funds",
       "Debt Schemes", "Liquid / Overnight"), use that section header to set the category.
    2. If there is NO section header but the fund name itself makes the category unambiguous
       (e.g. "XYZ Liquid Fund", "XYZ Nifty 50 ETF", "XYZ Overnight Fund"), use the name.
    3. If neither the section header NOR the fund name clearly indicates the category,
       do NOT guess — use "other". It is better to say "other" than to invent a category.

Return ONLY a JSON object. No markdown, no explanation.
Format:
{
  "Fund Name One": {"page": 14, "broad_category": "equity"},
  "Fund Name Two": {"page": 42, "broad_category": "debt"},
  "Fund Name Three": {"page": 55, "broad_category": "liquid"}
}

If you cannot find any fund index in this text, return: {}"""

def parse_index_with_llm(combined_text: str, min_funds: int = MIN_INDEX_FUNDS, max_retries: int = 3) -> dict:
    """
    Pass combined text from first N pages to GPT-4o-mini.
    Returns {fund_name: {"page": int, "broad_category": str}} or {} if no index found.

    Improvements:
    - Uses 12000 chars (was 8000) to reduce truncation misses
    - GPT now returns broad_category alongside page number (captured from PDF section headers)
    - Enforces JSON output via response_format
    - Retries up to max_retries times if result < min_funds (LLM non-determinism guard)
    - Uses dynamic min_funds threshold (set to expected_fund_count on subsequent runs)
    """
    VALID_CATEGORIES = {"equity", "hybrid", "debt", "liquid", "index", "fof", "other"}

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=GPT_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "user", "content": (
                        f"{INDEX_PARSE_PROMPT}\n\n"
                        f"Factsheet text (first {INDEX_SCAN_PAGES} pages):\n---\n"
                        f"{combined_text[:12000]}\n---"
                    )}
                ],
                temperature=0,
                max_tokens=2000
            )
            raw = resp.choices[0].message.content.strip()
            result = json.loads(raw)

            parsed = {}
            for k, v in result.items():
                # Support both new format {"page": N, "broad_category": "..."} and legacy flat {name: N}
                if isinstance(v, dict):
                    page = v.get("page") or v.get("page_number")
                    cat  = v.get("broad_category", "other").lower().strip()
                    if not cat or cat not in VALID_CATEGORIES:
                        cat = "other"
                elif isinstance(v, (int, float)):
                    # Legacy fallback — GPT returned old flat format
                    page = v
                    cat  = "other"
                else:
                    continue

                if page and int(page) > 0:
                    parsed[k] = {"page": int(page), "broad_category": cat}

            if len(parsed) >= min_funds:
                if attempt > 1:
                    print(f"    + Index parsed on attempt {attempt}: {len(parsed)} funds")
                return parsed

            print(f"    ! Attempt {attempt}/{max_retries}: GPT returned {len(parsed)} entries (need {min_funds}+). Retrying...")
            time.sleep(1)

        except Exception as e:
            print(f"    ! Attempt {attempt}/{max_retries}: LLM index parsing failed: {e}")
            time.sleep(1)

    print(f"    X Index parsing failed after {max_retries} attempts")
    return {}

def find_index_page(doc: fitz.Document, amc_name: str = "", amc_data: dict = None, amc_urls: dict = None) -> dict:
    """
    Read first INDEX_SCAN_PAGES pages, combine text, send to GPT to parse index.
    Returns {fund_name: page_number} or {} if no index found.

    Self-improving memory:
    - If amc_data has 'expected_fund_count' from a previous successful run, use it
      as the minimum threshold so the system knows if this month's parse is incomplete.
    - After a successful parse, writes 'expected_fund_count' back to amc_urls so
      future runs benefit from the learned count (gets smarter each month).
    """
    pages_to_scan = min(INDEX_SCAN_PAGES, len(doc))
    combined_text = ""
    for page_num in range(pages_to_scan):
        page_text = doc[page_num].get_text("text")
        combined_text += f"\n\n--- PDF PAGE {page_num + 1} ---\n\n{page_text}"

    # Use historical fund count as the minimum threshold if we have it
    expected = (amc_data or {}).get("expected_fund_count", MIN_INDEX_FUNDS)
    if expected > MIN_INDEX_FUNDS:
        print(f"    -> Scanning first {pages_to_scan} pages (expecting ~{expected} funds from prior run)...")
    else:
        print(f"    -> Scanning first {pages_to_scan} pages with LLM index parser...")

    fund_page_map = parse_index_with_llm(combined_text, min_funds=expected)

    if fund_page_map:
        count = len(fund_page_map)
        print(f"    + Index found: {count} funds parsed")

        # ── Memory: write expected_fund_count back for future runs ──
        if amc_urls is not None and amc_name:
            prev = (amc_data or {}).get("expected_fund_count", 0)
            if count != prev:
                amc_urls[amc_name]["expected_fund_count"] = count
                save_json(AMC_URLS_PATH, amc_urls)
                if prev:
                    print(f"    ~ Updated expected_fund_count: {prev} → {count}")
                else:
                    print(f"    ~ Stored expected_fund_count = {count} for future runs")

        return fund_page_map
    else:
        print(f"    X No index found — all retries exhausted")
        return {}

# ── Keyword Pre-filter (Layer 1 — zero API cost) ─────────────────────────────

# Any fund name containing one of these substrings (case-insensitive) is skipped
# immediately — no Ollama call, no GPT call, no cost.
SKIP_KEYWORDS = [
    # Liquid / cash management
    "liquid", "overnight", "money market", "ultra short", "ultra-short",
    "low duration",
    # Passive / index trackers
    "nifty 50 index", "nifty50 index", "sensex index", "nifty next 50 index",
    "nifty 100 index", "nifty midcap 150 index", "bse 500 index",
    "index fund",            # " etf" with leading space avoids "thematic ETF" hits
    # Fixed / closed-ended
    "fmp", "fixed maturity", "interval fund", "capital protection",
    # Pure arbitrage
    "arbitrage fund",
    # Segregated
    "segregated portfolio",
]

# broad_category values from GPT index parse that are always skipped
SKIP_CATEGORIES = {"liquid", "index"}

# broad_category values that are always indexed (skip Ollama entirely)
INDEX_CATEGORIES = {"equity", "fof"}

def keyword_should_skip(fund_name: str) -> bool:
    """Return True if the fund name matches any of the SKIP_KEYWORDS."""
    name_lower = fund_name.lower()
    return any(kw in name_lower for kw in SKIP_KEYWORDS)

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
- Pure index trackers (Nifty 50 index fund, Sensex ETF, any broad market index ETF)
- Overnight funds, liquid funds, ultra-short duration, money market funds
- Fixed Maturity Plans (FMP), interval funds
- Arbitrage funds
- Segregated portfolios

Return ONLY a JSON array. No markdown, no explanation, no extra text.
Format: [{"name": "fund name exactly as given", "index": true}, ...]"""

def classify_funds(fund_page_map: dict) -> dict:
    """
    Three-layer classification. Returns {fund_name: bool} — True = index this fund.

    Layer 1 — Keyword pre-filter (free):
        Fund name contains obvious skip words → False immediately.

    Layer 2 — broad_category from GPT index parse (free):
        "liquid" or "index" category → False immediately.
        "equity" or "fof" category   → True immediately.

    Layer 3 — Ollama (local LLM, only for genuinely ambiguous cases):
        "hybrid", "debt", "other" categories → ask Ollama.
    """
    results       = {}
    keyword_skip  = []
    category_skip = []
    category_keep = []
    need_ollama   = []

    for fund_name, info in fund_page_map.items():
        cat = info.get("broad_category", "other")

        # Layer 1: keyword
        if keyword_should_skip(fund_name):
            results[fund_name] = False
            keyword_skip.append(fund_name)
            continue

        # Layer 2: category from GPT index parse
        if cat in SKIP_CATEGORIES:
            results[fund_name] = False
            category_skip.append(fund_name)
            continue
        if cat in INDEX_CATEGORIES:
            results[fund_name] = True
            category_keep.append(fund_name)
            continue

        # Layer 3: ambiguous (hybrid, debt, other) — send to Ollama
        need_ollama.append(fund_name)

    if keyword_skip:
        print(f"    >> Keyword pre-filter skipped {len(keyword_skip)}: {keyword_skip}")
    if category_skip:
        print(f"    >> Category pre-filter skipped {len(category_skip)} ({', '.join(set(fund_page_map[n]['broad_category'] for n in category_skip))}): {category_skip}")
    if category_keep:
        print(f"    >> Category pre-filter kept {len(category_keep)} (equity/fof) — no Ollama needed")

    # Send only ambiguous funds to Ollama
    if need_ollama:
        print(f"    -> Sending {len(need_ollama)} ambiguous funds to Ollama ({', '.join(set(fund_page_map[n]['broad_category'] for n in need_ollama))})...")
        ollama_results = _classify_with_ollama(need_ollama)
        results.update(ollama_results)
    else:
        print(f"    >> No Ollama calls needed — all funds classified by keyword/category filters")

    return results


def _classify_with_ollama(fund_names: list) -> dict:
    """Internal: send fund names to Ollama. Returns {fund_name: bool}."""
    results = {}
    chunk_size = 10

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
                    timeout=180
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

def process_amc(amc_name: str, amc_data: dict, existing_index: dict, skipped_log: dict, amc_urls: dict) -> tuple[dict, dict]:
    """
    Returns (new_entries, audit_record).

    audit_record keys:
      found_in_index   — all fund names GPT found in the PDF index
      found_count      — len(found_in_index)
      indexed          — funds whose holdings were actually extracted
      indexed_count    — len(indexed)
      skipped          — {fund_name: reason} for every fund NOT extracted
      skipped_count    — len(skipped)
    """
    url = amc_data["url"]
    as_of = amc_data.get("month", "Unknown")
    new_entries = {}

    # audit scaffold — filled in as we go
    audit: dict = {
        "found_in_index": [],
        "found_count": 0,
        "indexed": [],
        "indexed_count": 0,
        "skipped": {},
        "skipped_count": 0,
        "url": url,
        "as_of": as_of,
    }

    print(f"\n{'='*60}")
    log(f"AMC: {amc_name}  |  Month: {as_of}", indent=0)

    # Download PDF
    with log_step("Downloading PDF"):
        pdf_bytes = download_pdf(url)
    if not pdf_bytes:
        reason = "PDF download failed"
        skipped_log[amc_name] = {"reason": reason, "url": url}
        audit["skipped"]["__amc__"] = reason
        return new_entries, audit

    # Open with PyMuPDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        log(f"PDF opened: {len(doc)} pages", indent=1)
    except Exception as e:
        reason = f"PyMuPDF error: {e}"
        log(f"X Could not open PDF: {e}", indent=1)
        skipped_log[amc_name] = {"reason": reason, "url": url}
        audit["skipped"]["__amc__"] = reason
        return new_entries, audit

    # Find index (LLM-based — handles any AMC format, multi-page indexes)
    with log_step("GPT index parse"):
        fund_page_map = find_index_page(doc, amc_name=amc_name, amc_data=amc_data, amc_urls=amc_urls)
    if not fund_page_map:
        reason = "No index page found"
        log(f"X No index found — skipping AMC", indent=1)
        skipped_log[amc_name] = {"reason": reason, "url": url}
        doc.close()
        audit["skipped"]["__amc__"] = reason
        return new_entries, audit

    fund_names = list(fund_page_map.keys())
    audit["found_in_index"] = fund_names
    audit["found_count"]    = len(fund_names)
    log(f"{len(fund_names)} funds found in index", indent=1)

    # ── 3-layer classification ────────────────────────────────────────────────
    with log_step("3-layer classification (keyword → category → Ollama)"):
        classification = classify_funds(fund_page_map)
    to_index    = [n for n, v in classification.items() if v]
    to_skip_cls = [n for n, v in classification.items() if not v]
    log(f"Keeping {len(to_index)}, skipping {len(to_skip_cls)} (liquid / index / ETF etc.)", indent=1)

    # Record classification skips in audit
    for name in to_skip_cls:
        cat = fund_page_map.get(name, {}).get("broad_category", "other") if isinstance(fund_page_map.get(name), dict) else "other"
        audit["skipped"][name] = f"classification_skip (cat={cat})"

    # GPT extraction for each qualifying fund
    total_funds = len(to_index)
    for idx, fund_name in enumerate(to_index, start=1):
        # ── Fund-level cache: skip if already extracted for the same month ──
        existing = existing_index.get(fund_name)
        if existing and existing.get("as_of") == as_of:
            log(f"[{idx}/{total_funds}] >> Cache hit (same month): {fund_name}", indent=2)
            audit["indexed"].append(fund_name)
            # carry it forward into new_entries so it stays in the output
            new_entries[fund_name] = existing
            continue

        entry_meta = fund_page_map.get(fund_name, {})
        if isinstance(entry_meta, dict):
            page_num  = entry_meta.get("page")
            broad_cat = entry_meta.get("broad_category", "other")
        else:
            page_num  = entry_meta
            broad_cat = "other"

        if not page_num:
            log(f"[{idx}/{total_funds}] X No page number for: {fund_name}", indent=2)
            audit["skipped"][fund_name] = "no_page_number"
            continue

        pdf_text = extract_pages_text(doc, page_num, PAGES_PER_FUND)
        if not pdf_text.strip():
            log(f"[{idx}/{total_funds}] X Empty PDF text: {fund_name}", indent=2)
            audit["skipped"][fund_name] = "empty_pdf_text"
            continue

        with log_step(f"[{idx}/{total_funds}] GPT extract: {fund_name}  [cat={broad_cat}, p.{page_num}]", indent=2):
            holdings_data = extract_holdings_gpt(fund_name, pdf_text, amc_name, as_of)

        if holdings_data:
            new_entries[fund_name] = {
                "amc": amc_name,
                "as_of": as_of,
                "broad_category": broad_cat,
                **holdings_data
            }
            audit["indexed"].append(fund_name)
            count = len(holdings_data.get("holdings", []))
            log(f"   + {count} holdings extracted", indent=2)
        else:
            log(f"   X GPT returned no holdings", indent=2)
            audit["skipped"][fund_name] = "gpt_extraction_failed"

        time.sleep(0.3)

    audit["indexed_count"] = len(audit["indexed"])
    audit["skipped_count"] = len(audit["skipped"])

    doc.close()
    return new_entries, audit


def main():
    parser = argparse.ArgumentParser(description="Build the mutual fund holdings index.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume mode: load existing output files and skip AMCs already indexed. "
            "Without this flag the run always starts from scratch (default)."
        ),
    )
    args = parser.parse_args()
    fresh = not args.resume   # True = scratch, False = resume

    print("\nHoldings Index Builder")
    print("=" * 60)
    print(f"  Mode: {'RESUME (skip already-done AMCs)' if not fresh else 'FRESH (full rebuild from scratch)'}")
    print("=" * 60)

    amc_urls = load_json(AMC_URLS_PATH)
    if not amc_urls:
        print(f"X Could not load {AMC_URLS_PATH}")
        return

    # Filter out Pattern C AMCs (random hash URLs — need manual update)
    processable = {k: v for k, v in amc_urls.items() if v.get("pattern") != "C"}
    pattern_c   = [k for k, v in amc_urls.items() if v.get("pattern") == "C"]

    print(f"Total AMCs in database : {len(amc_urls)}")
    print(f"Processing             : {len(processable)}")
    print(f"Skipping (Pattern C)   : {len(pattern_c)}")
    if pattern_c:
        print(f"Pattern C AMCs         : {pattern_c}")
    print("=" * 60)

    if fresh:
        # Wipe everything — true fresh run
        holdings_index: dict = {}
        skipped_log:    dict = {}
        audit_log:      dict = {}
    else:
        # Resume — load whatever was already saved
        holdings_index = load_json(OUTPUT_PATH)
        skipped_log    = load_json(SKIPPED_LOG_PATH)
        audit_log      = load_json(AUDIT_LOG_PATH)
        already_done   = {v.get("amc") for v in holdings_index.values()}
        print(f"Already indexed        : {len(already_done)} AMCs  ({len(holdings_index)} funds)")

    for amc_name, amc_data in processable.items():

        # Resume mode: skip AMCs whose funds are already in the index
        if not fresh:
            already_done = {v.get("amc") for v in holdings_index.values()}
            if amc_name in already_done:
                log(f">> Skipping (already done): {amc_name}", indent=0)
                continue

        amc_idx  = list(processable.keys()).index(amc_name) + 1
        amc_total = len(processable)
        print(f"\n{'█'*60}")
        log(f"[{amc_idx}/{amc_total}] {amc_name}", indent=0)
        print(f"{'█'*60}")

        new_entries, audit = process_amc(
            amc_name, amc_data, holdings_index, skipped_log, amc_urls
        )
        holdings_index.update(new_entries)
        audit_log[amc_name] = audit

        # Save after every AMC so a mid-run crash loses at most one AMC
        save_json(OUTPUT_PATH,      holdings_index)
        save_json(SKIPPED_LOG_PATH, skipped_log)
        save_json(AUDIT_LOG_PATH,   audit_log)

        log(f"Saved. Total indexed so far: {len(holdings_index)} funds", indent=1)
        time.sleep(DELAY_BETWEEN_AMCS)

    # ── Final summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print(f"   Funds indexed    : {len(holdings_index)}")
    print(f"   AMCs processed   : {len(audit_log)}")
    print(f"   AMCs skipped     : {len(skipped_log)}")
    print()
    print("Per-AMC summary:")
    print(f"  {'AMC':<35} {'Found':>6} {'Indexed':>8} {'Skipped':>8}")
    print(f"  {'-'*35} {'------':>6} {'--------':>8} {'--------':>8}")
    for amc, rec in audit_log.items():
        print(f"  {amc:<35} {rec['found_count']:>6} {rec['indexed_count']:>8} {rec['skipped_count']:>8}")

    print(f"\nDetailed audit saved to: {AUDIT_LOG_PATH}")
    if skipped_log:
        print("\nAMCs needing manual review:")
        for amc, info in skipped_log.items():
            print(f"   - {amc}: {info.get('reason', '?')}")


if __name__ == "__main__":
    main()
