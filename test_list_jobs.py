import requests

url = 'http://localhost:8000/v1/fetch'
response = requests.get(url)
print('Status:', response.status_code)
if response.status_code == 200:
    data = response.json()
    print('Total jobs:', data['total'])
    print('Jobs returned:', len(data['jobs']))
    for job in data['jobs'][:2]:  # Show first 2 jobs
        print(f'  {job["job_id"]}: {job["status"]} ({len(job["results"])} results)')
else:
    print('Error:', response.text)