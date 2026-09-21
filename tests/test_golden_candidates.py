"""合成矩阵和待批准契约的纯 Python 回归；不创建 CAD 会话。"""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoblade.core.backend import BackendName
from autoblade.core.geometry import transform_point
from scripts.golden.candidate_contract import PENDING, affine_residual, load_candidate
from scripts.golden.candidates import (
    SECTIONS,
    TRANSFORMS,
    jobs,
    prepare,
    profile_points,
    transformed_sections,
)
from scripts.golden.fixture import load_fixture


@pytest.mark.parametrize("count", [121, 153, 181, 1000])
@pytest.mark.parametrize("gap", [0.0, 0.004])
def test_synthetic_profiles_preserve_point_count_order_and_exact_topology(count, gap):
    points = profile_points(count, gap=gap)
    assert len(points) == count
    assert (points[0] == points[-1]) == (gap == 0)
    assert points[0] == (0, 1, gap / 2)
    assert points[-1] == (0, 1, -gap / 2)
    leading = min(range(count), key=lambda i: points[i][1])
    assert 0 < leading < count - 1 and points[leading] == (0, 0, 0)
    assert all(a[1] > b[1] for a, b in zip(points[:leading], points[1 : leading + 1]))
    assert all(a[1] < b[1] for a, b in zip(points[leading:], points[leading + 1 :]))


def test_prepared_matrix_is_self_contained_unapproved_and_has_dense_smoke(tmp_path):
    matrix = tmp_path / "matrix"
    prepare(matrix)
    planned = jobs(matrix, BackendName.FREECAD, tmp_path / "freecad")
    assert len(planned) == 7
    assert len(jobs(matrix, BackendName.CATIA, matrix)) == 6
    for case, data, job in planned:
        assert data["approval_status"] == PENDING
        assert data["origin"]["kind"] == "project_defined_analytic_geometry"
        assert len(data["sampling"]["stations"]) == 79
        assert not any(row["allow_incomplete"] for row in data["sampling"]["stations"])
        assert len(job.input_plan.sections) == 5
        with pytest.raises(FileNotFoundError):
            load_fixture(case)
    dense = next(job for _, data, job in planned if data["role"] == "performance")
    assert len(dense.input_plan.airfoils[0].points) == 1000
    with pytest.raises(FileExistsError):
        prepare(matrix)


def test_candidate_input_changes_and_output_conflicts_fail_preflight(tmp_path):
    matrix = tmp_path / "matrix"
    prepare(matrix)
    (matrix / "affine-25/catia").mkdir()
    with pytest.raises(FileExistsError, match="overwrite"):
        jobs(matrix, BackendName.CATIA, matrix)
    assert not (matrix / "single-sharp/catia").exists()
    (matrix / "single-blunt/input/airfoils/synthetic-1.csv").write_text("changed")
    with pytest.raises(ValueError, match="fingerprint"):
        load_candidate(matrix / "single-blunt", require_catia=False)


def test_candidate_does_not_claim_approval_after_label_edit(tmp_path):
    matrix = tmp_path / "matrix"
    prepare(matrix)
    path = matrix / "single-sharp/candidate.json"
    data = json.loads(path.read_text())
    data["approval_status"] = "approved"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unapproved"):
        load_candidate(path.parent, require_catia=False)


@pytest.mark.parametrize("name", TRANSFORMS)
def test_global_transform_applies_to_section_origins_and_twist(name):
    transform = TRANSFORMS[name]
    for source, derived in zip(SECTIONS, transformed_sections(transform), strict=True):
        assert derived[0] == source[0]
        assert derived[1] == pytest.approx(source[1] * transform["scale"])
        assert derived[2:5] == pytest.approx(
            transform_point(
                *source[2:5],
                transform["rotation_x_deg"],
                transform["scale"],
                *transform["translation_m"],
            )
        )
        assert derived[5] == source[5] + transform["rotation_x_deg"]


def test_affine_residual_uses_si_translation_and_cubic_scale_without_verdict():
    base = {"volume_mm3": 10, "center_of_mass_mm": [10, 20, 30]}
    transform = {"scale": 2, "rotation_x_deg": 90, "translation_m": [0.1, -0.2, 0.3]}
    actual = {"volume_mm3": 80, "center_of_mass_mm": [120, -260, 340]}
    residual = affine_residual(base, actual, transform)
    assert residual["volume_relative"] == 0
    assert residual["centroid_max_mm"] == pytest.approx(0)
    assert "within_existing_limits" not in residual
    wrong = deepcopy(actual)
    wrong["center_of_mass_mm"][0] += 0.06
    assert affine_residual(base, wrong, transform)["centroid_max_mm"] == pytest.approx(
        0.06
    )
    wrong = deepcopy(actual)
    wrong["volume_mm3"] *= 1.001
    assert affine_residual(base, wrong, transform)["volume_relative"] == pytest.approx(
        0.001
    )
