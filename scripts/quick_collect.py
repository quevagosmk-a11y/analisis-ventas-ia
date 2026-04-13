#!/usr/bin/env python3
"""Quick collector seguro.

Mejoras:
- Normaliza URLs (quita fragmentos) para evitar repetir la misma petición con `#...`.
- Límite máximo de requests (`MAX_REQUESTS`).
- Timeout por petición y tamaño máximo a descargar (para no agotar memoria).
- Ignora `data:` y `javascript:` y entradas vacías.
"""

import re
import time
import urllib.parse
import requests
from urllib.parse import urljoin, urlparse, urlunparse


BASE = "http://localhost:5000/"
TIMEOUT = 10  # segundos por petición
MAX_REQUESTS = 60  # máximo recursos a solicitar
MAX_CONTENT_BYTES = 5 * 1024 * 1024  # 5 MB max por recurso (evitar OOM)


def normalize_url(base: str, href: str) -> str:
    if not href:
        return ""
    # join relative urls
    joined = urljoin(base, href)
    parsed = urlparse(joined)
    # remove fragment to avoid duplicate requests for anchors
    nofrag = parsed._replace(fragment="")
    # optional: collapse default ports
    netloc = nofrag.netloc
    scheme = nofrag.scheme
    return urlunparse((scheme, netloc, nofrag.path or '/', nofrag.params, nofrag.query, ''))


def safe_get(session: requests.Session, url: str, timeout: int = TIMEOUT):
    """Realiza GET con timeout y límite de lectura; devuelve status, headers y length."""
    try:
        # prefer HEAD to get headers first
        h = session.head(url, allow_redirects=True, timeout=timeout)
        status = h.status_code
        headers = h.headers
        clen = headers.get('Content-Length')
        if clen is not None:
            size = int(clen)
            return status, headers, size
        # si no hay content-length, obtener pero limitando lectura
        g = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
        total = 0
        for chunk in g.iter_content(chunk_size=8192):
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_CONTENT_BYTES:
                g.close()
                return g.status_code, g.headers, total
        return g.status_code, g.headers, total
    except Exception as exc:
        return None, {'error': str(exc)}, 0


def main(base: str = BASE):
    session = requests.Session()
    session.headers.update({'User-Agent': 'quick-collector/1.0'})

    t0 = time.perf_counter()
    try:
        r = session.get(base, timeout=TIMEOUT)
    except Exception as exc:
        print(f"MAIN -> ERROR {exc}")
        return
    print(f"MAIN {r.status_code} {len(r.content)} bytes {time.perf_counter()-t0:.3f}s cache-control={r.headers.get('Cache-Control')} etag={r.headers.get('ETag')}")

    html = r.text or ''
    raw = re.findall(r'(?i)(?:href|src)=["\'](.*?)["\']', html)

    seen = set()
    results = []
    count = 0
    for href in raw:
        if count >= MAX_REQUESTS:
            print(f"Limite de peticiones alcanzado: {MAX_REQUESTS}")
            break
        href = href.strip()
        if not href or href.startswith('data:') or href.startswith('javascript:'):
            continue
        url = normalize_url(base, href)
        if not url or url in seen:
            continue
        seen.add(url)
        count += 1
        t0 = time.perf_counter()
        status, headers, size = safe_get(session, url)
        elapsed = time.perf_counter() - t0
        if status is None:
            print(f"{url} -> ERROR {headers.get('error')}")
            results.append({'url': url, 'error': headers.get('error')})
            continue
        print(f"{url} -> {status} {size} bytes {elapsed:.3f}s cache-control={headers.get('Cache-Control')} etag={headers.get('ETag')}")
        results.append({'url': url, 'status': status, 'size': size, 'time': elapsed, 'cache-control': headers.get('Cache-Control'), 'etag': headers.get('ETag')})


if __name__ == '__main__':
    main()
