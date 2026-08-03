import csv
import importlib.util
import json
from pathlib import Path


def _load_catalog_module():
    script = Path(__file__).parents[1] / "scripts" / "build_catalog.py"
    spec = importlib.util.spec_from_file_location("catalog_build", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_template_reports_all_missing_sources(tmp_path: Path) -> None:
    module = _load_catalog_module()
    selection = Path(__file__).parents[1] / "data" / "selection.csv"

    results = module.build(selection, tmp_path / "library", tmp_path / "reports")

    assert len(results) == 50
    assert {result["status"] for result in results} == {"NEEDS_LEGAL_SOURCE"}
    assert results[0]["artist"] == "鄧麗君"
    assert (tmp_path / "reports" / "catalog-summary.csv").exists()
    assert (tmp_path / "reports" / "missing-sources.csv").exists()
    assert (tmp_path / "reports" / "duplicates.csv").exists()
    assert (tmp_path / "reports" / "process-results.json").exists()
    assert (tmp_path / "reports" / "final-verification.md").exists()
    with (tmp_path / "reports" / "process-results.json").open(encoding="utf-8-sig") as handle:
        assert json.load(handle)[0]["title"] == "月亮代表我的心"


def test_catalog_template_has_fifty_selected_candidates() -> None:
    selection = Path(__file__).parents[1] / "data" / "selection.csv"
    with selection.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 50
    assert all(row["selected"] == "yes" for row in rows)
    assert all(row["status"] == "NEEDS_LEGAL_SOURCE" for row in rows)
