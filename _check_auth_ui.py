import json
import sys
import uuid

from playwright.sync_api import sync_playwright

URL = "https://email-orchestrator-agent.onrender.com"

console_errors = []
page_errors = []
failed = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("requestfailed", lambda r: failed.append(f"{r.url} {r.failure}"))

    page.goto(URL, wait_until="networkidle", timeout=120000)
    page.wait_for_timeout(2000)
    print(json.dumps({"step": "landing", "text": page.inner_text("body")[:220].replace("\n", " | ")}))

    has_password = page.locator("input[type=password]").count() > 0
    print(json.dumps({"step": "signin_screen_shown", "value": has_password}))

    if has_password:
        page.get_by_role("button", name="Create a workspace").click()
        page.wait_for_timeout(800)
        suffix = uuid.uuid4().hex[:8]
        page.locator("input[type=email]").fill(f"owner-{suffix}@example.com")
        inputs = page.locator("input[type=text]")
        for i in range(inputs.count()):
            inputs.nth(i).fill("Deploy Owner" if i == 0 else f"Tenant {suffix}")
        page.locator("input[type=password]").fill("Deploy-pass-12345")
        page.get_by_role("button", name="Create workspace").last.click()
        page.wait_for_timeout(6000)
        heading = page.locator("h1, h2").first
        title = heading.inner_text(timeout=15000).strip() if heading.count() else ""
        print(json.dumps({"step": "after_register", "heading": title}))
        print(
            json.dumps(
                {
                    "step": "body",
                    "text": page.inner_text("body")[:200].replace("\n", " | "),
                }
            )
        )

    browser.close()

print(json.dumps({"console_errors": console_errors, "page_errors": page_errors, "failed_requests": failed}, indent=1))
