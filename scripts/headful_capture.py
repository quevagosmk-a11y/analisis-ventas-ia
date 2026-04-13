from playwright.sync_api import sync_playwright
import time

OUT_DIR = "analisis-ventas-ia/scripts"

def main(url="http://localhost:5000"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        logs = []
        page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))

        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(1)

        desktop_path = f"{OUT_DIR}/screenshot-real-desktop.png"
        page.screenshot(path=desktop_path, full_page=True)

        # Resize to mobile-like viewport and capture
        try:
            page.set_viewport_size({"width": 375, "height": 812})
        except Exception:
            # Some browsers may not allow resizing; open a new context instead
            context.close()
            context = browser.new_context(viewport={"width": 375, "height": 812}, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1")
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(1)

        mobile_path = f"{OUT_DIR}/screenshot-real-mobile.png"
        page.screenshot(path=mobile_path, full_page=True)

        # Save console logs
        console_path = f"{OUT_DIR}/console_real.txt"
        with open(console_path, "w", encoding="utf-8") as f:
            if logs:
                for line in logs:
                    f.write(line + "\n")
            else:
                f.write("(no console messages captured during headful run)\n")

        # Give user time to see the browser before closing
        time.sleep(1)
        browser.close()
        print("Saved:")
        print(desktop_path)
        print(mobile_path)
        print(console_path)

if __name__ == '__main__':
    main()
