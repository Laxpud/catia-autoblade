"""黄金身份和测量完整性的无 CAD 回归；真实 FreeCAD 必须显式运行。"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.golden.fixture import (
    DEFAULT_CASE,
    DIRECTIONS,
    validate_measurements,
    fixture_path,
    load_fixture,
    sanitize_step,
    sha256,
    step_data,
)
from scripts.validate_distribution import (
    GOLDEN_CASE_PATH,
    GOLDEN_CASE_PATHS,
    ValidationError,
    _source_version,
    _validate_archive_names,
    _validate_golden_files,
)
from scripts.golden.report import write_error_report
from autoblade.core.input_plan import build_blade_input_plan


def test_public_golden_fixture_is_closed_and_audited():
    manifest = load_fixture()
    plan = build_blade_input_plan(
        DEFAULT_CASE / manifest["input"]["sections"],
        DEFAULT_CASE / "input/airfoils",
        None,
    )
    assert plan.is_sharp and len(plan.sections) == 89
    assert [len(item.points) for item in plan.airfoils] == [300, 253, 249]
    assert len(manifest["sampling"]["stations"]) == 46
    assert sum(row["allow_incomplete"] for row in manifest["sampling"]["stations"]) == 1
    assert (
        manifest["authorization"]["original_sha256"]
        == "d9ef236cb71e2765c69badec9cc7506b4744bb5d133208dc5cc66a9988824db9"
    )
    # 输入副本必须与先前公开分发且经审计的资源逐字节一致。
    resources = DEFAULT_CASE.parents[3] / "src/autoblade/resources"
    for name in manifest["input"]["airfoils"]:
        assert (DEFAULT_CASE / name).read_bytes() == (
            resources / "airfoil_library" / Path(name).name
        ).read_bytes()
    assert (DEFAULT_CASE / manifest["input"]["sections"]).read_bytes() == (
        resources / "workspace/blade_sections/example-blade-sections.csv"
    ).read_bytes()


def test_sanitization_changes_only_header_path_and_preserves_crlf():
    original = b"ISO-10303-21;\r\nHEADER;\r\nFILE_NAME('C:\\\\private\\\\owner''s.stp','date',('none'));\r\nENDSEC;\r\nDATA;\r\n#1=CARTESIAN_POINT('',(1.,2.,3.));\r\nENDSEC;\r\nEND-ISO-10303-21;\r\n"
    sanitized = sanitize_step(original, original_sha256=sha256(original))
    assert step_data(original) == step_data(sanitized)
    assert b"FILE_NAME('catia.stp','date'" in sanitized
    assert b"private" not in sanitized
    assert sanitized.count(b"\r\n") == original.count(b"\r\n")
    with pytest.raises(ValueError, match="approved SHA-256"):
        sanitize_step(original + b" ", original_sha256=sha256(original))


@pytest.mark.parametrize("name", ["catia.stp", "input/airfoils/airfoil1_sharp.csv"])
def test_changed_fixture_bytes_fail_before_cad(tmp_path, name):
    case = tmp_path / "case"
    shutil.copytree(DEFAULT_CASE, case)
    with (case / name).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_fixture(case)


def test_unlisted_fixture_asset_is_rejected(tmp_path):
    case = tmp_path / "case"
    shutil.copytree(DEFAULT_CASE, case)
    (case / "private.csv").write_text("private")
    with pytest.raises(ValueError, match="unlisted"):
        load_fixture(case)


@pytest.mark.parametrize(
    "name", ["../catia.stp", "/catia.stp", "C:/catia.stp", "input\\catia.stp"]
)
def test_fixture_rejects_path_escape(name):
    with pytest.raises(ValueError, match="Unsafe"):
        fixture_path(DEFAULT_CASE, name)


def _report(manifest):
    """构造一份理想测量，测试单个异常不能被其他通过层掩盖。"""
    surface = {
        direction: {"samples": 400, "max_mm": 0.0, "rms_mm": 0.0}
        for direction in DIRECTIONS
    }
    return {
        "properties": {
            name: {
                "valid": True,
                "closed": True,
                "solids": 1,
                "volume_mm3": 1.0,
                "center_of_mass_mm": [0, 0, 0],
                "bounding_box_mm": [0, 1, 0, 1, 0, 1],
            }
            for name in ("native", "step", "catia")
        },
        "exchange": {
            "volume_relative": 0,
            "centroid_max_mm": 0,
            "bbox_max_mm": 0,
            "surface": deepcopy(surface),
        },
        "cross_backend": {
            "volume_relative": 0,
            "centroid_max_mm": 0,
            "bbox_max_mm": 0,
            "surface": deepcopy(surface),
        },
        "stations": [
            {
                "requested_x_mm": row["x_mm"],
                "complete": True,
                "section": {
                    direction: {**row, "samples": 240}
                    for direction, row in surface.items()
                },
            }
            for row in manifest["sampling"]["stations"]
        ],
    }


@pytest.mark.parametrize(
    ("layer", "key"),
    [
        ("exchange", "volume_relative"),
        ("exchange", "centroid_max_mm"),
        ("cross_backend", "volume_relative"),
        ("cross_backend", "centroid_max_mm"),
        ("cross_backend", "bbox_max_mm"),
    ],
)
def test_large_property_differences_remain_measurements_for_humans(layer, key):
    manifest = load_fixture()
    report = _report(manifest)
    report[layer][key] = 1000
    coverage = validate_measurements(report, manifest)
    assert coverage["complete_stations"] == 46
    assert "tolerances" not in manifest
    assert manifest["decision_policy"] == "human_only"


@pytest.mark.parametrize("layer", ["exchange", "cross_backend"])
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_large_surface_differences_are_not_usability_verdicts(layer, direction):
    manifest = load_fixture()
    report = _report(manifest)
    report[layer]["surface"][direction]["max_mm"] = 1000
    assert validate_measurements(report, manifest)["recorded_stations"] == 46


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_measurement_is_never_a_pass(value):
    manifest = load_fixture()
    report = _report(manifest)
    report["exchange"]["volume_relative"] = value
    with pytest.raises(ValueError, match="finite numeric"):
        validate_measurements(report, manifest)


def test_incomplete_stations_are_reported_but_missing_records_are_rejected():
    manifest = load_fixture()
    report = _report(manifest)
    for row in report["stations"][:2]:
        row["complete"] = False
        row["surface_diagnostic"] = row.pop("section")
        row["surface_diagnostic"][DIRECTIONS[1]]["max_mm"] = 1000
    coverage = validate_measurements(report, manifest)
    assert coverage["complete_stations"] == 44
    assert coverage["incomplete_stations_mm"] == [
        row["x_mm"] for row in manifest["sampling"]["stations"][:2]
    ]
    report["stations"].pop()
    with pytest.raises(ValueError, match="coverage"):
        validate_measurements(report, manifest)


@pytest.mark.parametrize("case_path", GOLDEN_CASE_PATHS)
def test_only_approved_step_is_allowed_in_sdist_and_never_in_wheel(case_path):
    name = f"autoblade-{_source_version()}/" + case_path + "catia.stp"
    _validate_archive_names([name], artifact="sdist")
    for artifact, path in (
        ("wheel", name),
        ("sdist", name.replace("catia.stp", "private.stp")),
        ("sdist", name.replace("catia.stp", "catia.FCStd")),
    ):
        with pytest.raises(ValidationError, match="forbidden"):
            _validate_archive_names([path], artifact=artifact)


def test_sdist_fingerprints_actual_fixture_bytes():
    contents = {}
    for prefix in GOLDEN_CASE_PATHS:
        case = DEFAULT_CASE.parent / Path(prefix).name
        manifest = load_fixture(case)
        contents.update(
            {prefix + name: (case / name).read_bytes() for name in manifest["files"]}
        )
        contents[prefix + "manifest.json"] = json.dumps(manifest).encode()
    _validate_golden_files(contents.__getitem__, set(contents), "")
    contents[GOLDEN_CASE_PATH + "catia.stp"] += b" "
    with pytest.raises(ValidationError, match="fingerprint"):
        _validate_golden_files(contents.__getitem__, set(contents), "")


@pytest.mark.parametrize("case_path", GOLDEN_CASE_PATHS[1:])
def test_new_public_cases_have_explicit_authorization_and_matching_topology(case_path):
    case = DEFAULT_CASE.parent / Path(case_path).name
    manifest = load_fixture(case)
    assert manifest["authorization"]["public_redistribution"] is True
    assert manifest["authorization"]["date"] == "2026-09-21"
    assert manifest["decision_policy"] == "human_only"
    assert "tolerances" not in manifest
    plan = build_blade_input_plan(
        case / manifest["input"]["sections"],
        case / "input/airfoils",
        manifest["input"]["airfoil"],
    )
    assert plan.is_sharp == (manifest["input"]["trailing_edge"] == "sharp")
    assert [len(airfoil.points) for airfoil in plan.airfoils] == manifest["input"][
        "point_counts"
    ]


def test_standard_report_keeps_large_errors_and_requires_human_judgment(tmp_path):
    manifest = load_fixture()
    report = _report(manifest)
    report["cross_backend"]["volume_relative"] = 1000
    report.update(
        case_id="example",
        status="measured",
        freecad_version="1.1.3",
        occt_version="7.8.1",
        baseline_sha256="reference",
        artifacts={"native_sha256": "native", "step_sha256": "step"},
        coverage=validate_measurements(report, manifest),
    )
    write_error_report(report, tmp_path)
    text = (tmp_path / "error-report.md").read_text(encoding="utf-8")
    assert "由人类判断" in text and "1000" in text
    assert "Hausdorff" in text and "46 / 46 / 46" in text
    table = (tmp_path / "error-report.csv").read_text(encoding="utf-8-sig")
    assert "cross_backend,volume_relative,ratio,,,1000" in table
