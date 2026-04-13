#!/usr/bin/env python3
"""Genera un PDF con todas las capturas post-login, organizadas y con leyendas claras.

El script crea `report_captions.pdf` en la carpeta `scripts/` y no modifica las imágenes
origen. Usa Playwright para renderizar un HTML responsive que contiene cada imagen con su
caption (página, dispositivo, nombre de archivo). Luego actualiza el ZIP final.

Ejecución:
  & .\.venv\Scripts\python.exe .\analisis-ventas-ia\scripts\generate_captioned_pdf.py
"""
from pathlib import Path
from html import escape
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
REAL_DIR = SCRIPTS / 'real_shots'
OUT_HTML = SCRIPTS / 'report_captions.html'
OUT_PDF = SCRIPTS / 'report_captions.pdf'

DEVICE_MAP = {
    'desktop': 'Desktop (1280×720)',
    'mobile': 'Mobile (375×812)'
}

def gather_images():
    if not REAL_DIR.exists():
        print('No existe', REAL_DIR)
        return []
    imgs = [p for p in REAL_DIR.iterdir() if p.suffix.lower() in ('.png', '.jpg', '.jpeg')]
    def sort_key(p):
        name = p.stem
        # try to order by page name then device
        parts = name.split('_')
        # expected: real_{page}_{device}
        if len(parts) >= 3:
            return (parts[1], parts[2], p.name)
        return (p.name, '')
    return sorted(imgs, key=sort_key)

def build_html(imgs):
    head = '''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capturas - Post-login</title><style>/* Tipografía y espaciado */body{font-family:'Times New Roman',Times,serif;margin:20px;color:#111;line-height:1.5}h1{font-size:18pt;margin-bottom:8px}/* Tarjeta de imagen: evitar que la imagen se corte o solape */.img-card{page-break-inside:avoid;page-break-after:always;break-inside:avoid;display:block;margin-bottom:18px;border:1px solid #e6e6e6;padding:12px;border-radius:6px;background:#fff;overflow:visible;text-align:center}/* Imágenes: centrar y escalar manteniendo proporción; limitar ancho para evitar recortes */img{max-width:820px;width:100%;height:auto;display:block;margin:8px auto;border:1px solid #ddd;box-sizing:border-box}/* Ajustes para impresión/PDF */@media print{img{max-width:760px} .img-card{page-break-after:always}}.caption{font-size:11pt;color:#333;padding:6px 0}.meta{font-size:9pt;color:#666}</style></head><body><h1>Capturas post-login</h1><p>Cada imagen incluye leyenda con la página y el dispositivo.</p><hr>'''
    body = [head]
    if not imgs:
        body.append('<p>No se encontraron capturas en real_shots/</p>')
    else:
        for p in imgs:
            fname = p.name
            stem = p.stem
            parts = stem.split('_')
            page_label = parts[1].capitalize() if len(parts) >= 2 else stem
            device = parts[2] if len(parts) >= 3 else ''
            device_label = DEVICE_MAP.get(device, device)
            body.append('<div class="img-card">')
            body.append(f"<div class=\"caption\"><strong>{escape(page_label)}</strong> — {escape(device_label)}</div>")
            # image tag uses file URI
            uri = p.resolve().as_posix()
            body.append(f"<img src=\"file://{uri}\" alt=\"{escape(fname)}\">")
            body.append(f"<div class=\"meta\">Archivo: {escape(fname)}</div>")
            body.append('</div>')
    body.append('</body></html>')
    OUT_HTML.write_text('\n'.join(body), encoding='utf-8')
    print('Wrote HTML:', OUT_HTML)

def render_pdf():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print('Playwright no disponible:', e)
        raise
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f'file://{OUT_HTML.resolve().as_posix()}')
        page.wait_for_timeout(600)
        page.pdf(path=str(OUT_PDF), format='A4', print_background=True, margin={'top':'20px','bottom':'20px','left':'20px','right':'20px'})
        browser.close()
    print('Wrote PDF:', OUT_PDF)

def main():
    imgs = gather_images()
    build_html(imgs)
    render_pdf()
    # update zip files to include the new PDF
    import subprocess
    cmd = [
        'powershell',
        '-NoProfile',
        '-Command',
        "Compress-Archive -Path .\\analisis-ventas-ia\\scripts\\evidence\\*, .\\analisis-ventas-ia\\scripts\\real_shots\\*, .\\analisis-ventas-ia\\scripts\\report_captions.pdf, .\\analisis-ventas-ia\\scripts\\network.har, .\\analisis-ventas-ia\\scripts\\network_report.json -DestinationPath .\\analisis-ventas-ia\\scripts\\evidence_final_latest.zip -Force; Copy-Item -Path .\\analisis-ventas-ia\\scripts\\evidence_final_latest.zip -Destination .\\analisis-ventas-ia\\scripts\\evidence_final.zip -Force"
    ]
    print('Updating ZIPs...')
    subprocess.run(cmd, check=True)
    print('Updated ZIPs with report_captions.pdf')

if __name__ == '__main__':
    main()
