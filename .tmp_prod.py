import httpx

BASE = "https://email-orchestrator-agent.vercel.app"
AUTH = ("surbhi", "RVUy4rN83XlquXTfFv3ZRAOh")

print("--- templates on production ---")
r = httpx.get(BASE + "/api/templates", auth=AUTH, timeout=90)
for t in r.json().get("templates", []):
    print(f"  id={t['id']} category={t['category']!r} name={t['name']!r}")

print("\n--- categories ---")
print(" ", httpx.get(BASE + "/api/templates/categories", auth=AUTH, timeout=90).json())

print("\n--- agents status ---")
r = httpx.get(BASE + "/api/agents/status", auth=AUTH, timeout=90)
print(" ", r.status_code, list(r.json().keys()))

print("\n--- analytics (real, from state) ---")
state = httpx.get(BASE + "/api/state", auth=AUTH, timeout=90).json()
print("  ", state.get("analytics"))