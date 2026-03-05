"""
/api/market — live market pulse (Nifty, Sensex, Gold, Silver) + top performers cache
"""

import os
import json
from fastapi import APIRouter, HTTPException
import yfinance as yf

router = APIRouter()

TOP_PERFORMERS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "mutualfunds-ai", "cache", "top_performers.json")
)

TICKERS = {
    "Nifty 50":  "^NSEI",
    "Sensex":    "^BSESN",
    "Gold":      "GC=F",
    "Silver":    "SI=F",
}

@router.get("/pulse")
def market_pulse():
    """Live price + day change for Nifty 50, Sensex, Gold, Silver."""
    result = {}
    for name, ticker in TICKERS.items():
        try:
            info = yf.Ticker(ticker).fast_info
            current   = round(float(info.last_price), 2)
            prev      = round(float(info.previous_close), 2)
            change    = round(current - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0.0
            result[name] = {
                "current": current,
                "change": change,
                "change_pct": change_pct,
            }
        except Exception as e:
            result[name] = {"error": str(e)}
    return result

@router.get("/top-performers")
def top_performers():
    """Returns cached top performers JSON built by top_performers.py."""
    if not os.path.exists(TOP_PERFORMERS_PATH):
        raise HTTPException(status_code=404, detail="Top performers cache not found. Run utils/top_performers.py first.")
    with open(TOP_PERFORMERS_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)
    return cache
