import requests
import json
import os
from datetime import datetime, timedelta
import time

SECTORS = {
    "Large Cap": [
        "Mirae Asset Large Cap",
        "HDFC Top 100",
        "SBI Bluechip",
        "Axis Bluechip",
        "Canara Robeco Bluechip"
    ],
    "Small Cap": [
        "SBI Small Cap",
        "Nippon India Small Cap",
        "Axis Small Cap",
        "Kotak Small Cap",
        "HDFC Small Cap"
    ],
    "Mid Cap": [
        "HDFC Mid Cap Opportunities",
        "Kotak Emerging Equity",
        "Axis Midcap",
        "SBI Magnum Midcap",
        "Nippon India Growth Fund"
    ],
    "Flexi Cap": [
        "Parag Parikh Flexi Cap",
        "HDFC Flexi Cap",
        "Kotak Flexi Cap",
        "SBI Flexi Cap",
        "UTI Flexi Cap"
    ],
    "Infrastructure": [
        "HDFC Infrastructure",
        "Nippon India Power Infra",
        "DSP Tiger",
        "Canara Robeco Infrastructure",
        "Franklin India Infrastructure"
    ],
    "Defence": [
        "HDFC Defence",
        "Motilal Oswal Defence",
        "Aditya Birla Defence"
    ],
    "Technology": [
        "ICICI Prudential Technology",
        "SBI Technology",
        "Tata Digital India",
        "Aditya Birla Digital India",
        "Franklin Technology"
    ],
    "Banking & Financial Services": [
        "SBI Banking Financial",
        "Nippon Banking Financial",
        "HDFC Banking Financial",
        "Kotak Banking Financial",
        "Tata Banking Financial"
    ],
    "International": [
        "Motilal Oswal Nasdaq 100",
        "Mirae Asset NYSE FANG",
        "DSP US Flexible Equity",
        "Franklin Feeder US Opportunities",
        "PGIM India Global Equity"
    ]
}

def get_1y_return(scheme_code):
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        response = requests.get(url, timeout=10)
        data = response.json()
        nav_data = data["data"]
        
        if len(nav_data) < 2:
            return None, None
        
        current_nav = float(nav_data[0]["nav"])
        target_date = datetime.today() - timedelta(days=365)
        
        old_nav = None
        for entry in nav_data:
            entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
            if entry_date <= target_date:
                old_nav = float(entry["nav"])
                break
        
        if not old_nav:
            return None, None
        
        return_1y = round(((current_nav - old_nav) / old_nav) * 100, 2)
        return return_1y, data["meta"]["scheme_name"]
    
    except Exception:
        return None, None

def get_6m_return(scheme_code):
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        response = requests.get(url, timeout=10)
        data = response.json()
        nav_data = data["data"]
        
        current_nav = float(nav_data[0]["nav"])
        target_date = datetime.today() - timedelta(days=182)
        
        old_nav = None
        for entry in nav_data:
            entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
            if entry_date <= target_date:
                old_nav = float(entry["nav"])
                break
        
        if not old_nav:
            return None
        
        return round(((current_nav - old_nav) / old_nav) * 100, 2)
    
    except Exception:
        return None

def search_sector_funds(query):
    try:
        url = "https://api.mfapi.in/mf/search"
        response = requests.get(url, params={"q": query}, timeout=10)
        results = response.json()

        print(f"Raw results for '{query}': {len(results)}")
        for r in results[:10]:
            print(f"  {r['schemeName']}")
        print("After filter:", len(filtered))
                
        # Filter for Regular Plan Growth only
        filtered = [
            r for r in results
            if "regular" in r["schemeName"].lower()
            and "growth" in r["schemeName"].lower()
            and "idcw" not in r["schemeName"].lower()
            and "dividend" not in r["schemeName"].lower()
        ]
        
        return filtered[:20]  # top 20 results
    
    except Exception:
        return []
    
def find_fund_code(fund_name):
    try:
        url = "https://api.mfapi.in/mf/search"
        response = requests.get(url, params={"q": fund_name}, timeout=10)
        results = response.json()
        
        # Filter for regular growth
        filtered = [
            r for r in results
            if "regular" in r["schemeName"].lower()
            and "growth" in r["schemeName"].lower()
            and "idcw" not in r["schemeName"].lower()
            and "dividend" not in r["schemeName"].lower()
            and "direct" not in r["schemeName"].lower()
        ]
        
        if filtered:
            return filtered[0]["schemeCode"], filtered[0]["schemeName"]
        elif results:
            return results[0]["schemeCode"], results[0]["schemeName"]
        return None, None
    
    except Exception:
        return None, None

def build_top_performers():
    print("Building top performers cache...")
    top_performers = {}
    
    for sector, fund_names in SECTORS.items():
        print(f"\nProcessing {sector}...")
        ranked = []
        
        for fund_name in fund_names:
            scheme_code, actual_name = find_fund_code(fund_name)
            
            if not scheme_code:
                print(f"  Not found: {fund_name}")
                continue
            
            return_1y, _ = get_1y_return(scheme_code)
            if return_1y is None:
                continue
            
            return_6m = get_6m_return(scheme_code)
            
            print(f"  Found: {actual_name} — 1Y: {return_1y}%")
            
            ranked.append({
                "scheme_code": scheme_code,
                "name": actual_name,
                "return_1y": return_1y,
                "return_6m": return_6m
            })
            
            time.sleep(0.2)
        
        ranked = sorted(ranked, key=lambda x: x["return_1y"], reverse=True)[:3]
        top_performers[sector] = ranked
    
    cache = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data": top_performers
    }
    
    os.makedirs("cache", exist_ok=True)
    with open("cache/top_performers.json", "w") as f:
        json.dump(cache, f, indent=2)
    
    print("\nCache saved successfully.")
    print(f"Generated at: {cache['generated_at']}")

if __name__ == "__main__":
    build_top_performers()