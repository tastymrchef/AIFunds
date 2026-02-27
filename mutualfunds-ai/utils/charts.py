import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from .fund_data import get_nifty_data, calculate_nifty_returns


def build_comparison_chart(nav_data, fund_name, period="Max"):
    df = pd.DataFrame(nav_data)
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"] = df["nav"].astype(float)
    df = df.sort_values("date")

    # Filter based on period
    period_days = {
        "1Y": 365,
        "3Y": 1095,
        "5Y": 1825,
        "10Y": 3650,
        "Max": None
    }

    days = period_days[period]
    if days:
        cutoff = datetime.today() - timedelta(days=days)
        df = df[df["date"] >= cutoff]

    start_date = df["date"].min()
    end_date = df["date"].max()

    # Normalize NAV to 100 at start of selected period
    nav_start = df["nav"].iloc[0]
    df["nav_normalized"] = (df["nav"] / nav_start) * 100

    # Get Nifty for same period
    nifty_df = get_nifty_data(start_date, end_date)
    nifty_df.columns = ["date", "nifty_close"]
    nifty_df["date"] = pd.to_datetime(nifty_df["date"])
    nifty_start = nifty_df["nifty_close"].iloc[0]
    nifty_df["nifty_normalized"] = (nifty_df["nifty_close"] / nifty_start) * 100

    # Build chart — rest stays exactly the same
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["nav_normalized"],
        mode="lines",
        name=fund_name,
        line=dict(color="#00ff88", width=2)
    ))
    fig.add_trace(go.Scatter(
        x=nifty_df["date"],
        y=nifty_df["nifty_normalized"],
        mode="lines",
        name="Nifty 50",
        line=dict(color="#4da6ff", width=2)
    ))

    # Only show anomaly markers on Max view
    if period == "Max":
        anomalies = [
            {"date": "2008-09-15", "label": "2008 Crisis"},
            {"date": "2016-11-08", "label": "Demonetization"},
            {"date": "2020-03-23", "label": "COVID Crash"},
        ]
        for a in anomalies:
            fig.add_vline(
                x=a["date"],
                line_width=1,
                line_dash="dash",
                line_color="rgba(255,255,255,0.3)"
            )
            fig.add_annotation(
                x=a["date"],
                y=95,
                text=a["label"],
                showarrow=False,
                font=dict(color="rgba(255,255,255,0.5)", size=10),
                textangle=-90
            )

    fig.update_layout(
        paper_bgcolor="#0a0a0a",
        plot_bgcolor="#0a0a0a",
        font=dict(color="white"),
        xaxis=dict(showgrid=False, color="white", title="Year"),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.1)",
            color="white",
            title="Growth of ₹100"
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(255,255,255,0.2)",
            borderwidth=1
        ),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig, nifty_df