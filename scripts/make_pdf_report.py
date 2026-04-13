#!/usr/bin/env python3
"""Genera `report.pdf` a partir de `report.md` e incluye capturas del directorio `evidence/`.

Requisitos: Playwright instalado (se usó Playwright en este workspace previamente).
Ejecuta con: `& .\.venv\Scripts\python.exe .\analisis-ventas-ia\scripts\make_pdf_report.py`
"""
from pathlib import Path
from html import escape
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
REPORT_MD = SCRIPTS / 'report.md'
EVIDENCE_DIR = SCRIPTS / 'evidence'
REAL_SHOTS_DIR = SCRIPTS / 'real_shots'
OUT_HTML = SCRIPTS / 'report_for_pdf.html'
OUT_PDF = SCRIPTS / 'report.pdf'
OUT_ZIP = SCRIPTS / 'evidence_final.zip'

def build_html():
    md_text = REPORT_MD.read_text(encoding='utf-8') if REPORT_MD.exists() else ''
    imgs = []
    # include screenshots from evidence/ and real_shots/
    if EVIDENCE_DIR.exists():
        imgs.extend([p for p in EVIDENCE_DIR.rglob('*.png')])
    if REAL_SHOTS_DIR.exists():
        imgs.extend([p for p in REAL_SHOTS_DIR.rglob('*.png')])
    imgs = sorted(set(imgs))

    body = [
        '<!doctype html>',
        '<html lang="es">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>Informe - La Septima Estrella</title>',
        '<style>body{font-family:Arial,Helvetica,sans-serif;padding:20px;color:#111} h1{font-size:18pt} img{max-width:100%;margin:12px 0;border:1px solid #ddd;padding:4px;background:#fff} pre{white-space:pre-wrap;background:#f8f8f8;padding:12px;border-radius:6px;border:1px solid #eee}</style>',
        '</head>',
        '<body>',
        '<h1>Informe de rendimiento y evidencias</h1>',
        '<p>Incluye capturas y el informe textual.</p>',
        '<hr>'
    ]

    if imgs:
        body.append('<h2>Capturas (evidence/)</h2>')
        for img in imgs:
            # Use file:// URI for local file access
            uri = img.resolve().as_posix()
            body.append(f"<div><img src='file://{uri}' alt='{escape(img.name)}'></div>")

    body.append('<hr>')
    body.append('<h2>Informe (report.md)</h2>')
    body.append('<pre>')
    body.append(escape(md_text))
    body.append('</pre>')
    body.append('</body></html>')

    OUT_HTML.write_text('\n'.join(body), encoding='utf-8')
    print(f'Wrote HTML for PDF to: {OUT_HTML}')

def render_pdf_with_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print('Playwright not available in this environment:', e)
        raise

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f'file://{OUT_HTML.resolve().as_posix()}')
        # small wait to ensure images render
        page.wait_for_timeout(800)
        page.pdf(path=str(OUT_PDF), format='A4', print_background=True)
        browser.close()
    print(f'Wrote PDF: {OUT_PDF}')

def build_final_zip():
    files_to_add = []
    if EVIDENCE_DIR.exists():
        for p in EVIDENCE_DIR.rglob('*'):
            if p.is_file():
                files_to_add.append(p)
    if REAL_SHOTS_DIR.exists():
        for p in REAL_SHOTS_DIR.rglob('*'):
            if p.is_file():
                files_to_add.append(p)

    # also include network.har and network_report.json if present
    for extra in ['network.har', 'network_report.json', OUT_PDF.name]:
        p = SCRIPTS / extra
        if p.exists():
            files_to_add.append(p)

    # create zip
    with zipfile.ZipFile(OUT_ZIP, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for f in files_to_add:
            # arcname relative to scripts/
            arc = f.relative_to(SCRIPTS)
            z.write(f, arc.as_posix())
    print(f'Created final zip: {OUT_ZIP} (contains {len(files_to_add)} files)')

def main():
    build_html()
    render_pdf_with_playwright()
    build_final_zip()

if __name__ == '__main__':
    main()
