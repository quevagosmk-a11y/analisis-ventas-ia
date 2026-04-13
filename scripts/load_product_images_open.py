#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
import numpy as np

try:
    from PIL import Image, ImageFilter
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]

try:
    from scipy import ndimage as ndi  # type: ignore
    SCIPY_AVAILABLE = True
except Exception:
    ndi = None  # type: ignore[assignment]
    SCIPY_AVAILABLE = False

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db import connect as mysql_connect  # noqa: E402

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "LaSeptimaEstrellaImageSeeder/1.0 (proyecto-academico-local)"
REQUEST_TIMEOUT = 30
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = max(64_000, int(os.environ.get("PRODUCT_IMAGE_MAX_BYTES", "900000")))
SEARCH_WIDTHS = [640, 512, 420, 320, 260]

DISALLOWED_TITLE_TOKENS = {
    "logo",
    "diagram",
    "map",
    "icon",
    "symbol",
    "coat of arms",
    "flag",
    "vector",
    "svg",
}

PRODUCT_SEARCH_OVERRIDES: Dict[str, List[str]] = {
    "aceite 1l": ["vegetable oil bottle"],
    "agua 600ml": ["bottled water"],
    "arroz 1kg": ["bag of rice food package"],
    "azucar 1kg": ["sugar bag package"],
    "bebida energetica 250ml": ["energy drink can"],
    "cafe molido 250g": ["ground coffee package"],
    "cerveza sixpack": ["beer cans six pack"],
    "chitos 40g": ["cheese puffs snack bag"],
    "chocolate 250g": ["chocolate bar package"],
    "detergente 500g": ["laundry detergent powder package"],
    "frijol 500g": ["dry beans", "dried beans bag"],
    "galletas chocolate": ["chocolate cookies package"],
    "gaseosa cola 400ml": ["cola soft drink bottle"],
    "gaseosa manzana 400ml": ["green apple soda drink bottle"],
    "harina trigo 1kg": ["wheat flour bag", "flour package"],
    "huevos x30": ["egg carton", "eggs tray carton"],
    "jabon barra": ["bar soap", "laundry soap bar"],
    "jugo mango 300ml": ["mango juice bottle"],
    "leche entera 900ml": ["whole milk bottle"],
    "lenteja 500g": ["lentils", "lentils bag food"],
    "mani 50g": ["peanuts snack package"],
    "pan blandito x5": ["bread rolls bakery"],
    "pan tajado 500g": ["sliced bread", "bread loaf sliced", "sliced bread loaf package"],
    "papas 30g": ["potato chips snack bag"],
    "papel higienico x4": ["toilet tissue paper roll", "toilet paper roll", "toilet paper rolls pack"],
    "queso campesino 250g": ["fresh cheese package"],
    "sal 500g": ["table salt package"],
    "yogurt fresa 200ml": ["strawberry yogurt cup"],
}

CATEGORY_TERMS: Dict[str, List[str]] = {
    "bebidas": ["drink bottle", "beverage can"],
    "despensa": ["packaged grocery food"],
    "snacks": ["snack package"],
    "aseo": ["household cleaning product package"],
    "granos": ["dry grains bag"],
    "lacteos": ["dairy product package"],
    "panaderia": ["bakery bread package"],
}


def _find_main_component_bbox(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Retorna bbox (x0, y0, x1, y1) del objeto principal.

    Prioriza componentes grandes, cercanos al centro y que no toquen borde
    (para descartar "pedazos" de otras fotos en mosaicos).
    """
    if mask.ndim != 2 or not mask.any():
        return None

    h, w = mask.shape
    image_area = float(h * w)
    center_x = w / 2.0
    center_y = h / 2.0
    diag = max(1.0, (w ** 2 + h ** 2) ** 0.5)

    components: List[Tuple[float, Tuple[int, int, int, int]]] = []
    if SCIPY_AVAILABLE and ndi is not None:
        labels, count = ndi.label(mask)
        if count <= 0:
            return None
        slices = ndi.find_objects(labels)
        for label_idx, slc in enumerate(slices, start=1):
            if slc is None:
                continue
            y0, y1 = slc[0].start, slc[0].stop
            x0, x1 = slc[1].start, slc[1].stop
            comp = labels[slc] == label_idx
            area = float(comp.sum())
            if area < image_area * 0.0012:
                continue
            ys, xs = np.where(comp)
            if ys.size == 0 or xs.size == 0:
                continue
            cx = x0 + float(xs.mean())
            cy = y0 + float(ys.mean())
            center_dist = (((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5) / (diag / 2.0)
            touches_border = x0 <= 1 or y0 <= 1 or x1 >= (w - 1) or y1 >= (h - 1)

            score = area
            if touches_border:
                score *= 0.28
            score *= max(0.22, 1.0 - (0.55 * min(center_dist, 1.0)))
            components.append((score, (x0, y0, x1, y1)))
    else:
        ys, xs = np.where(mask)
        if ys.size == 0 or xs.size == 0:
            return None
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        components.append((1.0, (x0, y0, x1, y1)))

    if not components:
        return None
    components.sort(key=lambda item: item[0], reverse=True)
    return components[0][1]


def smart_prepare_image(blob: bytes, mime: str, target_size: int = 320) -> Tuple[bytes, str, Dict[str, Any]]:
    """Recorta fondo excesivo y genera un cuadrado limpio para UI."""
    if not blob:
        return blob, mime, {"processed": False, "reason": "empty"}
    if not PIL_AVAILABLE or Image is None:
        return blob, mime, {"processed": False, "reason": "pillow_missing"}

    try:
        with Image.open(io.BytesIO(blob)) as raw_img:
            img = raw_img.convert("RGB")
    except Exception:
        return blob, mime, {"processed": False, "reason": "decode_failed"}

    arr = np.asarray(img)
    h, w = arr.shape[:2]
    if h < 10 or w < 10:
        return blob, mime, {"processed": False, "reason": "too_small"}

    # Muestreo de borde para estimar color de fondo (blanco/gris claro en estos assets).
    border = max(2, int(min(h, w) * 0.04))
    border_pixels = np.concatenate(
        [
            arr[:border, :, :].reshape(-1, 3),
            arr[-border:, :, :].reshape(-1, 3),
            arr[:, :border, :].reshape(-1, 3),
            arr[:, -border:, :].reshape(-1, 3),
        ],
        axis=0,
    ).astype(np.int16)
    bg_rgb = np.median(border_pixels, axis=0).astype(np.int16)
    noise = int(np.std(border_pixels))
    diff = np.abs(arr.astype(np.int16) - bg_rgb)

    # Umbral adaptativo conservador para aislar producto.
    threshold = max(16, min(44, (noise * 3) + 14))
    mask = diff.max(axis=2) >= threshold

    # Limpieza de ruido y conexión de bordes del objeto.
    mask_img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    mask_img = mask_img.filter(ImageFilter.MedianFilter(size=3))
    mask_img = mask_img.filter(ImageFilter.MaxFilter(size=3))
    clean_mask = np.asarray(mask_img) > 0

    bbox = _find_main_component_bbox(clean_mask)
    if bbox is None:
        return blob, mime, {"processed": False, "reason": "no_subject"}
    x0, y0, x1, y1 = bbox

    # Padding para no "ahogar" el producto.
    box_w = x1 - x0
    box_h = y1 - y0
    pad_x = max(5, int(box_w * 0.18))
    pad_y = max(5, int(box_h * 0.18))
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(w, x1 + pad_x)
    y1 = min(h, y1 + pad_y)

    crop = img.crop((x0, y0, x1, y1))
    crop_w, crop_h = crop.size

    # Salida cuadrada para que el thumbnail se vea consistente.
    side = max(crop_w, crop_h)
    bg_color = tuple(int(v) for v in np.clip(bg_rgb, 0, 255))
    square = Image.new("RGB", (side, side), color=bg_color)
    offset_x = (side - crop_w) // 2
    offset_y = (side - crop_h) // 2
    square.paste(crop, (offset_x, offset_y))
    resampling = getattr(Image, "Resampling", Image)
    square = square.resize((target_size, target_size), resampling.LANCZOS)

    # JPEG funciona mejor para estas fotos de producto y reduce peso.
    out = io.BytesIO()
    square.save(out, format="JPEG", quality=90, optimize=True)
    out_blob = out.getvalue()
    out_mime = "image/jpeg"
    if not out_blob:
        return blob, mime, {"processed": False, "reason": "encode_failed"}
    return out_blob, out_mime, {
        "processed": True,
        "target_size": target_size,
        "source_size": [w, h],
        "crop_box": [x0, y0, x1, y1],
        "bytes_before": len(blob),
        "bytes_after": len(out_blob),
    }


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def build_db_config(args: argparse.Namespace) -> Dict[str, str]:
    return {
        "host": args.db_host or os.environ.get("DB_HOST", "localhost"),
        "user": args.db_user or os.environ.get("DB_USER", "root"),
        "password": args.db_password if args.db_password is not None else os.environ.get("DB_PASSWORD", ""),
        "database": args.db_name or os.environ.get("DB_NAME", "la_septima_estrella"),
    }


def build_search_terms(name: str, category: str) -> List[str]:
    terms: List[str] = []
    key = normalize_text(name)
    if key in PRODUCT_SEARCH_OVERRIDES:
        terms.extend(PRODUCT_SEARCH_OVERRIDES[key])

    compact_name = re.sub(r"\b\d+[a-zA-Z]*\b", " ", name)
    compact_name = re.sub(r"\bx\s*\d+\b", " ", compact_name, flags=re.IGNORECASE)
    compact_name = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]+", " ", compact_name)
    compact_name = re.sub(r"\s+", " ", compact_name).strip()
    if compact_name:
        terms.append(f"{compact_name} product package")

    category_key = normalize_text(category)
    terms.extend(CATEGORY_TERMS.get(category_key, []))
    if category:
        terms.append(f"{category} grocery product")
    terms.extend(["retail grocery product", "packaged food product"])

    deduped: List[str] = []
    seen = set()
    for term in terms:
        clean = term.strip()
        if not clean:
            continue
        fingerprint = normalize_text(clean)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(clean)
    return deduped


def title_is_disallowed(title: str) -> bool:
    title_norm = normalize_text(title)
    return any(token in title_norm for token in DISALLOWED_TITLE_TOKENS)


def score_candidate(title: str, query: str) -> int:
    title_norm = normalize_text(title)
    query_tokens = [tok for tok in normalize_text(query).split() if len(tok) > 2]
    score = 0
    for token in query_tokens:
        if token in title_norm:
            score += 2
    for token in DISALLOWED_TITLE_TOKENS:
        if token in title_norm:
            score -= 8
    return score


def commons_search_images(query: str, width: int, session: requests.Session) -> List[Dict[str, Any]]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "gsrsearch": query,
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "iiurlwidth": str(width),
    }
    response = session.get(WIKIMEDIA_API, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    pages = (payload.get("query") or {}).get("pages") or {}
    candidates: List[Dict[str, Any]] = []
    for page in pages.values():
        title = str(page.get("title") or "")
        if not title or title_is_disallowed(title):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "").lower()
        if mime not in ALLOWED_MIME:
            continue
        image_url = str(info.get("thumburl") or info.get("url") or "").strip()
        if not image_url:
            continue
        candidates.append(
            {
                "title": title,
                "url": image_url,
                "mime": mime,
                "score": score_candidate(title, query),
                "query": query,
                "width": width,
            }
        )
    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    return candidates


def download_image(url: str, session: requests.Session) -> Tuple[Optional[bytes], Optional[str]]:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        return None, None
    mime = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME:
        return None, None
    blob = response.content
    if not blob:
        return None, None
    return blob, mime


def find_best_image(name: str, category: str, session: requests.Session) -> Tuple[Optional[bytes], Optional[str], Dict[str, Any]]:
    terms = build_search_terms(name, category)
    for term in terms:
        for width in SEARCH_WIDTHS:
            try:
                candidates = commons_search_images(term, width, session)
            except Exception:
                continue
            for candidate in candidates[:5]:
                blob, mime = download_image(candidate["url"], session)
                if not blob or not mime:
                    continue
                if len(blob) > MAX_IMAGE_BYTES:
                    continue
                meta = {
                    "query": candidate.get("query"),
                    "source_title": candidate.get("title"),
                    "source_url": candidate.get("url"),
                    "width": candidate.get("width"),
                    "bytes": len(blob),
                }
                return blob, mime, meta
            time.sleep(0.08)
    return None, None, {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga imagenes libres desde Wikimedia Commons y las guarda en productos.imagen_blob",
    )
    parser.add_argument("--db-host", default=None)
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--db-password", nargs="?", const="", default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--limit", type=int, default=0, help="Maximo de productos a procesar (0 = todos)")
    parser.add_argument("--force", action="store_true", help="Reemplazar imagenes ya existentes")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en BD")
    parser.add_argument(
        "--recrop-existing",
        action="store_true",
        help="Recorta y normaliza imagenes ya cargadas sin volver a buscarlas en internet",
    )
    parser.add_argument(
        "--target-size",
        type=int,
        default=320,
        help="Tamano final (px) de cada imagen cuadrada",
    )
    parser.add_argument(
        "--manifest",
        default=str(ROOT_DIR / "backups" / "product_image_sources.json"),
        help="Ruta del JSON con fuentes usadas",
    )
    return parser.parse_args()


def _safe_console(value: Any) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except Exception:
        return text


def log(value: Any) -> None:
    print(_safe_console(value))


def main() -> int:
    args = parse_args()
    db_config = build_db_config(args)
    manifest_path = Path(args.manifest).resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,image/*"})

    conn = None
    cur = None
    manifest_rows: List[Dict[str, Any]] = []
    updated = 0
    skipped = 0
    failed = 0
    try:
        conn = mysql_connect(**db_config)
        cur = conn.cursor(dictionary=True)
        cur.execute("SHOW COLUMNS FROM productos LIKE 'activo'")
        has_active = bool(cur.fetchone())
        where_clause = "WHERE activo=1" if has_active else ""
        cur.execute(
            f"""
            SELECT id, nombre, categoria, imagen_blob
            FROM productos
            {where_clause}
            ORDER BY id
            """
        )
        rows = cur.fetchall() or []
        if args.limit and args.limit > 0:
            rows = rows[: args.limit]
        log(f"[images] Productos encontrados: {len(rows)}")

        for row in rows:
            product_id = int(row.get("id") or 0)
            name = str(row.get("nombre") or "").strip()
            category = str(row.get("categoria") or "").strip()
            current_blob = row.get("imagen_blob")
            has_image = bool(current_blob)
            if not product_id or not name:
                skipped += 1
                continue
            if has_image and not args.force:
                if args.recrop_existing:
                    cur.execute("SELECT imagen_blob, imagen_mime FROM productos WHERE id=%s", (product_id,))
                    current = cur.fetchone() or {}
                    existing_blob = current.get("imagen_blob")
                    existing_mime = str(current.get("imagen_mime") or "image/jpeg").strip().lower()
                    if existing_blob:
                        prepared_blob, prepared_mime, prep_meta = smart_prepare_image(
                            bytes(existing_blob),
                            existing_mime,
                            target_size=max(120, min(640, int(args.target_size or 320))),
                        )
                        changed = prepared_blob != bytes(existing_blob) or prepared_mime != existing_mime
                        if changed and not args.dry_run:
                            cur.execute(
                                "UPDATE productos SET imagen_blob=%s, imagen_mime=%s WHERE id=%s",
                                (prepared_blob, prepared_mime, product_id),
                            )
                        if changed:
                            updated += 1
                            manifest_rows.append(
                                {
                                    "id": product_id,
                                    "nombre": name,
                                    "categoria": category,
                                    "mime": prepared_mime,
                                    "source": "existing_blob_recrop",
                                    **prep_meta,
                                }
                            )
                            log(
                                f"[images] recrop#{product_id:<4} {name} "
                                f"({prep_meta.get('bytes_before',0)} -> {prep_meta.get('bytes_after',0)} bytes)"
                            )
                        else:
                            skipped += 1
                            log(f"[images] skip  #{product_id:<4} {name} (sin cambios tras recorte)")
                        continue
                log(f"[images] skip  #{product_id:<4} {name} (ya tiene imagen)")
                skipped += 1
                continue

            blob, mime, meta = find_best_image(name, category, session)
            if not blob or not mime:
                log(f"[images] fail  #{product_id:<4} {name} (sin resultado)")
                failed += 1
                continue

            prepared_blob, prepared_mime, prep_meta = smart_prepare_image(
                blob,
                mime,
                target_size=max(120, min(640, int(args.target_size or 320))),
            )
            final_blob = prepared_blob or blob
            final_mime = prepared_mime or mime

            if not args.dry_run:
                cur.execute(
                    "UPDATE productos SET imagen_blob=%s, imagen_mime=%s WHERE id=%s",
                    (final_blob, final_mime, product_id),
                )
            updated += 1
            manifest_rows.append(
                {
                    "id": product_id,
                    "nombre": name,
                    "categoria": category,
                    "mime": final_mime,
                    **meta,
                    **prep_meta,
                }
            )
            log(
                f"[images] ok    #{product_id:<4} {name} <- {meta.get('source_title','?')} "
                f"({final_mime}, {len(final_blob)} bytes)"
            )

        if not args.dry_run:
            conn.commit()
        else:
            conn.rollback()

    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        log(f"[images] error: {exc}")
        return 1
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    manifest_payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db_name": db_config.get("database"),
        "dry_run": bool(args.dry_run),
        "force": bool(args.force),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "sources": manifest_rows,
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log(
        f"[images] resumen -> actualizadas: {updated} | omitidas: {skipped} | sin imagen: {failed} | "
        f"manifest: {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
