"""
/api/funds — fund search, fund detail, NAV, returns, AI summary, chat, similar funds
"""

import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "mutualfunds-ai", ".env")
)

from utils.fund_data import (
    search_funds,
    get_fund_data,
    calculate_returns,
    get_nifty_data,
    calculate_nifty_returns,
)
from utils.ai_utils import get_ai_summary, chat_with_fund, build_fund_system_prompt
from utils.clustering import find_similar_funds
from utils.fund_report_agent import get_fund_report
from datetime import datetime, timedelta

router = APIRouter()

# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search")
def search(q: str):
    """Search funds by name. Returns top 10 matches."""
    if not q or len(q) < 2:
        return {"results": []}
    raw = search_funds(q)
    results = []
    for r in (raw or [])[:10]:
        # search_funds returns camelCase keys from the MFAPI
        results.append({
            "scheme_code": str(r.get("schemeCode", r.get("scheme_code", ""))),
            "scheme_name": r.get("schemeName", r.get("scheme_name", "")),
            "fund_house": r.get("fundHouse", r.get("fund_house", "")),
            "scheme_category": r.get("schemeCategory", r.get("scheme_category", "")),
        })
    return {"results": results}

# ── Fund detail ───────────────────────────────────────────────────────────────

@router.get("/{scheme_code}")
def fund_detail(scheme_code: str):
    """Full fund detail: meta, NAV history, returns, and matching Nifty series."""
    try:
        fund = get_fund_data(scheme_code)
        nav_data = fund["data"][:365 * 15]   # cap at 15 years
        returns = calculate_returns(fund["data"])

        # Build Nifty series for the same date range as the fund NAV
        # nav_data is newest-first; oldest entry is last
        import pandas as pd
        df = pd.DataFrame(nav_data)
        df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
        start_date = df["date"].min()
        end_date   = df["date"].max()

        nifty_df = get_nifty_data(start_date, end_date)
        nifty_df.columns = ["date", "nifty_close"]
        nifty_df["date"] = pd.to_datetime(nifty_df["date"])
        nifty_df = nifty_df.dropna()

        nifty_series = []
        if not nifty_df.empty:
            nifty_series = [
                {"date": row["date"].strftime("%d-%m-%Y"), "value": float(row["nifty_close"])}
                for _, row in nifty_df.iterrows()
            ]

        return {
            "meta": fund["meta"],
            "nav_data": nav_data,
            "returns": returns,
            "nifty_data": nifty_series,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{scheme_code}/summary")
def fund_summary(scheme_code: str):
    """AI-generated plain-English fund summary."""
    try:
        fund = get_fund_data(scheme_code)
        returns = calculate_returns(fund["data"])
        summary = get_ai_summary(fund["meta"], returns)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{scheme_code}/similar")
def similar_funds(scheme_code: str):
    """Funds with similar risk/return profile."""
    try:
        target, similar = find_similar_funds(scheme_code)
        if target is None:
            return {"similar": [], "message": "Fund not in similarity index"}
        return {"target": target, "similar": similar}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{scheme_code}/report")
def fund_report(scheme_code: str, fund_house: str, scheme_name: str):
    """Fund manager report extracted from factsheet PDF."""
    try:
        report = get_fund_report(
            scheme_code=scheme_code,
            fund_house=fund_house,
            scheme_name=scheme_name,
        )
        return {"report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Nifty ─────────────────────────────────────────────────────────────────────

@router.get("/nifty/returns")
def nifty_returns():
    """Nifty 50 returns for 1Y/3Y/5Y/10Y."""
    try:
        start = datetime.today() - timedelta(days=3650)
        df = get_nifty_data(start, datetime.today())
        df.columns = ["date", "value"]
        returns = calculate_nifty_returns(df)
        return returns
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nifty/nav")
def nifty_nav():
    """Nifty 50 daily closing values for the last 15 years (for chart)."""
    try:
        start = datetime.today() - timedelta(days=365 * 15)
        df = get_nifty_data(start, datetime.today())
        df.columns = ["date", "value"]
        df = df.dropna().sort_values("date")
        return {"data": df.rename(columns={"value": "nav"}).to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    scheme_code: str
    messages: list[dict]       # [{role, content}, ...]
    manager_info: str = ""

@router.post("/chat")
def chat(req: ChatRequest):
    """Chat with AI about a specific fund."""
    try:
        fund = get_fund_data(req.scheme_code)
        returns = calculate_returns(fund["data"])
        system_prompt = build_fund_system_prompt(
            fund["meta"], fund["data"], returns, req.manager_info
        )
        full_messages = [{"role": "system", "content": system_prompt}] + req.messages
        response = chat_with_fund(full_messages)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
