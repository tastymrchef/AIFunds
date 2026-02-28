import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta

# Keywords that identify equity growth funds
EQUITY_KEYWORDS = [
    "large cap", "small cap", "mid cap", "flexi cap", "multicap",
    "multi cap", "elss", "bluechip", "blue chip", "infrastructure",
    "defence", "technology", "digital", "banking", "financial services",
    "pharma", "consumption", "dividend yield", "value fund", "contra",
    "focused", "hybrid", "aggressive hybrid", "nasdaq", "global",
    "overseas", "international", "emerging market"
]

EXCLUDE_KEYWORDS = [
    "direct", "idcw", "dividend", "bonus", "debt", "liquid",
    "overnight", "gilt", "money market", "ultra short", "low duration",
    "short duration", "medium duration", "long duration", "dynamic bond",
    "corporate bond", "credit risk", "banking and psu", "floater",
    "arbitrage", "fmp", "interval", "fixed maturity", "capital protection",
    "segregated", "institutional", "income", "pension", "annuity"
]

def fetch_all_funds():
    print("Fetching all funds from mfapi...")
    url = "https://api.mfapi.in/mf?limit=10000&offset=0"
    response = requests.get(url, timeout=30)
    all_funds = response.json()
    print(f"Total funds fetched: {len(all_funds)}")
    return all_funds

def filter_equity_growth_funds(all_funds):
    filtered = []
    
    for fund in all_funds:
        name = fund["schemeName"].lower()
        
        # Must contain "regular" and "growth"
        if "regular" not in name and "growth" not in name:
            continue
        if "regular" not in name:
            continue
        if "growth" not in name:
            continue
            
        # Must not contain any exclude keywords
        excluded = False
        for kw in EXCLUDE_KEYWORDS:
            if kw in name:
                excluded = True
                break
        if excluded:
            continue
        
        # Must contain at least one equity keyword
        is_equity = False
        for kw in EQUITY_KEYWORDS:
            if kw in name:
                is_equity = True
                break
        if not is_equity:
            continue
        
        filtered.append(fund)
    
    print(f"Filtered to {len(filtered)} equity regular growth funds")
    return filtered

def assign_sector(fund_name):
    name = fund_name.lower()
    if any(k in name for k in ["small cap", "smallcap"]):
        return "Small Cap"
    elif any(k in name for k in ["mid cap", "midcap"]):
        return "Mid Cap"
    elif any(k in name for k in ["large cap", "largecap", "bluechip", "blue chip", "top 100", "top100"]):
        return "Large Cap"
    elif any(k in name for k in ["flexi cap", "flexicap", "multi cap", "multicap"]):
        return "Flexi Cap"
    elif any(k in name for k in ["infrastructure", "infra"]):
        return "Infrastructure"
    elif any(k in name for k in ["defence", "defense"]):
        return "Defence"
    elif any(k in name for k in ["technology", "digital", "tech"]):
        return "Technology"
    elif any(k in name for k in ["banking", "financial services", "bank"]):
        return "Banking & Financial Services"
    elif any(k in name for k in ["nasdaq", "global", "overseas", "international", "us equity", "world"]):
        return "International"
    elif any(k in name for k in ["pharma", "health", "medicine"]):
        return "Pharma & Healthcare"
    elif any(k in name for k in ["consumption", "consumer"]):
        return "Consumption"
    elif "elss" in name or "tax saver" in name:
        return "ELSS"
    elif any(k in name for k in ["hybrid", "aggressive"]):
        return "Hybrid"
    else:
        return "Diversified"

def calculate_features(scheme_code):
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}"
        response = requests.get(url, timeout=10)
        data = response.json()
        nav_data = data["data"]
        meta = data["meta"]
        
        # Skip funds with less than 1 year of data
        if len(nav_data) < 250:
            return None
        
        current_nav = float(nav_data[0]["nav"])
        
        # Check fund is active — latest NAV should be recent
        latest_date = datetime.strptime(nav_data[0]["date"], "%d-%m-%Y")
        if (datetime.today() - latest_date).days > 30:
            return None  # fund hasn't been updated in 30 days — likely defunct
        
        def get_return(days):
            target = datetime.today() - timedelta(days=days)
            for entry in nav_data:
                entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
                if entry_date <= target:
                    old_nav = float(entry["nav"])
                    return round(((current_nav - old_nav) / old_nav) * 100, 2)
            return None
        
        returns = {
            "1y": get_return(365),
            "3y": get_return(1095),
            "5y": get_return(1825),
        }
        
        # Skip if no 1y return
        if returns["1y"] is None:
            return None
        
        # Volatility
        navs = [float(d["nav"]) for d in nav_data[:365]]
        daily_returns = [
            (navs[i] - navs[i+1]) / navs[i+1]
            for i in range(len(navs)-1)
        ]
        volatility = round(float(np.std(daily_returns) * 100), 4)
        
        # Max drawdown
        navs_3y = [float(d["nav"]) for d in nav_data[:min(1095, len(nav_data))]]
        peak = navs_3y[0]
        max_drawdown = 0
        for nav in navs_3y:
            if nav > peak:
                peak = nav
            drawdown = (peak - nav) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            "scheme_code": scheme_code,
            "name": meta["scheme_name"],
            "fund_house": meta["fund_house"],
            "category": meta["scheme_category"],
            "returns": returns,
            "volatility": volatility,
            "max_drawdown": round(max_drawdown, 2)
        }
    
    except Exception:
        return None

def build_universe():
    all_funds = fetch_all_funds()
    filtered_funds = filter_equity_growth_funds(all_funds)
    
    universe = []
    total = len(filtered_funds)
    
    print(f"\nFetching features for {total} funds...")
    print("This will take 15-20 minutes. Go grab a coffee.\n")
    
    for i, fund in enumerate(filtered_funds):
        features = calculate_features(fund["schemeCode"])
        
        if features:
            features["sector"] = assign_sector(fund["schemeName"])
            universe.append(features)
            print(f"[{i+1}/{total}] ✓ {features['name'][:60]} — 1Y: {features['returns']['1y']}%")
        else:
            print(f"[{i+1}/{total}] ✗ Skipped: {fund['schemeName'][:60]}")
        
        time.sleep(0.2)
    
    os.makedirs("cache", exist_ok=True)
    with open("cache/fund_universe.json", "w") as f:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_funds": len(universe),
            "data": universe
        }, f, indent=2)
    
    print(f"\nDone. {len(universe)} funds saved to cache/fund_universe.json")
    
    # Print sector breakdown
    from collections import Counter
    sectors = Counter(f["sector"] for f in universe)
    print("\nSector breakdown:")
    for sector, count in sectors.most_common():
        print(f"  {sector}: {count} funds")

if __name__ == "__main__":
    build_universe()
