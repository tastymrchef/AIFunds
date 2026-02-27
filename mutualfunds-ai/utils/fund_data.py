import os
import pandas as pd
import requests
from datetime import datetime, timedelta
import yfinance as yf

schema_code = "100033"  # Example scheme code for HDFC Equity Fund - Regular Plan - Growth Option

def search_funds(query):
    url = "https://api.mfapi.in/mf/search"
    response = requests.get(url, params={"q": query})
    return response.json()

def get_fund_data(scheme_code):
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    response = requests.get(url)
    return response.json()

def calculate_returns(nav_data):
    def get_nav_on(days_ago):
        target = datetime.today() - timedelta(days=days_ago)
        for entry in nav_data:
            entry_date = datetime.strptime(entry["date"], "%d-%m-%Y")
            if entry_date <= target:
                return float(entry["nav"])
        return None

    current_nav = float(nav_data[0]["nav"])
    returns = {}
    
    for label, days in [("1 Year", 365), ("3 Year", 1095), ("5 Year", 1825), ("10 Year", 3650)]:
        nav = get_nav_on(days)
        if nav:
            returns[label] = round(((current_nav - nav) / nav) * 100, 2)
    
    return returns


def get_nifty_data(start_date, end_date):
    nifty = yf.download("^NSEI", start=start_date, end=end_date, progress=False)
    nifty = nifty["Close"].reset_index()
    nifty.columns = ["date", "nifty_close"]
    return nifty


def calculate_nifty_returns(nifty_df):
    def get_nifty_return(days):
        target = datetime.today() - timedelta(days=days)
        nifty_df["date"] = pd.to_datetime(nifty_df["date"])
        filtered = nifty_df[nifty_df["date"] <= target]
        if filtered.empty:
            return None
        old_value = filtered.iloc[-1]["nifty_close"]
        current_value = nifty_df.iloc[-1]["nifty_close"]
        return round(((current_value - old_value) / old_value) * 100, 2)
    print(nifty_df.columns)
    print(nifty_df.head())
    returns = {}
    for label, days in [("1 Year", 365), ("3 Year", 1095), ("5 Year", 1825), ("10 Year", 3650)]:
        returns[label] = get_nifty_return(days)
    return returns