from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from server import app

client = TestClient(app)

def test_bulk_quote_pagination():
    response = client.get("/api/bulk_quote?chunk_size=100&chunk_index=0")
    assert response.status_code == 200
    json_data = response.json()
    
    assert "data" in json_data
    assert "total_stocks" in json_data
    assert "chunk_index" in json_data
    assert "chunk_size" in json_data
    
    assert json_data["chunk_index"] == 0
    assert json_data["chunk_size"] == 100
    assert len(json_data["data"]) == 100
    assert json_data["total_stocks"] == 5300

def test_bulk_quote_out_of_bounds():
    response = client.get("/api/bulk_quote?chunk_size=100&chunk_index=1000")
    assert response.status_code == 200
    json_data = response.json()
    
    assert len(json_data["data"]) == 0
    assert json_data["total_stocks"] == 5300
    assert json_data["chunk_index"] == 1000
    assert json_data["chunk_size"] == 100
