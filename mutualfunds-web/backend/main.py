"""
FastAPI backend for MutualFund AI
Wraps existing Python utils from mutualfunds-ai/
Run: uvicorn main:app --reload --port 8000
"""

import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Add mutualfunds-ai to path so we can import utils directly ─────────────
PYTHON_PROJECT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "mutualfunds-ai")
)
sys.path.insert(0, PYTHON_PROJECT)

from routers import funds, holdings, market, portfolio

app = FastAPI(title="MutualFund AI API", version="1.0.0")

# Allow Next.js dev server and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(funds.router,      prefix="/api/funds",      tags=["funds"])
app.include_router(holdings.router,   prefix="/api/holdings",   tags=["holdings"])
app.include_router(market.router,     prefix="/api/market",     tags=["market"])
app.include_router(portfolio.router,  prefix="/api/portfolio",  tags=["portfolio"])

@app.get("/api/health")
def health():
    return {"status": "ok"}
