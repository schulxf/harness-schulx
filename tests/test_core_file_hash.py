from __future__ import annotations

import hashlib
from pathlib import Path

from harness_core.file_hash import file_sha256


def test_file_sha256_hashes_file_content(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("hello", encoding="utf-8")

    assert file_sha256(path) == hashlib.sha256(b"hello").hexdigest()
