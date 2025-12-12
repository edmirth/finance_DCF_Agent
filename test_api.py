"""
Test script to debug Financial Datasets API responses
"""
import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

API_KEY = os.getenv("FINANCIAL_DATASETS_API_KEY")
BASE_URL = "https://api.financialdatasets.ai"

headers = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

print("=" * 80)
print("Testing Financial Datasets API")
print("=" * 80)
print(f"API Key: {API_KEY[:20]}..." if API_KEY else "No API Key Found")
print()

# Test 1: Company Facts
print("1. Testing /company/facts endpoint:")
print("-" * 80)
try:
    response = requests.get(
        f"{BASE_URL}/company/facts",
        headers=headers,
        params={"ticker": "AAPL"},
        timeout=30
    )
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
except Exception as e:
    print(f"Error: {e}")

print("\n")

# Test 2: Financial Metrics
print("2. Testing /financial-metrics endpoint:")
print("-" * 80)
try:
    response = requests.get(
        f"{BASE_URL}/financial-metrics",
        headers=headers,
        params={"ticker": "AAPL", "period": "ttm", "limit": 1},
        timeout=30
    )
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Response Type: {type(data)}")
    print(f"Response: {json.dumps(data, indent=2)}")
except Exception as e:
    print(f"Error: {e}")

print("\n")

# Test 3: Financials
print("3. Testing /financials endpoint:")
print("-" * 80)
try:
    response = requests.get(
        f"{BASE_URL}/financials",
        headers=headers,
        params={"ticker": "AAPL", "period": "annual", "limit": 5},
        timeout=30
    )
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Response Type: {type(data)}")
    print(f"Keys in response: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
    print(f"\nFull Response:\n{json.dumps(data, indent=2)}")

    if isinstance(data, dict):
        for key in data.keys():
            item_count = len(data[key]) if isinstance(data[key], list) else 'Not a list'
            print(f"\n{key}: {item_count} items")
            if isinstance(data[key], list) and data[key] and len(data[key]) > 0:
                print(f"First item type: {type(data[key][0])}")
                if isinstance(data[key][0], dict):
                    print(f"First item keys: {list(data[key][0].keys())[:10]}")  # First 10 keys
                print(f"Sample data: {json.dumps(data[key][0], indent=2)[:1000]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 80)
