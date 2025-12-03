"""Test events API endpoints."""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoints():
    """Test all events endpoints."""
    print("Testing Events API Endpoints...")
    print("=" * 50)
    
    # Test 1: GET /v1/events (list events)
    print("\n1. Testing GET /v1/events")
    try:
        response = requests.get(f"{BASE_URL}/v1/events", params={"page": 1, "page_size": 5})
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Total events: {data.get('total', 0)}")
            print(f"   ✓ Page: {data.get('page', 1)}")
        else:
            print(f"   ✗ Error: {response.text}")
    except Exception as e:
        print(f"   ✗ Failed: {str(e)}")
    
    # Test 2: GET /v1/events/pending
    print("\n2. Testing GET /v1/events/pending")
    try:
        response = requests.get(f"{BASE_URL}/v1/events/pending")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Pending events: {len(data)}")
        else:
            print(f"   ✗ Error: {response.text}")
    except Exception as e:
        print(f"   ✗ Failed: {str(e)}")
    
    # Test 3: GET /v1/events/dividends
    print("\n3. Testing GET /v1/events/dividends")
    try:
        response = requests.get(f"{BASE_URL}/v1/events/dividends")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Dividend events: {len(data)}")
        else:
            print(f"   ✗ Error: {response.text}")
    except Exception as e:
        print(f"   ✗ Failed: {str(e)}")
    
    # Test 4: GET /v1/events/splits
    print("\n4. Testing GET /v1/events/splits")
    try:
        response = requests.get(f"{BASE_URL}/v1/events/splits")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Split events: {len(data)}")
        else:
            print(f"   ✗ Error: {response.text}")
    except Exception as e:
        print(f"   ✗ Failed: {str(e)}")
    
    # Test 5: GET /v1/health (health check)
    print("\n5. Testing GET /v1/health")
    try:
        response = requests.get(f"{BASE_URL}/v1/health")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Service: {data.get('service', 'unknown')}")
            print(f"   ✓ Status: {data.get('status', 'unknown')}")
        else:
            print(f"   ✗ Error: {response.text}")
    except Exception as e:
        print(f"   ✗ Failed: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ API endpoint tests completed!")

if __name__ == "__main__":
    test_endpoints()
