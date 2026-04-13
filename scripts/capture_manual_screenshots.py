from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura pantallas clave del sistema para manuales."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MANUAL_BASE_URL", "http://127.0.0.1:5000/"),
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("MANUAL_ADMIN_USER", "admin"),
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("MANUAL_ADMIN_PASSWORD")
        or os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin2026@"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get(
            "MANUAL_SCREENSHOT_DIR", "docs/manuales/assets/screenshots"
        ),
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def _capture_locator(page, selector: str, output_path: Path) -> bool:
    locator = page.locator(selector)
    if locator.count() == 0:
        return False
    target = locator.first
    target.wait_for(state="visible", timeout=30000)
    target.scroll_into_view_if_needed(timeout=30000)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target.screenshot(path=str(output_path), timeout=30000)
    return True


def _show_page(page, key: str, wait_selector: Optional[str] = None) -> None:
    page.locator(f'[data-page="{key}"]').first.click()
    if wait_selector:
        page.locator(wait_selector).first.wait_for(state="visible", timeout=30000)
    page.wait_for_timeout(1200)


def main() -> int:
    args = parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(
            "Playwright no disponible. Instala con `pip install playwright` "
            "y luego ejecuta `playwright install chromium`."
        )
        print(f"Detalle: {exc}")
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    report_from = "2026-01-01"
    report_to = today
    captured: Dict[str, str] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context(viewport={"width": 1600, "height": 1100})
        page = context.new_page()
        page.goto(args.base_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)

        if _capture_locator(page, "#loginPage", out_dir / "01_login.png"):
            captured["login"] = str((out_dir / "01_login.png").resolve())

        page.fill("#username", args.user)
        page.fill("#password", args.password)
        page.click('#loginForm button[type="submit"]')
        page.locator("#appShell").first.wait_for(state="visible", timeout=30000)
        page.wait_for_timeout(2000)

        _show_page(page, "dashboard", "#dashboardPage")
        if _capture_locator(page, "#dashboardPage", out_dir / "02_dashboard.png"):
            captured["dashboard"] = str((out_dir / "02_dashboard.png").resolve())

        _show_page(page, "sales", "#salesPage")
        page.wait_for_timeout(2000)
        if _capture_locator(page, "#salesPage", out_dir / "03_sales.png"):
            captured["sales"] = str((out_dir / "03_sales.png").resolve())
        detail_buttons = page.locator('#recentSalesTable [data-action="detail"]')
        if detail_buttons.count() > 0:
            detail_buttons.first.click()
            page.locator("#saleDetailModal.show, #saleDetailModal.modal.show").first.wait_for(
                state="visible", timeout=30000
            )
            page.wait_for_timeout(1000)
            if _capture_locator(
                page, "#saleDetailModal .modal-dialog", out_dir / "04_sale_detail.png"
            ):
                captured["sale_detail"] = str(
                    (out_dir / "04_sale_detail.png").resolve()
                )
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        _show_page(page, "products", "#productsPage")
        page.wait_for_timeout(2000)
        if _capture_locator(page, "#productsPage", out_dir / "05_products.png"):
            captured["products"] = str((out_dir / "05_products.png").resolve())

        _show_page(page, "reports", "#reportsPage")
        page.fill("#reportDateFrom", report_from)
        page.fill("#reportDateTo", report_to)
        page.click("#generateReportBtn")
        page.wait_for_timeout(2500)
        if _capture_locator(page, "#reportsPage", out_dir / "06_reports.png"):
            captured["reports"] = str((out_dir / "06_reports.png").resolve())

        _show_page(page, "statistics", "#statisticsPage")
        page.fill("#statsDateFrom", report_from)
        page.fill("#statsDateTo", report_to)
        page.click("#generateStatsBtn")
        page.wait_for_timeout(2500)
        if _capture_locator(page, "#statisticsPage", out_dir / "07_statistics.png"):
            captured["statistics"] = str((out_dir / "07_statistics.png").resolve())
        if page.locator("#refreshForecastBtn").count():
            page.click("#refreshForecastBtn")
            page.wait_for_timeout(2500)
        if _capture_locator(
            page, ".forecast-card", out_dir / "08_forecast.png"
        ):
            captured["forecast"] = str((out_dir / "08_forecast.png").resolve())

        _show_page(page, "users", "#usersPage")
        page.wait_for_timeout(1500)
        if _capture_locator(page, "#usersPage", out_dir / "09_users.png"):
            captured["users"] = str((out_dir / "09_users.png").resolve())

        _show_page(page, "audit", "#auditPage")
        page.wait_for_timeout(1500)
        if _capture_locator(page, "#auditPage", out_dir / "10_audit.png"):
            captured["audit"] = str((out_dir / "10_audit.png").resolve())

        _show_page(page, "backups", "#backupsPage")
        page.wait_for_timeout(1500)
        if _capture_locator(page, "#backupsPage", out_dir / "11_backups.png"):
            captured["backups"] = str((out_dir / "11_backups.png").resolve())

        _show_page(page, "account", "#accountPage")
        page.wait_for_timeout(1500)
        if _capture_locator(page, "#accountPage", out_dir / "12_account.png"):
            captured["account"] = str((out_dir / "12_account.png").resolve())

        browser.close()

    manifest_path = out_dir / "screenshots_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "base_url": args.base_url,
                "user": args.user,
                "date_from": report_from,
                "date_to": report_to,
                "captured": captured,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Capturas guardadas en: {out_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
