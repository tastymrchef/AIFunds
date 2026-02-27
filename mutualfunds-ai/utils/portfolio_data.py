import requests
import pandas as pd
import io
import time

def get_portfolio_holdings(scheme_name, fund_house):
    """
    Downloads AMFI monthly portfolio Excel and extracts holdings
    for a specific fund
    """
    # AMFI monthly portfolio Excel URL pattern
    url = "https://portal.amfiindia.com/spages/amjan2026repo.xls"
    
    try:
        print(f"Downloading AMFI portfolio data...")
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            return None
        
        # Read Excel file
        df = pd.read_excel(io.BytesIO(response.content), header=None)
        
        print(f"Downloaded. Shape: {df.shape}")
        print(df.head(5))

        df.to_csv("amfi_portfolio.csv", index=False)  # Save raw data for inspection
        
        return df
    
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    df = get_portfolio_holdings("Parag Parikh Flexi Cap", "PPFAS")
    if df is not None:
        print("Successfully retrieved portfolio data")
    else:
        print("Failed to retrieve portfolio data")