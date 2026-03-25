import pandas as pd
import numpy as np
from scripts.adapter import qmt_to_akshare
from scripts.finance_fetcher import fetch_fundamental_data

def run_radar_pipeline(qmt_tick_data):
    """
    Main entry point for the stock radar logic.
    """
    df_tick = qmt_to_akshare(qmt_tick_data)
    df_fundamentals = fetch_fundamental_data()
    
    df = pd.merge(df_tick, df_fundamentals, on='代码', how='left')
    
    filtered = df[df["市盈率-动态"] < 20]
    return filtered
