#!/usr/bin/env python3
"""Real (visible) capture sequence: abre Chromium, hace login y captura varias pantallas/viewport.

Uso: & .\.venv\Scripts\python.exe .\analisis-ventas-ia\scripts\real_capture_sequence.py
"""
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
OUT_DIR = SCRIPTS / 'real_shots'
OUT_DIR.mkdir(parents=True, exist_ok=True)
CONSOLE_LOG = SCRIPTS / 'console_real_sequence.txt'

URL = 'http://localhost:5000'
USER = 'admin'
PASS = 'Admin123!'

def run_sequence():
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except Exception as e:
        print('Playwright no está disponible en este entorno:', e)
        raise

    console_lines = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width':1280, 'height':720})
        page = context.new_page()

        page.on('console', lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))

        print('Navegando a', URL)
        try:
            page.goto(URL, wait_until='networkidle', timeout=20000)
        except PWTimeout:
            print('Timeout al navegar a la app; sigue intentando...')

        # Try login if login inputs present
        try:
            if page.locator('#username').count() > 0:
                page.fill('#username', USER)
            if page.locator('#password').count() > 0:
                page.fill('#password', PASS)
            # submit
            if page.locator('button[type=submit]').count() > 0:
                page.click('button[type=submit]')
                page.wait_for_timeout(1200)
        except Exception as e:
            print('No se pudo completar login automáticamente:', e)

        # give app time to reveal shell
        page.wait_for_timeout(1200)

        # Pages to visit (data-page attribute used in nav links)
        pages = [
            ('dashboard', 'dashboard'),
            ('sales', 'sales'),
            ('products', 'products'),
            ('reports', 'reports'),
            ('statistics', 'statistics'),
            ('account', 'account')
        ]

        # Desktop captures
        for name, pid in pages:
            print('Capturando (desktop):', name)
            # try click nav link
            try:
                sel = f'a[data-page="{pid}"]'
                if page.locator(sel).count() > 0:
                    page.click(sel)
                else:
                    # fallback: try link text
                    page.locator(f'text="{name.capitalize()}"').first.click()
            except Exception:
                pass
            page.wait_for_timeout(900)
            out = OUT_DIR / f'real_{name}_desktop.png'
            try:
                page.screenshot(path=str(out), full_page=True)
            except Exception:
                page.screenshot(path=str(out))

        # Mobile captures (resize viewport)
        print('Cambiando a viewport móvil 375x812')
        page.set_viewport_size({'width':375, 'height':812})
        page.wait_for_timeout(800)

        for name, pid in pages:
            print('Capturando (mobile):', name)
            try:
                sel = f'a[data-page="{pid}"]'
                if page.locator(sel).count() > 0:
                    page.click(sel)
                else:
                    page.locator(f'text="{name.capitalize()}"').first.click()
            except Exception:
                pass
            page.wait_for_timeout(900)
            out = OUT_DIR / f'real_{name}_mobile.png'
            try:
                page.screenshot(path=str(out), full_page=True)
            except Exception:
                page.screenshot(path=str(out))

        # capture a focused element screenshot (e.g., login card or first metric)
        try:
            if page.locator('.login-card').count() > 0:
                el = page.locator('.login-card').first
                el.screenshot(path=str(OUT_DIR / 'real_login_card.png'))
        except Exception:
            pass

        # save console logs
        with CONSOLE_LOG.open('w', encoding='utf-8') as fh:
            fh.write('\n'.join(console_lines))

        print('Capturas guardadas en', OUT_DIR)
        browser.close()

def main():
    try:
        run_sequence()
    except Exception as e:
        print('Error en secuencia de captura:', e)
        sys.exit(1)

if __name__ == '__main__':
    main()
