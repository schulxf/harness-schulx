"""Pytest config: make `bin/harness.py` importable as `harness`."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HARNESS_PY = ROOT / "bin" / "harness.py"


def _load_harness_module():
    spec = importlib.util.spec_from_file_location("harness", HARNESS_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["harness"] = module
    spec.loader.exec_module(module)
    return module


harness = _load_harness_module()
