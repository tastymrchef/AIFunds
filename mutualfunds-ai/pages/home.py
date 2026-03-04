import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import openai
import os
from dotenv import load_dotenv
import json

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def load_top_performers():
    try:
        with open("cache/top_performers.json", "r") as f:
            cache = json.load(f)
        return cache["data"], cache["generated_at"]
    except Exception:
        return None, None

def get_market_data():
    tickers = {
        "Nifty 50": "^NSEI",
        "Sensex": "^BSESN",
        "Gold": "GC=F",
        "Silver": "SI=F"
    }
    
    market_data = {}
    for name, ticker in tickers.items():
        data = yf.Ticker(ticker)
        info = data.fast_info
        current = round(info.last_price, 2)
        prev_close = round(info.previous_close, 2)
        change = round(current - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)
        market_data[name] = {
            "current": current,
            "change": change,
            "change_pct": change_pct
        }
    
    return market_data

def get_market_summary():
    response = client.chat.completions.create(
        model="gpt-4o-search-preview",
        web_search_options={},
        messages=[
            {
                "role": "user",
                "content": """What is happening in the Indian stock market today? 
                Write a 3 sentence summary covering:
                1. Overall market direction and why
                2. Any key sectors moving significantly
                3. One thing investors should watch today
                
                Be specific, current, and concise. No bullet points."""
            }
        ]
    )
    return response.choices[0].message.content

# ---- UI ----

st.title("📈 MutualFund AI")
st.caption("Your intelligent guide to Indian mutual funds")

st.markdown("<br>", unsafe_allow_html=True)

search_query = st.text_input(
    label="search",
    placeholder="🔍 Search any mutual fund — e.g. Parag Parikh Flexi Cap, HDFC Small Cap...",
    label_visibility="collapsed"
)

if search_query:
    st.session_state.home_search = search_query
    st.switch_page("pages/fund_search.py")

st.divider()

# Market Pulse
st.subheader("Market Pulse")

with st.spinner("Fetching live market data..."):
    market_data = get_market_data()

col1, col2, col3, col4 = st.columns(4)

for col, (name, data) in zip([col1, col2, col3, col4], market_data.items()):
    arrow = "▲" if data["change"] >= 0 else "▼"
    color = "normal" if data["change"] >= 0 else "inverse"
    col.metric(
        label=name,
        value=f"{data['current']:,}",
        delta=f"{arrow} {data['change']} ({data['change_pct']}%)",
        delta_color=color
    )

st.divider()

# Market Summary
st.subheader("Market Summary")
with st.spinner("Generating market summary..."):
    summary = get_market_summary()
st.write(summary)

# Top Performers
st.divider()

top_performers, generated_at = load_top_performers()

if top_performers:
    st.subheader("🏆 Top Performers by Sector")
    st.caption(f"Based on 1 year returns • Last updated: {generated_at}")
    
    sectors = list(top_performers.keys())
    
    # Display in rows of 3 sectors each
    for i in range(0, len(sectors), 3):
        cols = st.columns(3)
        row_sectors = sectors[i:i+3]
        
        for col, sector in zip(cols, row_sectors):
            funds = top_performers[sector]
            with col:
                st.markdown(f"**{sector}**")
                for fund in funds:
                    name = fund["name"]
                    # Shorten long fund names
                    short_name = name[:45] + "..." if len(name) > 45 else name
                    return_1y = fund.get("return_1y")
                    return_6m = fund.get("return_6m")
                    
                    color = "#00ff88" if return_1y and return_1y > 0 else "#ff4444"
                    
                    st.markdown(f"""
                    <div style='
                        background: #1a1a1a;
                        border-radius: 8px;
                        padding: 10px 14px;
                        margin-bottom: 8px;
                        border-left: 3px solid {color};
                    '>
                        <div style='font-size: 12px; color: #aaa; margin-bottom: 4px;'>{short_name}</div>
                        <div style='display: flex; gap: 16px;'>
                            <span style='color: {color}; font-weight: bold; font-size: 14px;'>1Y: {return_1y}%</span>
                            <span style='color: #888; font-size: 13px;'>6M: {return_6m}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)


st.divider()

# CTA
st.subheader("Find Your Fund")
st.caption("Search and analyse any Indian mutual fund with AI")

col1, col2 = st.columns(2)
with col1:
    if st.button("🔍 Search Funds", use_container_width=True):
        st.switch_page("pages/fund_search.py")
with col2:
    if st.button("📦 Find by Stock / Theme", use_container_width=True):
        st.switch_page("pages/holdings_search.py")