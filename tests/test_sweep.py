import json
from pathlib import Path

import pytest

from autoblade.commands.sweep import run_sweep_command
from autoblade.config.manager import ConfigManager
from autoblade.core.input_validation import InputValidationError
from autoblade.core.jobs import BuildResult
from autoblade.core.sweep import SweepPlan, SweepPlanner


SHARP_AIRFOIL = """x,y,z
0,1,0
0,0.5,0.1
0,0,0
0,0.5,-0.1
0,1,0
"""

SECTIONS = """idx,scale/m,translate_x/m,translate_y/m,translate_z/m,rotate/deg
1,0.1,0,0,0,10
2,0.08,1,0,0,5
"""

SELF_CONTAINED_SECTIONS = """idx,scale/m,translate_x/m,translate_y/m,translate_z/m,rotate/deg,airfoil
1,0.1,0,0,0,10,foil-a.csv
2,0.08,1,0,0,5,foil-b.csv
"""


def _inputs(tmp_path: Path) -> tuple[Path, Path, list[str]]:
    airfoil_dir = tmp_path / "airfoils"
    section_dir = tmp_path / "sections"
    airfoil_dir.mkdir()
    section_dir.mkdir()
    for filename in ("foil-a.csv", "foil-b.csv", "unselected.csv"):
        (airfoil_dir / filename).write_text(SHARP_AIRFOIL, encoding="utf-8")
    sections = [f"blade_sections-{index}.csv" for index in range(1, 6)]
    for filename in [*sections, "blade_sections-extra.csv"]:
        (section_dir / filename).write_text(SECTIONS, encoding="utf-8")
    (section_dir / "self-contained.csv").write_text(
        SELF_CONTAINED_SECTIONS,
        encoding="utf-8",
    )
    return airfoil_dir, section_dir, sections


def _planner(
    tmp_path: Path,
    airfoil_dir: Path,
    section_dir: Path,
    *,
    output_name_template: str = "{blade}",
) -> SweepPlanner:
    return SweepPlanner(
        tmp_path / "output",
        airfoil_dir=airfoil_dir,
        blade_sections_dir=section_dir,
        output_name_template=output_name_template,
        author="",
    )


def test_sweep_planner_generates_ten_airfoil_major_jobs_from_explicit_inputs(
    tmp_path: Path,
) -> None:
    airfoil_dir, section_dir, sections = _inputs(tmp_path)

    plan = _planner(tmp_path, airfoil_dir, section_dir).plan(
        ["foil-b.csv", "foil-a.csv", "foil-b.csv"],
        reversed(sections),
    )

    assert len(plan.jobs) == 10
    assert [
        (job.airfoil_filename, job.blade_sections_filename)
        for job in plan.jobs
    ] == [
        (airfoil, section)
        for airfoil in ("foil-a.csv", "foil-b.csv")
        for section in sections
    ]
    assert "unselected.csv" not in plan.airfoil_filenames
    assert "blade_sections-extra.csv" not in plan.blade_sections_filenames


def test_sweep_manifest_is_stable_json_with_complete_ordered_job_list(
    tmp_path: Path,
) -> None:
    airfoil_dir, section_dir, sections = _inputs(tmp_path)
    plan = _planner(tmp_path, airfoil_dir, section_dir).plan(
        ["foil-b.csv", "foil-a.csv"],
        sections[:2],
    )

    serialized = plan.to_json()
    manifest = json.loads(serialized)

    assert serialized == plan.to_json()
    assert manifest == plan.as_dict()
    assert manifest["schema_version"] == 3
    assert manifest["combination"] == "cartesian"
    assert manifest["selection"] == {
        "airfoils": ["foil-a.csv", "foil-b.csv"],
        "blade_sections": sections[:2],
    }
    assert [job["job_id"] for job in manifest["jobs"]] == [
        "sweep-0001",
        "sweep-0002",
        "sweep-0003",
        "sweep-0004",
    ]
    assert all(len(job["artifacts"]) == 2 for job in manifest["jobs"])


def test_sweep_rejects_self_contained_section_definition(tmp_path: Path) -> None:
    airfoil_dir, section_dir, _ = _inputs(tmp_path)

    with pytest.raises(InputValidationError, match="only accepts six-column"):
        _planner(tmp_path, airfoil_dir, section_dir).plan(
            ["foil-a.csv"],
            ["self-contained.csv"],
        )


def test_sweep_rejects_duplicate_output_targets(tmp_path: Path) -> None:
    airfoil_dir, section_dir, sections = _inputs(tmp_path)

    with pytest.raises(ValueError, match="Sweep output conflict"):
        _planner(
            tmp_path,
            airfoil_dir,
            section_dir,
            output_name_template="same-name",
        ).plan(["foil-a.csv"], sections[:2])


def test_sweep_dry_run_shows_manifest_and_conflicts_without_executor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_file = workspace / "config.toml"
    config_file.write_text(
        """version = "4.0.0"

[paths]
input_dir = "."
output_dir = "output"
airfoil_dir = "airfoils"
blade_sections_dir = "sections"

[defaults]
author = ""
output_name_template = "{blade}"
""",
        encoding="utf-8",
    )
    airfoil_dir, section_dir, sections = _inputs(workspace)
    existing = workspace / "output" / "foil-a" / "foil-a_blade-1.CATPart"
    existing.parent.mkdir(parents=True)
    existing.touch()

    def forbidden_executor(_jobs):
        raise AssertionError("dry-run must not call the Executor")

    result = run_sweep_command(
        ["foil-b.csv", "foil-a.csv"],
        sections[:2],
        None,
        True,
        False,
        config_manager=ConfigManager(config_file),
        sweep_processor=forbidden_executor,
    )
    output = capsys.readouterr().out

    assert isinstance(result, SweepPlan)
    assert len(result.jobs) == 4
    assert "Combination: cartesian (2 x 2 = 4)" in output
    assert "Existing output conflicts: 1" in output
    assert '"job_id": "sweep-0004"' in output
    assert "Dry run complete; CAD was not started." in output


def test_non_interactive_sweep_requires_both_explicit_dimensions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_file = workspace / "config.toml"
    config_file.write_text(
        """version = "4.0.0"

[paths]
input_dir = "."
output_dir = "output"
airfoil_dir = "airfoils"
blade_sections_dir = "sections"
""",
        encoding="utf-8",
    )
    _inputs(workspace)

    with pytest.raises(ValueError, match="requires at least one explicit"):
        run_sweep_command(
            ["foil-a.csv"],
            [],
            None,
            True,
            False,
            config_manager=ConfigManager(config_file),
        )


def test_sweep_execution_delegates_complete_plan_to_shared_executor(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_file = workspace / "config.toml"
    config_file.write_text(
        """version = "4.0.0"

[paths]
input_dir = "."
output_dir = "output"
airfoil_dir = "airfoils"
blade_sections_dir = "sections"

[defaults]
author = ""
output_name_template = "{blade}"
""",
        encoding="utf-8",
    )
    _, _, sections = _inputs(workspace)
    received = []

    def fake_executor(jobs):
        received.extend(jobs)
        return [BuildResult(job=job, status="success") for job in jobs]

    results = run_sweep_command(
        ["foil-b.csv", "foil-a.csv"],
        sections[:2],
        None,
        False,
        False,
        config_manager=ConfigManager(config_file),
        sweep_processor=fake_executor,
    )

    assert isinstance(results, list)
    assert len(results) == len(received) == 4
    assert [
        (job.airfoil_filename, job.blade_sections_filename)
        for job in received
    ] == [
        ("foil-a.csv", "blade_sections-1.csv"),
        ("foil-a.csv", "blade_sections-2.csv"),
        ("foil-b.csv", "blade_sections-1.csv"),
        ("foil-b.csv", "blade_sections-2.csv"),
    ]
