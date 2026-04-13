from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from main import restore_backup_snapshot  # pylint: disable=import-outside-toplevel

    if len(sys.argv) > 1:
        snapshot_path = Path(sys.argv[1]).resolve()
    else:
        snapshot_path = (project_root / "backups" / "latest.json").resolve()
    output_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None

    if not snapshot_path.exists():
        raise SystemExit(f"[restore] snapshot no encontrado: {snapshot_path}")

    result = restore_backup_snapshot(str(snapshot_path))
    payload = json.dumps(result, ensure_ascii=False)
    if output_path:
        output_path.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
