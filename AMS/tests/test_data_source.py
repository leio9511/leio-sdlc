import pytest
import pandas as pd
from scripts.adapter import qmt_to_akshare
from scripts.finance_fetcher import fetch_fundamental_data

def test_qmt_to_akshare_mapping():
    # Mock QMT get_full_tick response
    mock_qmt_data = {
        "600000.SH": {
            "lastPrice": 10.0,
            "open": 9.9,
            "high": 10.1,
            "low": 9.8,
            "close": 10.0,
            "amount": 1000000.0,
            "volume": 1000,
            "stockName": "浦发银行",
            "lastClose": 9.9,
            "askPrice": [10.1, 10.2, 10.3, 10.4, 10.5],
            "bidPrice": [10.0, 9.9, 9.8, 9.7, 9.6],
            "askVol": [100, 100, 100, 100, 100],
            "bidVol": [100, 100, 100, 100, 100]
        }
    }
    
    df = qmt_to_akshare(mock_qmt_data)
    
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert '代码' in df.columns
    assert df.iloc[0]['代码'] == '600000'
    assert df.iloc[0]['名称'] == '浦发银行'
    assert df.iloc[0]['最新价'] == 10.0
    assert df.iloc[0]['昨收'] == 9.9
    assert abs(df.iloc[0]['涨跌幅'] - (0.1 / 9.9 * 100)) < 0.0001
    assert abs(df.iloc[0]['涨跌额'] - 0.1) < 0.0001
    assert df.iloc[0]['成交量'] == 1000
    assert df.iloc[0]['成交额'] == 1000000.0
    assert df.iloc[0]['最高'] == 10.1
    assert df.iloc[0]['最低'] == 9.8
    assert df.iloc[0]['今开'] == 9.9

from unittest.mock import patch

@patch('scripts.finance_fetcher.fetch_fundamental_data')
def test_full_merge_process(mock_fetch):
    from scripts.pilot_stock_radar import run_radar_pipeline
    mock_fund_df = pd.DataFrame([
        {'代码': '600000', '市盈率-动态': 12.5, '总市值': 100000000}
    ])
    mock_fetch.return_value = mock_fund_df
    
    mock_qmt_data = {
        "600000.SH": {
            "lastPrice": 10.0,
            "stockName": "浦发银行"
        }
    }
    
    merged_df = run_radar_pipeline(mock_qmt_data)
    
    assert '市盈率-动态' in merged_df.columns
    assert '总市值' in merged_df.columns
    assert merged_df.iloc[0]['市盈率-动态'] == 12.5
    assert merged_df.iloc[0]['市盈率-动态'] != 15.0
