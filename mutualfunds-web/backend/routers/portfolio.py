"""
/api/portfolio — CAS PDF parsing + portfolio analytics
"""

import os
import sys
import io
import requests
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

# cas/ lives inside mutualfunds-ai which is already on sys.path via main.py
from cas.cas_parser import parse_cas

router = APIRouter()

MFAPI_BASE = "https://api.mfapi.in/mf"

# ── helpers ───────────────────────────────────────────────────────────────────

def _fetch_current_nav(scheme_name: str) -> tuple[float, str]:
    """
    Search MFAPI for a scheme by name and return (latest_nav, scheme_code).
    Falls back to (0.0, "") if not found.
    """
    try:
        resp = requests.get(
            "https://api.mfapi.in/mf/search",
            params={"q": scheme_name[:50]},
            timeout=8,
        )
        results = resp.json() if resp.ok else []
        if not results:
            return 0.0, ""
        # pick closest match (first result)
        code = str(results[0].get("schemeCode", ""))
        if not code:
            return 0.0, ""
        detail = requests.get(f"{MFAPI_BASE}/{code}", timeout=8).json()
        nav_data = detail.get("data", [])
        if nav_data:
            nav = float(nav_data[0].get("nav", 0))
            return nav, code
    except Exception:
        pass
    return 0.0, ""


def _xirr(transactions: list, current_value: float) -> float | None:
    """
    Simple XIRR approximation using scipy.
    transactions: list of {"date": "DD-MMM-YYYY", "amount": float, "units": float}
    Positive amount = purchase (cash out), negative = redemption (cash in).
    current_value: present value of holding (treated as final cash inflow).
    Returns annualised return % or None on failure.
    """
    try:
        from datetime import datetime
        from scipy.optimize import brentq

        cashflows = []  # (date, amount) — outflows negative, inflows positive
        for txn in transactions:
            try:
                d = datetime.strptime(txn["date"], "%d-%b-%Y")
            except Exception:
                try:
                    d = datetime.strptime(txn["date"], "%d-%m-%Y")
                except Exception:
                    continue
            amt = txn.get("amount", 0.0)
            ttype = txn.get("type", "").lower()
            # purchases / SIPs are outflows (negative), redemptions are inflows (positive)
            if any(k in ttype for k in ["redempt", "withdrawal", "dividend"]):
                cashflows.append((d, +amt))
            else:
                cashflows.append((d, -amt))

        if not cashflows:
            return None

        # add current value as final inflow at today
        today = datetime.today()
        cashflows.append((today, +current_value))
        cashflows.sort(key=lambda x: x[0])

        t0 = cashflows[0][0]
        days = [(cf[0] - t0).days / 365.0 for cf in cashflows]
        amounts = [cf[1] for cf in cashflows]

        def npv(r):
            return sum(a / (1 + r) ** t for a, t in zip(amounts, days))

        try:
            rate = brentq(npv, -0.999, 100.0, maxiter=200)
            return round(rate * 100, 2)
        except Exception:
            return None
    except Exception:
        return None


def _overall_return_pct(cost: float, current: float) -> float:
    if cost and cost > 0:
        return round((current - cost) / cost * 100, 2)
    return 0.0


# ── endpoint ──────────────────────────────────────────────────────────────────

@router.post("/parse-cas")
async def parse_cas_pdf(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """
    Accept a CAMS/NSDL CAS PDF + password.
    Parse holdings, enrich with live NAV from MFAPI, compute P&L and XIRR.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    raw_bytes = await file.read()
    if len(raw_bytes) < 1024:
        raise HTTPException(status_code=400, detail="File is too small — is it a valid PDF?")

    # ── parse PDF ─────────────────────────────────────────────────────────────
    try:
        parsed = parse_cas(io.BytesIO(raw_bytes), password=password)
    except Exception as e:
        err = str(e).lower()
        if "password" in err or "encrypt" in err or "decrypt" in err:
            raise HTTPException(status_code=401, detail="Wrong password. Try PAN (uppercase) + date of birth as DDMMYYYY, e.g. ABCDE1234F01011990.")
        raise HTTPException(status_code=422, detail=f"Could not parse PDF: {e}")

    investor = parsed.get("investor", {})
    raw_holdings = parsed.get("holdings", [])

    if not raw_holdings:
        raise HTTPException(
            status_code=422,
            detail="No holdings found in the PDF. Make sure this is a CAMS/NSDL CAS statement."
        )

    # ── enrich with live NAV + compute analytics ──────────────────────────────
    enriched = []
    total_invested = 0.0
    total_current  = 0.0

    for h in raw_holdings:
        scheme = h.get("scheme", "")
        units  = h.get("units", 0.0)
        cost   = h.get("cost_value", 0.0)

        # fetch live NAV (fallback to CAS-stated NAV if API fails)
        live_nav, scheme_code = _fetch_current_nav(scheme)
        if live_nav == 0.0:
            live_nav = h.get("current_nav", 0.0)

        live_value = round(units * live_nav, 2) if units and live_nav else h.get("current_value", 0.0)

        xirr_pct = _xirr(h.get("transactions", []), live_value)
        abs_return = _overall_return_pct(cost, live_value)

        total_invested += cost
        total_current  += live_value

        enriched.append({
            "amc":           h.get("amc", ""),
            "folio":         h.get("folio", ""),
            "scheme":        scheme,
            "scheme_code":   scheme_code,
            "isin":          h.get("isin", ""),
            "units":         units,
            "avg_nav":       h.get("avg_nav", 0.0),
            "cost_value":    round(cost, 2),
            "live_nav":      round(live_nav, 4),
            "live_value":    live_value,
            "abs_return_pct":abs_return,
            "xirr_pct":      xirr_pct,
            "transactions":  h.get("transactions", []),
        })

    overall_return = _overall_return_pct(total_invested, total_current)

    return {
        "investor": investor,
        "summary": {
            "total_invested":   round(total_invested, 2),
            "total_current":    round(total_current,  2),
            "total_gain":       round(total_current - total_invested, 2),
            "overall_return_pct": overall_return,
            "fund_count":       len(enriched),
        },
        "holdings": enriched,
    }
