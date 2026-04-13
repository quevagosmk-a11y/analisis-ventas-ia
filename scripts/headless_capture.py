from playwright.sync_api import sync_playwright
import sys

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    screenshot_path = "analisis-ventas-ia/scripts/screenshot.png"
    console_log_path = "analisis-ventas-ia/scripts/console_log.txt"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        logs = []
        def on_console(msg):
            try:
                logs.append(f"{msg.type}: {msg.text}")
            except Exception:
                logs.append(f"console: <unreadable message>")

        page.on("console", on_console)

        # Navigate and wait until network is mostly idle
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        # Full page screenshot
        page.screenshot(path=screenshot_path, full_page=True)

        # Save console logs
        with open(console_log_path, "w", encoding="utf-8") as f:
            if logs:
                for line in logs:
                    f.write(line + "\n")
            else:
                f.write("(no console messages captured during headless run)\n")

        browser.close()
    print(f"Saved screenshot to {screenshot_path}")
    print(f"Saved console log to {console_log_path}")

if __name__ == '__main__':
    main()
