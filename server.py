from fastapi import FastAPI

app = FastAPI()

# Mock xtdata for testing purposes if not running in real Windows environment
try:
    from xtquant import xtdata
except ImportError:
    class MockXtData:
        def get_stock_list_in_sector(self, sector):
            if sector == 'a_shares':
                return [f"{str(i).zfill(6)}.SZ" for i in range(5300)]
            return []

        def get_full_tick(self, stock_list):
            return {stock: {"lastPrice": 10.0, "volume": 100} for stock in stock_list}

    xtdata = MockXtData()

@app.get("/api/bulk_quote")
def bulk_quote(chunk_size: int = 500, chunk_index: int = 0):
    all_stocks = xtdata.get_stock_list_in_sector('a_shares')
    total_stocks = len(all_stocks)
    
    start = chunk_index * chunk_size
    end = start + chunk_size
    
    slice_stocks = all_stocks[start:end]
    
    if not slice_stocks:
        data = {}
    else:
        data = xtdata.get_full_tick(slice_stocks)
        
    return {
        "data": data,
        "total_stocks": total_stocks,
        "chunk_index": chunk_index,
        "chunk_size": chunk_size
    }
