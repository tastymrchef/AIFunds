import streamlit as st
import json
import os
from rapidfuzz import process, fuzz

st.set_page_config(
    page_title="Stock Search · MutualFund AI",
    page_icon="🔎",
    layout="wide"
)

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📈 MutualFund AI")
    st.divider()
    if st.button("🏠 Home", use_container_width=True):
        st.switch_page("pages/home.py")
    if st.button("🔍 Search Funds", use_container_width=True):
        st.switch_page("pages/fund_search.py")
    st.button("📦 Find by Stock", use_container_width=True, disabled=True)  # current page

# ── Load holdings index ───────────────────────────────────────────────────────
@st.cache_data
def load_holdings_index():
    path = "cache/holdings_index.json"
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@st.cache_data
def build_stock_map(holdings_index: dict) -> dict:
    """
    Build reverse index: {stock_name_lower: [(fund_name, weight_float, weight_str, category, amc), ...]}
    Sorted by weight descending within each stock.
    """
    stock_map = {}
    for fund_name, fund_data in holdings_index.items():
        category = fund_data.get("category", "")
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
            if key not in stock_map:
                stock_map[key] = []
            stock_map[key].append({
                "fund_name": fund_name,
                "weight_str": weight_str if weight_str else "—",
                "weight_float": weight_float,
                "category": category,
                "amc": amc,
                "stock_display": stock  # original casing
            })

    # Sort each stock's fund list by weight descending
    for key in stock_map:
        stock_map[key].sort(key=lambda x: x["weight_float"], reverse=True)

    return stock_map

def search_stocks(query: str, stock_map: dict, top_n: int = 10) -> list[str]:
    """Fuzzy match query against all stock names, return top matches."""
    all_stocks = list(stock_map.keys())
    results = process.extract(
        query.lower(),
        all_stocks,
        scorer=fuzz.WRatio,
        limit=top_n
    )
    # Only return matches with decent score
    return [r[0] for r in results if r[1] >= 60]

# ── Page ──────────────────────────────────────────────────────────────────────
st.title("📦 Find Funds by Stock or Theme")
st.caption("Type any stock name to see which mutual funds hold it and how much")

holdings_index = load_holdings_index()

if not holdings_index:
    st.error("Holdings index not found. Run `python utils/build_holdings_index.py` first.")
    st.stop()

stock_map = build_stock_map(holdings_index)
total_funds = len(holdings_index)
total_stocks = len(stock_map)

st.markdown(f"<p style='color:#888; font-size:13px;'>Covering <b>{total_funds}</b> funds · <b>{total_stocks:,}</b> unique stocks & instruments</p>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

query = st.text_input(
    label="stock_search",
    placeholder="🔍 Search a stock — e.g. Zomato, Infosys, Copper, HDFC Bank...",
    label_visibility="collapsed"
)

if not query:
    st.stop()

# ── Search ────────────────────────────────────────────────────────────────────
matched_stocks = search_stocks(query, stock_map)

if not matched_stocks:
    st.warning(f"No stocks found matching **{query}**. Try a different name.")
    st.stop()

# If exact or near-exact match exists, use it directly
exact = query.lower()
if exact in stock_map:
    selected_stock = exact
else:
    selected_stock = matched_stocks[0]

# If multiple matches, let user pick
if len(matched_stocks) > 1:
    display_names = [stock_map[s][0]["stock_display"] for s in matched_stocks]
    chosen = st.selectbox(
        "Did you mean:",
        options=matched_stocks,
        format_func=lambda s: stock_map[s][0]["stock_display"],
        index=0
    )
    selected_stock = chosen

# ── Results ───────────────────────────────────────────────────────────────────
results = stock_map[selected_stock]
stock_display_name = results[0]["stock_display"]

st.divider()
st.subheader(f"Funds holding **{stock_display_name}**")
st.caption(f"{len(results)} fund{'s' if len(results) != 1 else ''} found · sorted by allocation")

st.markdown("<br>", unsafe_allow_html=True)

# Bar chart
import pandas as pd

chart_data = pd.DataFrame([
    {
        "Fund": r["fund_name"].replace("Fund", "").strip()[:45],
        "Weight (%)": r["weight_float"]
    }
    for r in results if r["weight_float"] > 0
]).head(15)  # cap at 15 for readability

if not chart_data.empty:
    st.bar_chart(chart_data.set_index("Fund"), height=320)
    st.markdown("<br>", unsafe_allow_html=True)

# Fund cards
for r in results:
    weight_color = "#00ff88" if r["weight_float"] >= 3 else "#f0c040" if r["weight_float"] >= 1 else "#888"

    st.markdown(f"""
    <div style='
        background: #1a1a1a;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        border-left: 4px solid {weight_color};
        display: flex;
        justify-content: space-between;
        align-items: center;
    '>
        <div>
            <div style='font-size: 15px; font-weight: 600; color: #fff;'>{r["fund_name"]}</div>
            <div style='font-size: 12px; color: #888; margin-top: 3px;'>{r["amc"]} · {r["category"] or "—"}</div>
        </div>
        <div style='text-align: right;'>
            <div style='font-size: 20px; font-weight: bold; color: {weight_color};'>{r["weight_str"]}</div>
            <div style='font-size: 11px; color: #555;'>of portfolio</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
