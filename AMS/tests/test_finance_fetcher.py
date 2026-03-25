import pytest
import pandas as pd
from unittest.mock import patch
from scripts.finance_fetcher import fetch_fundamental_data

@patch('scripts.finance_fetcher.ak.stock_zh_a_spot_em')
def test_fetch_fundamental_data_returns_required_columns(mock_spot_em):
    # Mocking the response of stock_zh_a_spot_em to prevent network fragility
    mock_df = pd.DataFrame([
        {'代码': '000001', '市盈率-动态': 5.6, '总市值': 120000000},
        {'代码': '000002', '市盈率-动态': 8.9, '总市值': 340000000},
        {'代码': '600000', '市盈率-动态': 15.0, '总市值': 550000000}
    ])
    mock_spot_em.return_value = mock_df
    
    df = fetch_fundamental_data()
    
    # Assert DataFrame has required structure
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert '代码' in df.columns
    assert '市盈率-动态' in df.columns
    assert '总市值' in df.columns
    
    # Assert dynamic and not uniformly hardcoded to 15.0
    pe_values = df['市盈率-动态'].dropna()
    assert len(pe_values) == 3
    assert pe_values.nunique() > 1, "PE values are uniform, indicating hardcoded fake data!"
    
    # Check that values mapped correctly
    assert df.loc[df['代码'] == '000001', '市盈率-动态'].values[0] == 5.6
    assert df.loc[df['代码'] == '000002', '总市值'].values[0] == 340000000
