import urllib.request
import json
import time

def fetch(url, method="GET", headers={}, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8') if data else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.dumps(json.loads(response.read().decode()), indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps(json.loads(e.read().decode()), indent=2)

print("--- 0. Seeding Demo User (Getting JWT) ---")
req = urllib.request.Request("http://localhost:8000/dev/seed", method="POST")
with urllib.request.urlopen(req) as response:
    seed = json.loads(response.read().decode())
token = seed["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print(f"Token obtained (starts with): {token[:40]}...")

print("\n--- 1. Tier 1: /health ---")
print(fetch("http://localhost:8000/health"))

print("\n--- 2. Tier 1: /me ---")
print(fetch("http://localhost:8000/me", headers=headers))

print("\n--- 3. Tier 1: /credits/balance ---")
print(fetch("http://localhost:8000/credits/balance", headers=headers))

print("\n--- 4. Tier 2: /api/analyse (Positive Text) ---")
print(fetch("http://localhost:8000/api/analyse", method="POST", headers=headers, data={"text": "I absolutely love this amazing new product! It is genuinely fantastic and makes me incredibly happy."}))

print("\n--- 5. Tier 2: /api/analyse (Negative Text) ---")
print(fetch("http://localhost:8000/api/analyse", method="POST", headers=headers, data={"text": "This is the worst experience of my life. It is absolutely terrible, frustrating, and a complete waste of time."}))

print("\n--- 6. Tier 2: /api/summarise (Async) ---")
job_str = fetch("http://localhost:8000/api/summarise", method="POST", headers=headers, data={"text": "NexusAPI is a production-grade backend platform built with FastAPI and PostgreSQL. Every user belongs to one organisation, and data from one organisation must never be visible to another. This multi-tenant isolation is strictly enforced at the database query level."})
print(job_str)

job = json.loads(job_str)
job_id = job.get("job_id")
if job_id:
    print("\n[Waiting 2 seconds for Redis ARQ worker to process...]")
    time.sleep(2)
    print(f"\n--- 7. Tier 2: /api/jobs/{job_id} (Polling) ---")
    print(fetch(f"http://localhost:8000/api/jobs/{job_id}", headers=headers))
