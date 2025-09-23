import requests

# Test individual job status
url = 'http://localhost:8000/v1/fetch/job_20250923_171044_d7f67e'
response = requests.get(url)
print('Individual job status:')
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Job ID: {data["job_id"]}')
    print(f'Status: {data["status"]}')
    print(f'Results: {len(data["results"])} symbols')
    print(f'Duration: {data["duration_seconds"]} seconds')