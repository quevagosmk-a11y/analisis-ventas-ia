from __future__ import annotations

import glob
import io
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from fpdf import FPDF


def prune_old_backups(*, backup_dir: str, backup_keep: int) -> None:
    try:
        files = sorted(glob.glob(os.path.join(backup_dir, "snapshot-*.json")), reverse=True)
    except FileNotFoundError:
        return
    for old_path in files[backup_keep:]:
        try:
            os.remove(old_path)
        except OSError:
            continue


def load_backup_payload(snapshot_path: str) -> Dict[str, Any]:
    with open(snapshot_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("El respaldo no tiene un formato valido.")
    return payload


def build_backup_pdf_file(
    payload: Dict[str, Any],
    *,
    pdf_safe_text: Callable[[Any], str],
    format_currency: Callable[[Any], str],
) -> io.BytesIO:
    metadata = payload.get("metadata") or {}
    products = payload.get("productos") or []
    sales = payload.get("ventas") or []
    low_stock = [
        item
        for item in products
        if int(item.get("stock") or 0) <= int(item.get("min_stock") or 0)
    ][:12]
    top_sales = sales[:12]
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    line_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, pdf_safe_text("Snapshot de respaldo"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    summary_lines = [
        f"Creado: {payload.get('created_at') or '-'}",
        f"Motivo: {payload.get('reason') or '-'}",
        f"Fuente: {payload.get('source') or '-'}",
        (
            "Conteo: "
            f"{int(metadata.get('productos') or len(products) or 0)} productos, "
            f"{int(metadata.get('ventas') or len(sales) or 0)} ventas, "
            f"{int(metadata.get('detalle') or len(payload.get('venta_detalle') or []) or 0)} lineas"
        ),
    ]
    for line in summary_lines:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(line_width, 6, pdf_safe_text(line))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, pdf_safe_text("Stock bajo"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    if not low_stock:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(line_width, 6, pdf_safe_text("Sin alertas criticas en el snapshot."))
    for entry in low_stock:
        line = (
            f"{entry.get('nombre') or '-'} | Stock {int(entry.get('stock') or 0)} | "
            f"Minimo {int(entry.get('min_stock') or 0)}"
        )
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(line_width, 6, pdf_safe_text(line))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, pdf_safe_text("Ultimas ventas incluidas"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    if not top_sales:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(line_width, 6, pdf_safe_text("No hay ventas en este snapshot."))
    for sale in top_sales:
        line = (
            f"#{int(sale.get('id') or 0)} | {sale.get('fecha') or '-'} | "
            f"{sale.get('metodo_pago') or '-'} | {format_currency(sale.get('total'))}"
        )
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(line_width, 6, pdf_safe_text(line))
    output = io.BytesIO(bytes(pdf.output()))
    output.seek(0)
    return output


def build_backup_artifacts(
    snapshot_path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    backup_dir: str,
    load_backup_payload: Callable[[str], Dict[str, Any]],
    build_backup_pdf_file: Callable[[Dict[str, Any]], io.BytesIO],
) -> Dict[str, Any]:
    data = payload or load_backup_payload(snapshot_path)
    snapshot_name = os.path.basename(snapshot_path)
    pdf_name = f"{os.path.splitext(snapshot_name)[0]}.pdf"
    pdf_path = os.path.join(backup_dir, pdf_name)
    output = build_backup_pdf_file(data)
    with open(pdf_path + ".tmp", "wb") as fh:
        fh.write(output.getvalue())
    os.replace(pdf_path + ".tmp", pdf_path)
    return {
        "json_filename": snapshot_name,
        "json_path": snapshot_path,
        "json_url": f"/api/backups/download/{snapshot_name}",
        "pdf_filename": pdf_name,
        "pdf_path": pdf_path,
        "pdf_url": f"/api/backups/download/{pdf_name}",
    }


def normalize_backup_filename(filename: Any) -> str:
    normalized = os.path.basename(str(filename or "").strip())
    if not normalized or normalized != str(filename or "").strip():
        raise ValueError("Nombre de respaldo invalido.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", normalized):
        raise ValueError("Nombre de respaldo invalido.")
    return normalized


def resolve_backup_artifact_path(filename: Any, *, backup_dir: str) -> str:
    normalized = normalize_backup_filename(filename)
    ext = os.path.splitext(normalized)[1].lower()
    if ext not in {".json", ".pdf"}:
        raise ValueError("Tipo de archivo de respaldo no soportado.")
    candidate = os.path.abspath(os.path.join(backup_dir, normalized))
    base_dir = os.path.abspath(backup_dir)
    if not candidate.startswith(base_dir + os.sep) and candidate != base_dir:
        raise ValueError("Ruta de respaldo invalida.")
    if not os.path.exists(candidate) or not os.path.isfile(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def list_backup_entries(
    *,
    limit: int = 50,
    backup_dir: str,
    ensure_backup_dir: Callable[[], None],
    load_backup_payload: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ensure_backup_dir()
    candidates = sorted(glob.glob(os.path.join(backup_dir, "snapshot-*.json")), reverse=True)[
        : max(1, limit)
    ]
    entries: List[Dict[str, Any]] = []
    for index, snapshot_path in enumerate(candidates):
        snapshot_name = os.path.basename(snapshot_path)
        try:
            payload = load_backup_payload(snapshot_path)
        except Exception as exc:
            entries.append(
                {
                    "json_filename": snapshot_name,
                    "created_at": None,
                    "reason": "desconocido",
                    "error": str(exc),
                    "latest": index == 0,
                    "json_url": f"/api/backups/download/{snapshot_name}",
                }
            )
            continue
        pdf_name = f"{os.path.splitext(snapshot_name)[0]}.pdf"
        pdf_path = os.path.join(backup_dir, pdf_name)
        metadata = payload.get("metadata") or {}
        entries.append(
            {
                "json_filename": snapshot_name,
                "json_url": f"/api/backups/download/{snapshot_name}",
                "json_size_bytes": os.path.getsize(snapshot_path),
                "pdf_filename": pdf_name if os.path.exists(pdf_path) else None,
                "pdf_url": f"/api/backups/download/{pdf_name}" if os.path.exists(pdf_path) else None,
                "pdf_size_bytes": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else None,
                "created_at": payload.get("created_at"),
                "reason": payload.get("reason") or "manual",
                "metadata": {
                    "productos": int(metadata.get("productos") or 0),
                    "ventas": int(metadata.get("ventas") or 0),
                    "detalle": int(metadata.get("detalle") or 0),
                    "configuracion": int(metadata.get("configuracion") or 0),
                    "inventario_movimientos": int(
                        metadata.get("inventario_movimientos") or 0
                    ),
                },
                "latest": index == 0,
            }
        )
    return entries


def load_latest_backup(
    *,
    backup_dir: str,
    ensure_backup_dir: Callable[[], None],
    offline_cache: Any,
) -> Optional[str]:
    ensure_backup_dir()
    latest_path = os.path.join(backup_dir, "latest.json")
    try:
        if os.path.exists(latest_path):
            offline_cache.load_from_file(latest_path)
            return latest_path
        candidates = sorted(glob.glob(os.path.join(backup_dir, "snapshot-*.json")), reverse=True)
        if candidates:
            offline_cache.load_from_file(candidates[0])
            return candidates[0]
    except Exception as exc:
        print(f"[backup] no se pudo cargar respaldo: {exc}")
    return None
