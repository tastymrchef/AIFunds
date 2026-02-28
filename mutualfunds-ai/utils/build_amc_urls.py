import openai
import json
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# All AMCs from AMFI page
ALL_AMCS = [
    "360 ONE Mutual Fund",
    "Aditya Birla Sun Life Mutual Fund",
    "Angel One Mutual Fund",
    "Axis Mutual Fund",
    "Bajaj Finserv Mutual Fund",
    "Bandhan Mutual Fund",
    "Bank of India Mutual Fund",
    "Baroda BNP Paribas Mutual Fund",
    "Canara Robeco Mutual Fund",
    "Capitalmind Mutual Fund",
    "Choice Mutual Fund",
    "DSP Mutual Fund",
    "Edelweiss Mutual Fund",
    "Franklin Templeton Mutual Fund",
    "Groww Mutual Fund",
    "HDFC Mutual Fund",
    "Helios Mutual Fund",
    "HSBC Mutual Fund",
    "ICICI Prudential Mutual Fund",
    "Invesco Mutual Fund",
    "ITI Mutual Fund",
    "Jio BlackRock Mutual Fund",
    "JM Financial Mutual Fund",
    "Kotak Mahindra Mutual Fund",
    "LIC Mutual Fund",
    "Mahindra Manulife Mutual Fund",
    "Mirae Asset Mutual Fund",
    "Motilal Oswal Mutual Fund",
    "Navi Mutual Fund",
    "Nippon India Mutual Fund",
    "NJ Mutual Fund",
    "Old Bridge Mutual Fund",
    "PGIM India Mutual Fund",
    "PPFAS Mutual Fund",
    "quant Mutual Fund",
    "Quantum Mutual Fund",
    "Samco Mutual Fund",
    "SBI Mutual Fund",
    "Shriram Mutual Fund",
    "Sundaram Mutual Fund",
    "Tata Mutual Fund",
    "Taurus Mutual Fund",
    "Trust Mutual Fund",
    "Unifi Mutual Fund",
    "Union Mutual Fund",
    "UTI Mutual Fund",
    "WhiteOak Capital Mutual Fund",
    "Zerodha Mutual Fund"
]

def find_factsheet_urls_batch(amc_batch):
    """Find factsheet URLs for a batch of AMCs"""
    response = client.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[{
            "role": "user",
            "content": f"""Find the direct PDF download URLs for the latest monthly factsheets (January 2026 or December 2025) for these Indian mutual fund houses:

{chr(10).join(f'- {amc}' for amc in amc_batch)}

Search for each one carefully. Return only real, verified direct PDF URLs.

Respond in this exact JSON format only, no other text:
{{
    "360 ONE Mutual Fund": "https://...",
    "Aditya Birla Sun Life Mutual Fund": "https://...",
    ...
}}

Rules:
- Only include AMCs where you found a real direct PDF URL
- URL must end in .pdf
- If you cannot find a verified URL for an AMC, omit it
- Return only valid JSON"""
        }]
    )
    
    content = response.choices[0].message.content.strip()
    content = content.replace("```json", "").replace("```", "").strip()
    
    try:
        return json.loads(content)
    except Exception as e:
        print(f"Parse error: {e}")
        print(f"Raw: {content[:500]}")
        return {}

def build_all_urls():
    print(f"Finding factsheet URLs for {len(ALL_AMCS)} AMCs...")
    all_urls = {}
    
    # Process in batches of 10 to avoid overwhelming the search
    batch_size = 10
    for i in range(0, len(ALL_AMCS), batch_size):
        batch = ALL_AMCS[i:i+batch_size]
        print(f"\nBatch {i//batch_size + 1}: {batch[0]} to {batch[-1]}")
        
        urls = find_factsheet_urls_batch(batch)
        all_urls.update(urls)
        
        print(f"Found {len(urls)} URLs in this batch:")
        for amc, url in urls.items():
            print(f"  ✓ {amc}")
    
    # Save to cache
    os.makedirs("cache", exist_ok=True)
    with open("cache/amc_factsheet_urls.json", "w") as f:
        json.dump(all_urls, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Total found: {len(all_urls)}/{len(ALL_AMCS)} AMCs")
    print(f"Saved to cache/amc_factsheet_urls.json")
    
    # Show what's missing
    missing = [amc for amc in ALL_AMCS if amc not in all_urls]
    if missing:
        print(f"\nNot found ({len(missing)}):")
        for amc in missing:
            print(f"  ✗ {amc}")

MISSING_TOP_AMCS = [
    "HDFC Mutual Fund",
    "Kotak Mahindra Mutual Fund",
    "Axis Mutual Fund",
    "Mirae Asset Mutual Fund",
    "Nippon India Mutual Fund",
    "DSP Mutual Fund",
    "Franklin Templeton Mutual Fund",
    "Motilal Oswal Mutual Fund",
    "Bandhan Mutual Fund",
    "Canara Robeco Mutual Fund"
]

def find_individual_url(amc_name):
    response = client.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[{
            "role": "user",
            "content": f"Find the direct PDF download URL for the January 2026 or December 2025 monthly factsheet of {amc_name} India. Search carefully on their official website. Return only the direct PDF URL ending in .pdf, nothing else."
        }]
    )
    content = response.choices[0].message.content.strip()
    import re
    urls = re.findall(r'https?://[^\s]+\.pdf', content)
    return urls[0] if urls else None

def find_missing_urls():
    # Load existing cache
    with open("cache/amc_factsheet_urls.json", "r") as f:
        existing = json.load(f)
    
    print(f"Finding URLs for top missing AMCs individually...")
    found = 0
    
    for amc in MISSING_TOP_AMCS:
        print(f"\nSearching: {amc}...")
        url = find_individual_url(amc)
        if url:
            existing[amc] = url
            found += 1
            print(f"  ✓ Found: {url}")
        else:
            print(f"  ✗ Not found")
    
    # Save updated cache
    with open("cache/amc_factsheet_urls.json", "w") as f:
        json.dump(existing, f, indent=2)
    
    print(f"\nFound {found}/{len(MISSING_TOP_AMCS)} additional URLs")
    print(f"Total now: {len(existing)}/48")

if __name__ == "__main__":
    find_missing_urls()

