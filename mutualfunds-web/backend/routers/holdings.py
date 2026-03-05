"""
/api/holdings — thematic search: find funds by stock name
"""

import os
import json
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from rapidfuzz import process, fuzz

router = APIRouter()

HOLDINGS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "mutualfunds-ai", "cache", "holdings_index.json")
)

@lru_cache(maxsize=1)
def _load_index() -> dict:
    if not os.path.exists(HOLDINGS_PATH):
        return {}
    with open(HOLDINGS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=1)
def _build_stock_map() -> dict:
    idx = _load_index()
    stock_map: dict = {}
    for fund_name, fund_data in idx.items():
        category = fund_data.get("broad_category") or fund_data.get("category", "")
        amc = fund_data.get("amc", "")
        for holding in fund_data.get("holdings", []):
            stock = holding.get("stock", "").strip()
            if not stock:
                continue
            weight_str = holding.get("weight") or ""
            try:
                weight_float = float(weight_str.replace("%", "").strip())
            except Exception:
                weight_float = 0.0
            key = stock.lower()
            stock_map.setdefault(key, []).append({
                "fund_name": fund_name,
                "weight_str": weight_str or "—",
                "weight_float": weight_float,
                "category": category,
                "amc": amc,
                "stock_display": stock,
                "sector": holding.get("sector", ""),
            })
    for key in stock_map:
        stock_map[key].sort(key=lambda x: x["weight_float"], reverse=True)
    return stock_map

@router.get("/search")
def search_stock(q: str):
    """
    Fuzzy search stocks/instruments across all indexed funds.
    Returns matched stock name + list of funds holding it.
    """
    if not q or len(q) < 2:
        return {"matches": []}

    stock_map = _build_stock_map()
    all_stocks = list(stock_map.keys())

    results = process.extract(q.lower(), all_stocks, scorer=fuzz.WRatio, limit=5)
    matches = [r[0] for r in results if r[1] >= 60]

    if not matches:
        return {"matches": []}

    return {
        "matches": [
            {
                "display_name": stock_map[s][0]["stock_display"],
                "stock_key": s,
                "fund_count": len(stock_map[s]),
            }
            for s in matches
        ]
    }

@router.get("/stock/{stock_key}")
def funds_for_stock(stock_key: str):
    """
    Return all funds holding a given stock (by lowercase key).
    """
    stock_map = _build_stock_map()
    results = stock_map.get(stock_key.lower())
    if results is None:
        raise HTTPException(status_code=404, detail=f"Stock '{stock_key}' not found")
    return {
        "display_name": results[0]["stock_display"],
        "total_funds": len(results),
        "funds": [
            {
                "scheme_name": r["fund_name"],
                "fund_house": r["amc"],
                "weight": r["weight_float"],
                "weight_str": r["weight_str"],
                "category": r["category"],
                "sector": r["sector"],
            }
            for r in results
        ],
    }

@router.get("/stats")
def stats():
    """Total funds and unique stocks in the index."""
    idx = _load_index()
    stock_map = _build_stock_map()
    return {
        "total_funds": len(idx),
        "total_stocks": len(stock_map),
    }
