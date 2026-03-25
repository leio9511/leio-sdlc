import pandas as pd
import akshare as ak

def fetch_fundamental_data() -> pd.DataFrame:
    """
    Fetches real-world fundamental data using a stable endpoint.
    Returns a DataFrame with at least: 代码, 市盈率-动态, 总市值.
    """
    try:
        # Attempt to use the robust endpoint mentioned in PRD
        df = ak.stock_a_indicator_lg(symbol="all")
        if 'pe_ttm' in df.columns:
            df.rename(columns={'pe_ttm': '市盈率-动态', 'total_mv': '总市值', 'code': '代码'}, inplace=True)
    except AttributeError:
        # Fallback if the endpoint is not available in the current akshare version
        df = ak.stock_zh_a_spot_em()

    df['代码'] = df['代码'].astype(str)
    
    # Ensure required columns are present
    required = ['代码', '市盈率-动态', '总市值']
    for col in required:
        if col not in df.columns:
            df[col] = None
            
    return df[required]
