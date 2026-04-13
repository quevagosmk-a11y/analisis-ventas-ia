import os
import sys
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def test_find_existing_sales_csv_resolves_project_relative_path(tmp_path):
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        resolved = app_module.find_existing_sales_csv('data/sample_sales.csv')
    finally:
        os.chdir(original_cwd)
    assert resolved, 'Debe encontrar el CSV demo aunque el cwd sea distinto al proyecto.'
    assert os.path.isabs(resolved)
    normalized = resolved.replace('\\', '/')
    assert normalized.endswith('/data/sample_sales.csv')
