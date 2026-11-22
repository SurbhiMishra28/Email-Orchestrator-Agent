import json
import sys

from playwright.sync_api import sync_playwright

URL = "https://email-orchestrator-agent.onrender.com"
VIEWS = [
    "",
    "agents",
    "contacts",
    "templates",
    "campaigns",
    "drafts",
    "experiments",
    "inbox",
    "verifications",
    "automation",
    "team",
    "settings",
]

console_errors = []
page_errors = []
failed_requests = []


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on(
            "requestfailed",
            lambda r: failed_requests.append(f"{r.url} {r.failure}"),
        )

        results = []
        for view in VIEWS:
            target = f"{URL}/{view}" if view else URL
            page.goto(target, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(1200)
            heading = page.locator("h1, h2").first
            title = heading.inner_text(timeout=10000).strip() if heading.count() else ""
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - "
                "document.documentElement.clientWidth"
            )
            body_text = page.inner_text("body")[:160].replace("\n", " | ")
            results.append(
                {
                    "view": view or "(root)",
                    "heading": title,
                    "overflow": overflow,
                    "snippet": body_text,
                }
            )
            print(json.dumps(results[-1], ensure_ascii=False))

        # Mobile drawer check
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1200)
        mobile_overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - "
            "document.documentElement.clientWidth"
        )
        print(json.dumps({"view": "root@390", "overflow": mobile_overflow}))

        browser.close()

    print(
        json.dumps(
            {
                "console_errors": console_errors,
                "page_errors": page_errors,
                "failed_requests": failed_requests,
            },
            indent=1,
        )
    )
    return 1 if (console_errors or page_errors or failed_requests) else 0


sys.exit(main())
