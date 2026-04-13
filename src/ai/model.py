from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from joblib import load

MODEL_ENV_VAR = "AI_DEMAND_MODEL_PATH"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "demand_model.joblib"

_MODEL_BUNDLE: Optional[Dict[str, Any]] = None
_MODEL_PATH: Optional[Path] = None


def _resolve_model_path() -> Path:
    env_path = os.environ.get(MODEL_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_MODEL_PATH


def get_demand_model_bundle(force_reload: bool = False) -> Optional[Dict[str, Any]]:
    global _MODEL_BUNDLE, _MODEL_PATH
    model_path = _resolve_model_path()
    if not model_path.exists():
        _MODEL_BUNDLE = None
        _MODEL_PATH = model_path
        return None
    if not force_reload and _MODEL_BUNDLE is not None and _MODEL_PATH == model_path:
        return _MODEL_BUNDLE
    try:
        bundle = load(model_path)
    except Exception:
        _MODEL_BUNDLE = None
        _MODEL_PATH = model_path
        return None
    if not isinstance(bundle, dict) or "model" not in bundle:
        _MODEL_BUNDLE = None
        _MODEL_PATH = model_path
        return None
    _MODEL_BUNDLE = bundle
    _MODEL_PATH = model_path
    return _MODEL_BUNDLE
