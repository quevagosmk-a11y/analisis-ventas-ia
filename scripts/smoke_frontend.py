from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba de humo del frontend con login y modulos clave."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000/"),
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("SMOKE_ADMIN_USER", "admin"),
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SMOKE_ADMIN_PASSWORD")
        or os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin2026@"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("SMOKE_OUTPUT_DIR", "artifacts/smoke"),
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(
            "[smoke] Playwright no disponible. Instala con `pip install playwright` "
            "y luego ejecuta `playwright install chromium`.",
            file=sys.stderr,
        )
        print(f"[smoke] detalle: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    checks = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            context = browser.new_context()
            page = context.new_page()
            page.goto(args.base_url, wait_until="domcontentloaded", timeout=30000)

            page.fill("#username", args.user)
            page.fill("#password", args.password)
            page.click('#loginForm button[type="submit"]')
            page.wait_for_selector("#appShell", state="visible", timeout=30000)
            page.wait_for_selector("#salesToday", timeout=30000)
            checks.append("dashboard")

            page.click('[data-page="products"]')
            page.wait_for_selector("#productsTable", timeout=30000)
            checks.append("products")

            if page.locator('[data-page="audit"]').count():
                page.click('[data-page="audit"]')
                page.wait_for_selector("#auditTable", timeout=30000)
                checks.append("audit")

            if page.locator('[data-page="backups"]').count():
                page.click('[data-page="backups"]')
                page.wait_for_selector("#backupsTable", timeout=30000)
                checks.append("backups")

            screenshot_path = output_dir / "frontend-smoke.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            report_path = output_dir / "frontend-smoke.json"
            report_path.write_text(
                json.dumps(
                    {
                        "base_url": args.base_url,
                        "checks": checks,
                        "screenshot": str(screenshot_path),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            print(f"[smoke] ok: {', '.join(checks)}")
            print(f"[smoke] evidencia: {screenshot_path}")
            browser.close()
            return 0
    except PlaywrightTimeoutError as exc:
        print(f"[smoke] timeout: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[smoke] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
