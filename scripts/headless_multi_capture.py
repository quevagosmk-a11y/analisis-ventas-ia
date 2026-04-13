from playwright.sync_api import sync_playwright

OUT_DIR = "analisis-ventas-ia/scripts"

def capture_all(url="http://localhost:5000"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Desktop full-page
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        logs = []
        page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        desktop_path = f"{OUT_DIR}/screenshot-desktop.png"
        page.screenshot(path=desktop_path, full_page=True)
        context.close()

        # Mobile emulation
        iphone = p.devices["iPhone 12"]
        context = browser.new_context(**iphone)
        page = context.new_page()
        page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        mobile_path = f"{OUT_DIR}/screenshot-mobile.png"
        page.screenshot(path=mobile_path, full_page=True)
        context.close()

        # Mid resolution
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()
        page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(800)
        mid_path = f"{OUT_DIR}/screenshot-1366x768.png"
        page.screenshot(path=mid_path, full_page=True)
        context.close()

        # Save console logs combined
        console_path = f"{OUT_DIR}/console_log_multi.txt"
        with open(console_path, "w", encoding="utf-8") as f:
            if logs:
                for line in logs:
                    f.write(line + "\n")
            else:
                f.write("(no console messages captured during multi headless run)\n")

        browser.close()
        print("Saved:")
        print(desktop_path)
        print(mobile_path)
        print(mid_path)
        print(console_path)

if __name__ == '__main__':
    capture_all()
