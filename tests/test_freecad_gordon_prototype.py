import json
import sys
from pathlib import Path

import pytest

from autoblade.core.input_plan import AirfoilInput, BladeInputPlan


# Hatch 的开发环境只把 ``src`` 加入 sys.path；阶段 2 原型刻意留在 wheel 外，
# 因此测试显式加入仓库根目录，而不改变产品包的导入边界。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.freecad_gordon_prototype.launch import build_command
from scripts.freecad_gordon_prototype.protocol import (
    ALGORITHM_ID,
    REQUEST_SCHEMA,
    ProtocolError,
    canonical_json,
    request_sha256,
    validate_request,
)
from scripts.freecad_gordon_prototype.request import (
    apply_global_transform,
    build_request,
)


def _plan(tmp_path: Path, *, sharp: bool = True) -> BladeInputPlan:
    section_path = tmp_path / "sections.csv"
    section_path.write_text("closed input fixture\n", encoding="utf-8")
    airfoil_path = tmp_path / "foil.csv"
    airfoil_path.write_text("closed airfoil fixture\n", encoding="utf-8")
    last = (0.0, -0.75, 0.0) if sharp else (0.0, -0.74, -0.01)
    points = (
        (0.0, -0.75, 0.0),
        (0.0, 0.25, 0.1),
        last,
    )
    return BladeInputPlan(
        mode="single",
        blade_sections_path=section_path,
        sections=(
            {
                "idx": 1,
                "airfoil_filename": "foil.csv",
                "chord_m": 0.1,
                "translate_x_m": 0.0,
                "translate_y_m": 0.0,
                "translate_z_m": 0.0,
                "rotation_deg": 0.0,
            },
            {
                "idx": 2,
                "airfoil_filename": "foil.csv",
                "chord_m": 0.08,
                "translate_x_m": 0.5,
                "translate_y_m": 0.0,
                "translate_z_m": 0.0,
                "rotation_deg": 10.0,
            },
        ),
        airfoils=(
            AirfoilInput(
                filename="foil.csv",
                path=airfoil_path,
                points=points,
                is_sharp=sharp,
            ),
        ),
        is_sharp=sharp,
    )


@pytest.mark.parametrize(("sharp", "topology"), [(True, "sharp"), (False, "blunt")])
def test_closed_request_has_stable_protocol_and_no_source_paths(
    tmp_path: Path,
    sharp: bool,
    topology: str,
) -> None:
    request = build_request(_plan(tmp_path, sharp=sharp))

    assert request["schema_version"] == REQUEST_SCHEMA
    assert request["length_unit"] == "m"
    assert request["trailing_edge_topology"] == topology
    assert request["modeling"]["algorithm"] == ALGORITHM_ID
    assert request["airfoils"]["foil.csv"]["point_count"] == 3
    assert request["source"]["blade_sections"] == "sections.csv"
    assert str(tmp_path) not in canonical_json(request)
    assert len(request_sha256(request)) == 64
    assert validate_request(json.loads(json.dumps(request))) == request


def test_request_rejects_unknown_fields_and_topology_mismatch(tmp_path: Path) -> None:
    request = build_request(_plan(tmp_path))
    request["unexpected"] = True

    with pytest.raises(ProtocolError, match=r"unknown \[unexpected\]"):
        validate_request(request)

    request.pop("unexpected")
    request["trailing_edge_topology"] = "blunt"
    with pytest.raises(ProtocolError, match="does not match blunt"):
        validate_request(request)


def test_request_rejects_path_like_artifact_name(tmp_path: Path) -> None:
    request = build_request(_plan(tmp_path))
    request["artifacts"]["native_model"] = "nested/blade.FCStd"

    with pytest.raises(ProtocolError, match="must be a basename"):
        validate_request(request)


def test_global_transform_updates_closed_sections_and_records_derivation(
    tmp_path: Path,
) -> None:
    request = build_request(_plan(tmp_path))

    transformed = apply_global_transform(
        request,
        scale=1.7,
        rotation_x_deg=37.0,
        translate_x_m=0.2,
        translate_y_m=-0.1,
        translate_z_m=0.3,
    )

    first = transformed["sections"][0]
    second = transformed["sections"][1]
    assert first["chord_m"] == pytest.approx(0.17)
    assert first["rotation_deg"] == pytest.approx(37.0)
    assert (first["translate_x_m"], first["translate_y_m"], first["translate_z_m"]) == pytest.approx((0.2, -0.1, 0.3))
    assert second["translate_x_m"] == pytest.approx(1.05)
    assert transformed["source"]["derived_transform"] == {
        "scale": 1.7,
        "rotation_x_deg": 37.0,
        "translate_x_m": 0.2,
        "translate_y_m": -0.1,
        "translate_z_m": 0.3,
    }
    assert "derived_transform" not in request["source"]


def test_flatpak_command_uses_fixed_runner_without_shell(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    output_dir = tmp_path / "output"

    command = build_command(runner=runner, output_dir=output_dir)

    assert command[:4] == [
        "flatpak",
        "run",
        "--command=FreeCADCmd",
        "org.freecad.FreeCAD",
    ]
    assert command[-1] == str(runner)
    assert all("shell" not in argument for argument in command)
