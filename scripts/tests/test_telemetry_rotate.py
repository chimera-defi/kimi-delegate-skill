"""Tests for _maybe_rotate() in kimi_delegate_telemetry.py.

summarize() and repo_root_from_script() are covered in test_telemetry_summary.py
and test_edge_cases.py respectively. This file covers _maybe_rotate() which
has no prior test coverage.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_telemetry():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "kimi_delegate_telemetry.py"
    spec = importlib.util.spec_from_file_location("kimi_telemetry", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


telemetry = _load_telemetry()


def test_nonexistent_file_returns_silently() -> None:
    """_maybe_rotate on a non-existent path must not raise."""
    p = Path("/tmp/does-not-exist-kimi-test-xyz.jsonl")
    assert not p.exists()
    telemetry._maybe_rotate(p)  # must not raise


def test_small_file_not_rotated(tmp_path: Path) -> None:
    """File under threshold should remain in place unchanged."""
    f = tmp_path / "events.jsonl"
    f.write_text('{"event": "test"}\n', encoding="utf-8")
    telemetry._maybe_rotate(f, max_bytes=1024 * 1024)  # 1 MB threshold
    assert f.exists(), "original file should still exist"
    assert not (tmp_path / "events.jsonl.1").exists(), "no rotation should happen"


def test_file_at_exact_threshold_not_rotated(tmp_path: Path) -> None:
    """File at exactly max_bytes is not rotated (condition is >)."""
    f = tmp_path / "events.jsonl"
    f.write_bytes(b"x" * 50)
    telemetry._maybe_rotate(f, max_bytes=50)
    assert f.exists(), "at-threshold file should not be rotated"


def test_large_file_rotated_to_jsonl_1(tmp_path: Path) -> None:
    """File exceeding max_bytes should be renamed to .jsonl.1."""
    f = tmp_path / "events.jsonl"
    f.write_bytes(b"x" * 100)
    telemetry._maybe_rotate(f, max_bytes=50)
    assert not f.exists(), "original should be gone after rotation"
    assert (tmp_path / "events.jsonl.1").exists(), ".jsonl.1 should be created"


def test_existing_rotated_files_shifted(tmp_path: Path) -> None:
    """Pre-existing .jsonl.1 and .jsonl.2 are shifted up by one."""
    f = tmp_path / "events.jsonl"
    f.write_bytes(b"x" * 100)
    (tmp_path / "events.jsonl.1").write_text("old1", encoding="utf-8")
    (tmp_path / "events.jsonl.2").write_text("old2", encoding="utf-8")

    telemetry._maybe_rotate(f, max_bytes=50)

    assert (tmp_path / "events.jsonl.2").read_text(encoding="utf-8") == "old1"
    assert (tmp_path / "events.jsonl.3").read_text(encoding="utf-8") == "old2"


def test_rotation_chain_max_3_slots(tmp_path: Path) -> None:
    """Rotation shifts slots .1/.2/.3 → .2/.3/.4, dropping nothing silently."""
    f = tmp_path / "events.jsonl"
    f.write_bytes(b"x" * 100)
    for i in range(1, 4):
        (tmp_path / f"events.jsonl.{i}").write_text(f"slot{i}", encoding="utf-8")

    telemetry._maybe_rotate(f, max_bytes=50)

    # Slots should shift: 1→2, 2→3, 3→4
    assert (tmp_path / "events.jsonl.2").read_text(encoding="utf-8") == "slot1"
    assert (tmp_path / "events.jsonl.3").read_text(encoding="utf-8") == "slot2"
    assert (tmp_path / "events.jsonl.4").read_text(encoding="utf-8") == "slot3"
    # Current file moves to .jsonl.1
    assert (tmp_path / "events.jsonl.1").exists()
    assert not f.exists()
