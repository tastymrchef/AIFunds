import requests
import json

with open("cache/amc_factsheet_urls.json", "r") as f:
    urls = json.load(f)

print("Validating URLs...\n")
valid = {}
invalid = {}

for amc, url in urls.items():
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            size_kb = int(response.headers.get("content-length", 0)) // 1024
            valid[amc] = url
            print(f"✓ {amc} — {size_kb}KB")
        else:
            invalid[amc] = f"HTTP {response.status_code}"
            print(f"✗ {amc} — HTTP {response.status_code}")
    except Exception as e:
        invalid[amc] = str(e)
        print(f"✗ {amc} — {e}")

print(f"\nValid: {len(valid)}/48")
print(f"Invalid: {len(invalid)}/48")
