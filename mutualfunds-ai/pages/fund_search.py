from utils.fund_data import search_funds, get_fund_data, calculate_returns, get_nifty_data, calculate_nifty_returns
from utils.ai_utils import chat_with_fund, get_ai_summary, get_fund_manager_and_holdings, build_fund_system_prompt
from utils.charts import build_comparison_chart
from utils.clustering import find_similar_funds
from utils.fund_report_agent import get_fund_report

import streamlit as st
import pandas as pd
import requests
import openai
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()  # ensure .env exists in the project root

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Pre-fill search if coming from homepage
default_query = st.session_state.get("home_search", "")

st.set_page_config(page_title="Mutual Funds AI Assistant", page_icon="💰", layout="wide")
st.title("Mutual Funds AI Assistant")
st.caption("Get insights on any Indian mutual fund with intelligent analysis")

query = st.text_input(
    "Search for a mutual fund",
    value=default_query,
    placeholder="e.g. HDFC Large Cap, SBI Bluechip..."
)

if query:

    with st.spinner("Searching for funds..."):
        search_results = search_funds(query)

    if not search_results:
        st.warning("No funds found. Try a different query.")
    else:
        fund_names = [f"{r['schemeName']}" for r in search_results[:10]]
        selected = st.selectbox("Select a fund", fund_names)
        
        selected_code = search_results[fund_names.index(selected)]["schemeCode"]

        if st.button("Analyze Fund"):
            with st.spinner("Fetching fund data..."):
                fund = get_fund_data(selected_code)
                st.session_state.meta = fund["meta"]
                st.session_state.nav_data = fund["data"]
                st.session_state.returns = calculate_returns(fund["data"])

            with st.spinner("Generating AI summary for you..."):
                st.session_state.summary = get_ai_summary(
                    st.session_state.meta,
                    st.session_state.returns
                )

        if "nav_data" in st.session_state:
            meta = st.session_state.meta
            nav_data = st.session_state.nav_data
            returns = st.session_state.returns
            summary = st.session_state.summary

            st.subheader(meta["scheme_name"])
            st.caption(f"{meta['fund_house']} • {meta['scheme_category']}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Current NAV", f"₹{nav_data[0]['nav']}")
    

            st.divider()
            st.subheader("AI Summary")
            st.write(summary)

            st.divider()
            st.subheader("Performance vs Nifty 50")
            st.caption("Both normalized to ₹100 at start of selected period")

            period = st.radio(
                "Select period",
                ["Max", "10Y", "5Y", "3Y", "1Y"],
                horizontal=True,
                index=0
            )

            chart, nifty_df = build_comparison_chart(nav_data, meta["scheme_name"], period=period)
            st.plotly_chart(chart, use_container_width=True)

            st.divider()
            st.subheader("Returns Comparison")


            nifty_full_start = datetime.today() - timedelta(days=3650)  # 10 years
            nifty_full_df = get_nifty_data(nifty_full_start, datetime.today())
            nifty_full_df.columns = ["date", "value"]
            nifty_returns = calculate_nifty_returns(nifty_full_df)
            

            comparison_data = {
                "Period": ["1 Year", "3 Year", "5 Year", "10 Year"],
                "Fund Return (%)": [returns.get(p) for p in ["1 Year", "3 Year", "5 Year", "10 Year"]],
                "Nifty 50 (%)": [nifty_returns.get(p) for p in ["1 Year", "3 Year", "5 Year", "10 Year"]],
            }

            comparison_df = pd.DataFrame(comparison_data)
            comparison_df["Fund Return (%)"] = pd.to_numeric(comparison_df["Fund Return (%)"], errors="coerce")
            comparison_df["Nifty 50 (%)"] = pd.to_numeric(comparison_df["Nifty 50 (%)"], errors="coerce")
            comparison_df["Outperformance (%)"] = (
                comparison_df["Fund Return (%)"] - comparison_df["Nifty 50 (%)"]
            ).round(2)

            

            st.dataframe(
                comparison_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fund Return (%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "Nifty 50 (%)": st.column_config.NumberColumn(format="%.2f%%"),
                    "Outperformance (%)": st.column_config.NumberColumn(format="%.2f%%"),
                }
            )


            st.divider()
            st.subheader("🔍 Similar Funds")
            st.caption("Funds with similar return profile and risk characteristics")

            target_fund, similar_funds = find_similar_funds(selected_code)

            if not similar_funds:
                st.info("Not enough funds in this category for similarity analysis yet.")
            else:
                cols = st.columns(len(similar_funds))
                for col, fund in zip(cols, similar_funds):
                    with col:
                        return_1y = fund["returns"].get("1y")
                        return_color = "#00ff88" if return_1y and return_1y > 0 else "#ff4444"
                        border_color = "#555555" if fund["similarity_score"] < 50 else return_color
                        similarity_note = "⚠ Limited similarity" if fund["similarity_score"] < 50 else f"Similarity: {fund['similarity_score']}%"
                        similarity_color = "#888888" if fund["similarity_score"] < 50 else "#4da6ff"
                                                
                        st.markdown(f"""
                        <div style='
                            background: #1a1a1a;
                            border-radius: 8px;
                            padding: 14px;
                            border-left: 3px solid {border_color};
                            height: 100%;
                        '>
                            <div style='font-size: 11px; color: #888; margin-bottom: 6px;'>{fund["fund_house"]}</div>
                            <div style='font-size: 13px; color: white; font-weight: bold; margin-bottom: 10px;'>{fund["name"][:50]}...</div>
                            <div style='display: flex; justify-content: space-between; margin-bottom: 4px;'>
                                <span style='color: #888; font-size: 12px;'>1Y Return</span>
                                <span style='color: {return_color}; font-size: 13px; font-weight: bold;'>{return_1y}%</span>
                            </div>
                            <div style='display: flex; justify-content: space-between; margin-bottom: 4px;'>
                                <span style='color: #888; font-size: 12px;'>Volatility</span>
                                <span style='color: white; font-size: 12px;'>{fund["volatility"]}%</span>
                            </div>
                            <div style='display: flex; justify-content: space-between; margin-bottom: 8px;'>
                                <span style='color: #888; font-size: 12px;'>Max Drawdown</span>
                                <span style='color: #ff9944; font-size: 12px;'>{fund["max_drawdown"]}%</span>
                            </div>
                            <div style='text-align: center; background: #2a2a2a; border-radius: 4px; padding: 4px;'>
                                <span style='color: {similarity_color}; font-size: 11px;'>{similarity_note}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)



            st.divider()
            st.subheader("Fund Manager")

            with st.spinner("Fetching fund factsheet..."):
                report = get_fund_report(
                    scheme_code=selected_code,
                    fund_house=meta["fund_house"],
                    scheme_name=meta["scheme_name"]
                )
                
                if report:
                    st.session_state.manager_info = report
                    st.subheader("📄 Fund Report")
                    st.text(report)
                else:
                    # Fall back to web search if report agent fails
                    manager_info = get_fund_manager_and_holdings(
                        meta["fund_house"],
                        meta["scheme_name"]
                    )
                    st.session_state.manager_info = manager_info
                    st.write(manager_info)

            st.divider()
            st.subheader("💬 Ask Anything About This Fund")
            st.caption("Powered by AI — ask about performance, risk, fund manager, suitability, or anything else")

            # Reset chat if a new fund is loaded
            current_fund = meta["scheme_name"]
            if st.session_state.get("current_fund") != current_fund:
                st.session_state.chat_messages = []
                st.session_state.current_fund = current_fund
                st.session_state.fund_system_prompt = build_fund_system_prompt(
                    meta,
                    nav_data,
                    returns,
                    st.session_state.get("manager_info", "Not available")
                )

            # Initialize chat history in session state
            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []

            if "fund_system_prompt" not in st.session_state:
                st.session_state.fund_system_prompt = build_fund_system_prompt(
                    meta,
                    nav_data,
                    returns,
                    st.session_state.get("manager_info", "Not available")
                )

            # Display chat history
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            # Chat input
            user_input = st.chat_input("Ask something about this fund...")

            if user_input:
                # Add user message to history
                st.session_state.chat_messages.append({
                    "role": "user",
                    "content": user_input
                })
                
                # Build full message list with system prompt
                messages = [
                    {"role": "system", "content": st.session_state.fund_system_prompt}
                ] + st.session_state.chat_messages
                
                # Get AI response
                with st.spinner("Thinking..."):
                    response = chat_with_fund(messages)
                
                # Add response to history
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response
                })
                
                st.rerun()