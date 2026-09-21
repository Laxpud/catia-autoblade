"""人工检查包的身份与数据保真测试；全部使用假模型字节，不加载真实 CAD。"""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.golden.candidates import prepare
from scripts.golden.fixture import DIRECTIONS, sha256
from scripts.golden.review import package_review, write_json


@pytest.fixture
def sources(tmp_path):
    matrix, models, measures = (
        tmp_path / name for name in ("matrix", "models", "measures")
    )
    prepare(matrix)
    name = "single-sharp"
    case, model, measured = matrix / name, models / name / "model", measures / name
    model.mkdir(parents=True)
    measured.mkdir(parents=True)
    (case / "catia").mkdir()
    for path in (
        model / "blade.FCStd",
        model / "blade.stp",
        case / "catia/blade.CATPart",
        case / "catia/blade.stp",
    ):
        path.write_bytes(path.name.encode())
    manifest_digest = sha256((case / "candidate.json").read_bytes())
    write_json(
        case / "catia/record.json",
        {
            "status": "generated_candidate",
            "input_manifest_sha256": manifest_digest,
            "artifacts_sha256": {
                p.name: sha256(p.read_bytes()) for p in (case / "catia").iterdir()
            },
        },
    )
    props = {"volume_mm3": 10, "center_of_mass_mm": [1, 2, 3]}
    record = {
        "case_id": name,
        "role": "golden_candidate",
        "input_manifest_sha256": manifest_digest,
        "artifacts_sha256": {p.name: sha256(p.read_bytes()) for p in model.iterdir()},
        "request_sha256": "request",
        "properties": props,
        "build_seconds": 1,
        "peak_rss_kib": 100,
    }
    write_json(
        models / "summary.json",
        {"schema": "autoblade.golden.candidate-build/v1", "cases": [record]},
    )
    surface = {direction: {"max_mm": 0.03, "rms_mm": 0.01} for direction in DIRECTIONS}
    report = {
        "status": "measured_candidate",
        "freecad_version": "1.1.3",
        "occt_version": "7.9.3",
        "manifest_sha256": manifest_digest,
        "baseline_sha256": sha256((case / "catia/blade.stp").read_bytes()),
        "artifacts": {
            "native_sha256": record["artifacts_sha256"]["blade.FCStd"],
            "step_sha256": record["artifacts_sha256"]["blade.stp"],
            "request_sha256": "request",
        },
        "properties": {"native": props, "catia": props},
        "exchange": {},
        "cross_backend": {
            "volume_relative": 0.01,
            "centroid_max_mm": 0.1,
            "bbox_max_mm": 0.2,
            "surface": surface,
        },
        "stations": [
            {"complete": True, "section": surface},
            {"complete": False, "surface_diagnostic": surface},
        ],
        "elapsed_seconds": 1,
        "peak_rss_kib": 100,
        "failures": ["old hypothetical threshold verdict"],
    }
    write_json(measured / "result.json", report)
    return matrix, models, measures, report


def test_review_preserves_values_and_bytes_without_exporting_a_verdict(
    sources, tmp_path
):
    matrix, models, measures, report = sources
    original = (measures / "single-sharp/result.json").read_bytes()
    output = tmp_path / "review"
    result = package_review(matrix, models, measures, output)
    exported = json.loads((output / "single-sharp/measurements.json").read_text())
    assert "failures" not in exported
    for key in ("properties", "exchange", "cross_backend", "stations"):
        assert exported[key] == report[key]
    assert (measures / "single-sharp/result.json").read_bytes() == original
    row = result["cases"][0]
    assert row["volume_difference_percent"] == 1
    assert row["complete_stations"] == 1 and row["total_stations"] == 2
    for path, digest in json.loads((output / "SHA256SUMS.json").read_text()).items():
        assert sha256((output / path).read_bytes()) == digest
    for filename in ("blade.FCStd", "blade.stp"):
        assert (output / "single-sharp/FreeCAD" / filename).read_bytes() == (
            models / "single-sharp/model" / filename
        ).read_bytes()
    with pytest.raises(FileExistsError):
        package_review(matrix, models, measures, output)


@pytest.mark.parametrize("target", ["model", "report"])
def test_review_rejects_stale_artifacts_before_creating_directory(
    sources, tmp_path, target
):
    matrix, models, measures, report = sources
    if target == "model":
        (models / "single-sharp/model/blade.FCStd").write_bytes(b"changed")
    else:
        report["artifacts"]["native_sha256"] = "unrelated model"
        write_json(measures / "single-sharp/result.json", report)
    output = tmp_path / "review"
    with pytest.raises(ValueError, match="fingerprint|identity"):
        package_review(matrix, models, measures, output)
    assert not output.exists()
