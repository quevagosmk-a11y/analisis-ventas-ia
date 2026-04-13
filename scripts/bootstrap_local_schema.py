from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from main import bootstrap_database  # pylint: disable=import-outside-toplevel

    result = bootstrap_database()
    payload = json.dumps(result, ensure_ascii=False)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).resolve().write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
