from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.astex.fetch_dataset import find_astex_root


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_astex_manifest_pins_85_case_regression_suite():
    manifest = json.loads(
        (REPOSITORY_ROOT / "benchmarks/astex/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["benchmark"] == "astex_diverse_v1"
    assert manifest["dataset"]["paper_case_count"] == 85
    assert manifest["dataset"]["subset_directory"] == "astex_diverse_set"
    assert manifest["protocol"]["docking"]["engine_version"] == "1.2.7"
    assert manifest["protocol"]["evaluation"]["top_n_values"] == [1, 3, 5, 9]


def test_find_astex_root_requires_exactly_one_prepared_dataset(tmp_path):
    root = tmp_path / "paper" / "astex_diverse_set"
    root.mkdir(parents=True)

    assert find_astex_root(tmp_path) == root

    duplicate = tmp_path / "other" / "astex_diverse_set"
    duplicate.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="exactly one"):
        find_astex_root(tmp_path)


def test_find_astex_root_rejects_missing_dataset(tmp_path):
    with pytest.raises(RuntimeError, match="found 0"):
        find_astex_root(tmp_path)
