from playwright.sync_api import sync_playwright
import json

OUT_DIR = "analisis-ventas-ia/scripts"

def main(url="http://localhost:5000"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Create context that records HAR
        context = browser.new_context(record_har_path=f"{OUT_DIR}/network.har")

        # Start tracing (performance)
        context.tracing.start(screenshots=True, snapshots=True)

        page = context.new_page()
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))

        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        # Save a screenshot (full-page) as an extra artifact
        page.screenshot(path=f"{OUT_DIR}/screenshot-har.png", full_page=True)

        # Accessibility snapshot
        try:
            a11y = page.accessibility.snapshot()
            with open(f"{OUT_DIR}/a11y_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(a11y, f, indent=2, ensure_ascii=False)
        except Exception as e:
            with open(f"{OUT_DIR}/a11y_snapshot.json", "w", encoding="utf-8") as f:
                json.dump({"error": str(e)}, f)

        # Stop tracing and save
        context.tracing.stop(path=f"{OUT_DIR}/trace.zip")

        # Close context and browser
        context.close()
        browser.close()

        # Save console messages
        with open(f"{OUT_DIR}/console_for_har.txt", "w", encoding="utf-8") as f:
            if console_messages:
                for line in console_messages:
                    f.write(line + "\n")
            else:
                f.write("(no console messages captured during HAR run)\n")

        print("Saved network.har, trace.zip, a11y_snapshot.json, console_for_har.txt, screenshot-har.png")

if __name__ == '__main__':
    main()
