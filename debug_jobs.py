import asyncio
import asyncpg
import json

async def check_jobs():
    try:
        conn = await asyncpg.connect('postgresql://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres')

        # Check fetch_jobs table
        jobs = await conn.fetch("SELECT job_id, status, created_at, results, errors, progress FROM fetch_jobs ORDER BY created_at DESC LIMIT 3")
        print("Recent jobs:")
        for job in jobs:
            print(f"  {job['job_id']}: {job['status']} ({job['created_at']})")
            print(f"    results type: {type(job['results'])}, len: {len(job['results']) if job['results'] else 0}")
            print(f"    errors type: {type(job['errors'])}, len: {len(job['errors']) if job['errors'] else 0}")
            print(f"    progress type: {type(job['progress'])}, len: {len(job['progress']) if job['progress'] else 0}")

            # Try to parse results
            if job['results']:
                try:
                    if isinstance(job['results'], str):
                        parsed = json.loads(job['results'])
                    else:
                        parsed = job['results']
                    print(f"    parsed results: {parsed[:200]}...")
                except Exception as e:
                    print(f"    ERROR parsing results: {e}")

        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(check_jobs())