import json
import os
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity

# Always resolve cache relative to the mutualfunds-ai root, not the CWD
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # …/mutualfunds-ai

def load_universe():
    path = os.path.join(_BASE, "cache", "fund_universe.json")
    with open(path, "r") as f:
        cache = json.load(f)
    return cache["data"]

def get_fund_features(fund):
    """Extract numerical features from a fund for clustering"""
    return [
        fund["returns"].get("1y") or 0,
        fund["returns"].get("3y") or 0,
        fund["returns"].get("5y") or 0,
        fund["volatility"] or 0,
        fund["max_drawdown"] or 0,
    ]

def find_similar_funds(scheme_code, top_n=4):
    universe = load_universe()
    
    # Find the target fund
    target_fund = None
    for fund in universe:
        if str(fund["scheme_code"]) == str(scheme_code):
            target_fund = fund
            break
    
    if not target_fund:
        return None, []
    
    # Filter to same sector only
    sector = target_fund["sector"]
    sector_funds = [f for f in universe if f["sector"] == sector]
    
    if len(sector_funds) < 3:
        return target_fund, []
    
    # Build feature matrix
    feature_matrix = np.array([get_fund_features(f) for f in sector_funds])
    
    # Normalize features
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(feature_matrix)
    
    # Find target index in sector funds
    target_idx = None
    for i, f in enumerate(sector_funds):
        if str(f["scheme_code"]) == str(scheme_code):
            target_idx = i
            break
    
    if target_idx is None:
        return target_fund, []
    
    # Calculate cosine similarity
    target_vector = scaled_features[target_idx].reshape(1, -1)
    similarities = cosine_similarity(target_vector, scaled_features)[0]
    
    # Sort by similarity, exclude the fund itself
    similar_indices = np.argsort(similarities)[::-1]
    similar_funds = []
    
    for idx in similar_indices:
        if idx == target_idx:
            continue
        fund = sector_funds[idx]
        similar_funds.append({
            "scheme_code": fund["scheme_code"],
            "name": fund["name"],
            "fund_house": fund["fund_house"],
            "returns": fund["returns"],
            "volatility": fund["volatility"],
            "max_drawdown": fund["max_drawdown"],
            "similarity_score": round(float(similarities[idx]) * 100, 1)
        })
        if len(similar_funds) >= top_n:
            break
    
    return target_fund, similar_funds