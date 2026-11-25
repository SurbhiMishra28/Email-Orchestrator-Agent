import json
import os

import httpx

AUTH = os.path.join(os.environ["APPDATA"], "com.vercel.cli", "Data", "auth.json")
TOKEN = json.load(open(AUTH, encoding="utf-8"))["token"]
CFG = json.load(
    open(os.path.join(os.environ["APPDATA"], "com.vercel.cli", "Data", "config.json"), encoding="utf-8")
)
TEAM = CFG.get("currentTeam") or "surbhi-mishras-projects"
H = {"Authorization": f"Bearer {TOKEN}"}

r = httpx.get(
    "https://api.vercel.com/v6/deployments",
    params={"projectId": "prj_a1ZFXUsU0Ijy1nuDZLmWDS781fOc", "teamId": TEAM, "limit": 3},
    headers=H,
    timeout=60,
)
for dep in r.json().get("deployments", []):
    print(dep.get("uid"), dep.get("state"), dep.get("createdAt"), dep.get("meta", {}).get("githubCommitSha", "")[:7], dep.get("url"))