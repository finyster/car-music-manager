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


def test_existing_original_is_reused_for_an_interrupted_catalog_item(tmp_path: Path) -> None:
    module = _load_catalog_module()
    originals = tmp_path / "originals"
    originals.mkdir()
    original = originals / "21 - 任賢齊 - 心太軟.webm"
    original.touch()
    (originals / "21 - 任賢齊 - 心太軟 (2).webm").touch()

    assert module._existing_original(originals, "21 - 任賢齊 - 心太軟") == original


def test_catalog_template_is_locked_to_original_fifty() -> None:
    selection = Path(__file__).parents[1] / "data" / "selection.csv"
    with selection.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = [
        ("鄧麗君", "月亮代表我的心"), ("鄧麗君", "我只在乎你"), ("鄧麗君", "甜蜜蜜"),
        ("鄧麗君", "小城故事"), ("鄧麗君", "千言萬語"), ("費玉清", "一剪梅"),
        ("費玉清", "夢駝鈴"), ("蔡琴", "被遺忘的時光"), ("蔡琴", "恰似你的溫柔"),
        ("蔡琴", "你的眼神"), ("江蕙", "家後"), ("江蕙", "惜別的海岸"),
        ("江蕙", "酒後的心聲"), ("江蕙", "甲你攬牢牢"), ("江蕙", "博杯"),
        ("葉啟田", "愛拼才會贏"), ("葉啟田", "浪子的心情"), ("陳雷", "歡喜就好"),
        ("蔡秋鳳", "金包銀"), ("黃乙玲", "海波浪"), ("任賢齊", "心太軟"),
        ("任賢齊", "傷心太平洋"), ("任賢齊", "對面的女孩看過來"), ("任賢齊", "天涯"),
        ("任賢齊", "任逍遙"), ("動力火車", "無情的情書"), ("動力火車", "當"),
        ("動力火車", "背叛情歌"), ("動力火車", "忠孝東路走九遍"), ("動力火車", "除了愛你還能愛誰"),
        ("周杰倫", "晴天"), ("周杰倫", "七里香"), ("周杰倫", "青花瓷"),
        ("周杰倫", "稻香"), ("周杰倫", "夜曲"), ("蔡依林", "倒帶"),
        ("蔡依林", "說愛你"), ("蔡依林", "日不落"), ("蔡依林", "舞孃"),
        ("蔡依林", "看我72變"), ("蕭煌奇", "你是我的眼"), ("蕭煌奇", "末班車"),
        ("蕭煌奇", "阿嬤的話"), ("蕭煌奇", "上水的花"), ("蕭煌奇", "好好先生"),
        ("刀郎", "2002年的第一場雪"), ("刀郎", "衝動的懲罰"), ("刀郎", "西海情歌"),
        ("刀郎", "情人"), ("刀郎", "披著羊皮的狼"),
    ]

    assert [(row["artist"], row["title"]) for row in rows] == expected
    assert {row["catalog_version"] for row in rows} == {"original-50-v1"}
