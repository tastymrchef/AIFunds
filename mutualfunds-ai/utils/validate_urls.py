import requests
import json

with open("cache/amc_factsheet_urls.json", "r") as f:
    urls = json.load(f)

print("Validating URLs...\n")
valid = {}
invalid = {}

for amc, data in urls.items():
    # Handle both old format (string) and new format (dict)
    url = data["url"] if isinstance(data, dict) else data
    month = data.get("month", "") if isinstance(data, dict) else ""
    
    if not url:
        invalid[amc] = "No URL provided"
        print(f"✗ {amc} — No URL")
        continue
    
    try:
        response = requests.head(url, timeout=10, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        size_kb = int(response.headers.get("content-length", 0)) // 1024
        
        if response.status_code == 200:
            valid[amc] = url
            print(f"✓ {amc} ({month}) — {size_kb}KB")
        else:
            # Try GET for servers that block HEAD
            response = requests.get(url, timeout=15, allow_redirects=True, stream=True,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            chunk = next(response.iter_content(1024), b"")
            is_pdf = chunk[:4] == b"%PDF"
            
            if response.status_code == 200 and is_pdf:
                valid[amc] = url
                print(f"✓ {amc} ({month}) — PDF confirmed")
            else:
                invalid[amc] = f"HTTP {response.status_code}"
                print(f"✗ {amc} — HTTP {response.status_code}")
                
    except Exception as e:
        invalid[amc] = str(e)
        print(f"✗ {amc} — {e}")

print(f"\n{'='*60}")
print(f"Valid: {len(valid)}/{len(urls)}")
print(f"Invalid: {len(invalid)}/{len(urls)}")

if invalid:
    print(f"\nInvalid:")
    for amc, reason in invalid.items():
        print(f"  ✗ {amc} — {reason}")
