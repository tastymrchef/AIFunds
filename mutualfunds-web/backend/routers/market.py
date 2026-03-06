"""
/api/market — live market pulse (Nifty, Sensex, Gold, Silver) + top performers + news + health
"""

import os
import json
import time
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

# Tickers used for news scraping — broad Indian market coverage
NEWS_TICKERS = ["^NSEI", "^BSESN", "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS"]

@router.get("/pulse")
def market_pulse():
    """Live price + day change for Nifty 50, Sensex, Gold, Silver."""
    result = {}
    for name, ticker in TICKERS.items():
        try:
            info = yf.Ticker(ticker).fast_info
            current    = round(float(info.last_price), 2)
            prev       = round(float(info.previous_close), 2)
            change     = round(current - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0.0
            result[name] = {
                "current": current,
                "change": change,
                "change_pct": change_pct,
            }
        except Exception as e:
            result[name] = {"error": str(e)}
    return result


@router.get("/health")
def market_health():
    """
    Returns two separate market pictures:
      - today:      today's % change for Nifty, Sensex, Gold, Silver + a score
      - two_week:   14-calendar-day (≈10 trading day) trend for Nifty, Sensex, Gold, Silver + a score

    Score logic (same formula applied independently to each window):
      base 50 + Nifty signal (±30) + Sensex signal (±20) + Gold inverse (±10) + Silver (±10)
    Overall health label is driven purely by the two-week score so one green day
    can't mask a bad fortnight.
    """

    # ── helpers ──────────────────────────────────────────────────────────────
    def _score_from_pcts(nifty, sensex, gold, silver) -> int:
        s  = 50
        s += max(-30, min(30, nifty  * 15))
        s += max(-20, min(20, sensex * 10))
        s -= max(-10, min(10, gold   *  5))   # gold inverse
        s += max(-10, min(10, silver *  5))
        return int(max(0, min(100, s)))

    def _label_color(score: int):
        if score >= 65:   return "Bullish", "#00ff88"
        if score <= 35:   return "Bearish", "#ff4444"
        return "Neutral", "#ff9944"

    # ── today's % changes ────────────────────────────────────────────────────
    today_pcts: dict = {}
    for name, ticker in TICKERS.items():
        try:
            info = yf.Ticker(ticker).fast_info
            cur  = float(info.last_price)
            prev = float(info.previous_close)
            today_pcts[name] = ((cur - prev) / prev * 100) if prev else 0.0
        except Exception:
            today_pcts[name] = 0.0

    t_nifty  = today_pcts.get("Nifty 50", 0.0)
    t_sensex = today_pcts.get("Sensex",   0.0)
    t_gold   = today_pcts.get("Gold",     0.0)
    t_silver = today_pcts.get("Silver",   0.0)
    today_score = _score_from_pcts(t_nifty, t_sensex, t_gold, t_silver)
    today_label, today_color = _label_color(today_score)

    # ── 2-week % changes (14 calendar days ≈ 10 trading days) ───────────────
    tw_pcts: dict = {}
    for name, ticker in TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="15d")
            if len(hist) >= 2:
                close_now  = float(hist["Close"].iloc[-1])
                close_then = float(hist["Close"].iloc[0])
                tw_pcts[name] = ((close_now - close_then) / close_then * 100) if close_then else 0.0
            else:
                tw_pcts[name] = 0.0
        except Exception:
            tw_pcts[name] = 0.0

    tw_nifty  = tw_pcts.get("Nifty 50", 0.0)
    tw_sensex = tw_pcts.get("Sensex",   0.0)
    tw_gold   = tw_pcts.get("Gold",     0.0)
    tw_silver = tw_pcts.get("Silver",   0.0)
    tw_score = _score_from_pcts(tw_nifty, tw_sensex, tw_gold, tw_silver)
    tw_label, tw_color = _label_color(tw_score)

    # ── overall label driven by two-week score ───────────────────────────────
    overall_label, overall_color = _label_color(tw_score)
    today_str = f"{'up' if t_nifty >= 0 else 'down'} {abs(round(t_nifty, 2))}% today"
    tw_str    = f"{'up' if tw_nifty >= 0 else 'down'} {abs(round(tw_nifty, 2))}% over 2 weeks"

    if tw_score >= 65:
        summary = f"Strong uptrend in play. Nifty is {today_str} and {tw_str}."
    elif tw_score <= 35:
        summary = f"Markets under sustained pressure. Nifty is {today_str} and {tw_str}."
    else:
        summary = f"Markets are mixed. Nifty is {today_str} and {tw_str}."

    return {
        "score":         tw_score,          # overall score = 2-week score
        "label":         overall_label,
        "color":         overall_color,
        "summary":       summary,
        "today": {
            "score": today_score,
            "label": today_label,
            "color": today_color,
            "nifty_pct":  round(t_nifty,  2),
            "sensex_pct": round(t_sensex, 2),
            "gold_pct":   round(t_gold,   2),
            "silver_pct": round(t_silver, 2),
        },
        "two_week": {
            "score": tw_score,
            "label": tw_label,
            "color": tw_color,
            "nifty_pct":  round(tw_nifty,  2),
            "sensex_pct": round(tw_sensex, 2),
            "gold_pct":   round(tw_gold,   2),
            "silver_pct": round(tw_silver, 2),
        },
    }


@router.get("/trend")
def market_trend():
    """
    Returns daily closing values for Nifty 50 over the last 15 calendar days
    for rendering a sparkline on the home page.
    """
    try:
        hist = yf.Ticker("^NSEI").history(period="15d")
        points = [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
            for idx, row in hist.iterrows()
        ]
        return {"points": points}
    except Exception as e:
        return {"points": [], "error": str(e)}




@router.get("/news")
def market_news():
    """
    Fetch recent news headlines from yfinance for major Indian market tickers.
    Returns up to 10 unique headlines sorted by recency.
    """
    seen_titles: set = set()
    articles = []

    for ticker_sym in NEWS_TICKERS:
        try:
            ticker = yf.Ticker(ticker_sym)
            news_items = ticker.news or []
            for item in news_items[:5]:
                content = item.get("content", {})
                title = content.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                # provider info
                provider = content.get("provider", {})
                source = provider.get("displayName", "") or provider.get("name", "Yahoo Finance")

                # publish time
                pub_time = content.get("pubDate", "")  # ISO string e.g. "2026-03-05T10:30:00Z"
                timestamp = 0
                if pub_time:
                    try:
                        import datetime
                        dt = datetime.datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                        timestamp = int(dt.timestamp())
                    except Exception:
                        timestamp = 0

                # url
                url = ""
                canonical = content.get("canonicalUrl", {})
                if isinstance(canonical, dict):
                    url = canonical.get("url", "")
                if not url:
                    url = content.get("clickThroughUrl", {}).get("url", "") if isinstance(content.get("clickThroughUrl"), dict) else ""

                articles.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "timestamp": timestamp,
                    "time_ago": _time_ago(timestamp),
                })
        except Exception:
            continue

    # Sort by recency, take top 10
    articles.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"news": articles[:10]}


def _time_ago(timestamp: int) -> str:
    """Convert unix timestamp to human-readable 'X hours ago' string."""
    if not timestamp:
        return "recently"
    diff = int(time.time()) - timestamp
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{diff // 60}m ago"
    if diff < 86400:
        return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


@router.get("/top-performers")
def top_performers():
    """Returns cached top performers JSON built by top_performers.py."""
    if not os.path.exists(TOP_PERFORMERS_PATH):
        raise HTTPException(status_code=404, detail="Top performers cache not found. Run utils/top_performers.py first.")
    with open(TOP_PERFORMERS_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)
    return cache
