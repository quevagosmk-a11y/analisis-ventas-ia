#!/usr/bin/env python3
"""Recopila recursos de la página y mide tiempos, tamaños y headers.

Uso: python scripts/collect_network.py http://localhost:5000
"""
from __future__ import annotations

import re
import sys
import time
import json
from urllib.parse import urljoin, urlparse

import requests


def extract_resources(html: str) -> list:
    resources = []
    # link href
    resources += re.findall(r"<link[^>]+href=[\"']([^\"']+)[\"']", html, flags=re.I)
    # script src
    resources += re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.I)
    # img src
    resources += re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.I)
    # source src (video/audio)
    resources += re.findall(r"<source[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.I)
    # @import in style tags / inline CSS
    resources += re.findall(r"@import\s+[\"']([^\"']+)[\"']", html, flags=re.I)
    # url(...) in CSS
    resources += re.findall(r"url\((?:'|\")?([^\)\'\"]+)(?:'|\")?\)", html, flags=re.I)
    # Filter out data: and javascript: etc.
    cleaned = []
    for r in resources:
        r = r.strip()
        if not r:
            continue
        if r.startswith("data:") or r.startswith("javascript:"):
            continue
        cleaned.append(r)
    # deduplicate while preserving order
    seen = set()
    out = []
    for r in cleaned:
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return out


def fetch_resource(url: str, session: requests.Session) -> dict:
    result = {
        "url": url,
        "status_code": None,
        "time": None,
        "size": None,
        "cache_control": None,
        "etag": None,
        "content_type": None,
    }
    try:
        t0 = time.perf_counter()
        # Try HEAD first
        resp = session.head(url, allow_redirects=True, timeout=15)
        t1 = time.perf_counter()
        result["status_code"] = resp.status_code
        result["time"] = max(0.0, t1 - t0)
        headers = resp.headers
        result["cache_control"] = headers.get("Cache-Control") or headers.get("cache-control")
        result["etag"] = headers.get("ETag") or headers.get("etag")
        result["content_type"] = headers.get("Content-Type")
        clen = headers.get("Content-Length")
        if clen is not None:
            try:
                result["size"] = int(clen)
            except Exception:
                result["size"] = None
        else:
            # fallback to GET for size
            t0 = time.perf_counter()
            resp2 = session.get(url, allow_redirects=True, timeout=30, stream=True)
            body = resp2.content
            t1 = time.perf_counter()
            result["status_code"] = resp2.status_code
            result["time"] = max(0.0, t1 - t0)
            result["size"] = len(body)
            headers = resp2.headers
            result["cache_control"] = headers.get("Cache-Control") or headers.get("cache-control")
            result["etag"] = headers.get("ETag") or headers.get("etag")
            result["content_type"] = headers.get("Content-Type")
    except Exception as exc:
        result["error"] = str(exc)
    return result


def main():
    if len(sys.argv) < 2:
        print("Uso: python collect_network.py http://localhost:5000")
        sys.exit(1)
    base = sys.argv[1].rstrip("/")
    session = requests.Session()
    session.headers.update({"User-Agent": "collect-network/1.0"})

    print(f"Cargando página {base} ...")
    t0 = time.perf_counter()
    resp = session.get(base, timeout=30)
    t1 = time.perf_counter()
    html = resp.text
    main_result = {
        "url": base,
        "status_code": resp.status_code,
        "time": max(0.0, t1 - t0),
        "size": len(resp.content),
        "cache_control": resp.headers.get("Cache-Control") or resp.headers.get("cache-control"),
        "etag": resp.headers.get("ETag") or resp.headers.get("etag"),
        "content_type": resp.headers.get("Content-Type"),
    }

    resources = extract_resources(html)
    abs_resources = []
    for r in resources:
        if r.startswith("//"):
            parsed = urlparse(base)
            abs_resources.append(parsed.scheme + ":" + r)
        elif bool(urlparse(r).netloc):
            abs_resources.append(r)
        else:
            abs_resources.append(urljoin(base + "/", r))

    results = [main_result]
    print(f"Encontrados {len(abs_resources)} recursos en HTML")
    for r in abs_resources:
        print(f"  -> {r}")
    for r in abs_resources:
        print(f"Solicitando: {r}")
        res = fetch_resource(r, session)
        results.append(res)

    # Sorts
    by_time = sorted(results, key=lambda x: (x.get("time") or 0), reverse=True)
    by_size = sorted(results, key=lambda x: (x.get("size") or 0), reverse=True)

    # compute impact = time * size (if both present)
    for item in results:
        t = item.get("time") or 0
        s = item.get("size") or 0
        item["impact"] = t * s

    by_impact = sorted(results, key=lambda x: x.get("impact") or 0, reverse=True)

    report = {
        "summary": {
            "total_resources": len(results) - 1,
            "root": main_result,
        },
        "by_time": by_time,
        "by_size": by_size,
        "by_impact": by_impact,
    }

    import os
    out_path = os.path.join(os.path.dirname(__file__), "network_report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Informe guardado en {out_path}")


if __name__ == "__main__":
    main()
