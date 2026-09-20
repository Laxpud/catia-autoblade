"""校验源码版本、CLI、Git 标签和构建产物中的发布元数据。"""

from __future__ import annotations

import argparse
import ast
from configparser import ConfigParser
from email.message import Message
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tomllib
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
VERSION_PATH = PROJECT_ROOT / "src" / "autoblade" / "__init__.py"
README_PATH = PROJECT_ROOT / "README.md"
EXPECTED_PROJECT_NAME = "autoblade"
EXPECTED_SUMMARY = "AutoBlade command-line tool for creating blade models with CATIA"
EXPECTED_REQUIRES_PYTHON = ">=3.14,<3.15"
EXPECTED_CONSOLE_SCRIPTS = {
    "autoblade": "autoblade.cli:app",
    "autoblade-create": "autoblade.cli:create_entrypoint",
    "autoblade-batch": "autoblade.cli:batch_entrypoint",
}
REQUIRED_WHEEL_FILES = {
    "autoblade/_distribution.py",
    "autoblade/adapters/cad/freecad/runner.py",
    "autoblade/adapters/cad/freecad/protocol.py",
    "autoblade/adapters/cad/freecad/probe.py",
    "autoblade/resources/workspace/config.toml",
    "autoblade/resources/airfoil_library/manifest.json",
    "autoblade/resources/airfoil_library/airfoil1_sharp.csv",
    "autoblade/resources/airfoil_library/airfoil2_sharp.csv",
    "autoblade/resources/airfoil_library/airfoil3_sharp.csv",
    (
        "autoblade/resources/workspace/blade_sections/"
        "example-blade-sections.csv"
    ),
}
REQUIRED_SDIST_PATHS = {
    "CONTEXT.md",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "scripts/check.ps1",
    "scripts/check-linux.sh",
    "scripts/smoke_installed_wheel.sh",
    "scripts/validate_distribution.py",
    "src/autoblade/__init__.py",
    "tests/conftest.py",
}
FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    ".uv",
    ".venv",
    "build",
    "dist",
    "output",
    "__pycache__",
}
FORBIDDEN_SUFFIXES = {
    ".catpart",
    ".catproduct",
    ".fcstd",
    ".log",
    ".pyc",
    ".stp",
}


class ValidationError(RuntimeError):
    """构建元数据违反已发布契约。"""


def _source_version() -> str:
    """从 Hatchling 使用的源文件读取字面量版本，避免导入运行时模块。"""
    tree = ast.parse(VERSION_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        ):
            return node.value.value
    raise ValidationError(f"Literal __version__ not found in {VERSION_PATH}")


def _read_wheel_metadata(dist_dir: Path, version: str) -> Message:
    wheel_pattern = f"autoblade-{version}-*.whl"
    wheels = sorted(dist_dir.glob(wheel_pattern))
    if len(wheels) != 1:
        raise ValidationError(
            f"Expected exactly one {wheel_pattern} in {dist_dir}, found {len(wheels)}"
        )

    with ZipFile(wheels[0]) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ValidationError(
                f"Expected one wheel METADATA file, found {len(metadata_names)}"
            )
        content = archive.read(metadata_names[0]).decode("utf-8")
    return Parser().parsestr(content)


def _wheel_path(dist_dir: Path, version: str) -> Path:
    wheels = sorted(dist_dir.glob(f"autoblade-{version}-*.whl"))
    if len(wheels) != 1:
        raise ValidationError(
            f"Expected exactly one wheel for {version}, found {len(wheels)}"
        )
    wheel = wheels[0]
    if not wheel.name.endswith("-py3-none-any.whl"):
        raise ValidationError(
            f"Expected a platform-neutral Python wheel, found {wheel.name}"
        )
    return wheel


def _sdist_path(dist_dir: Path, version: str) -> Path:
    path = dist_dir / f"autoblade-{version}.tar.gz"
    if not path.is_file():
        raise ValidationError(f"Expected sdist not found: {path}")
    return path


def _read_sdist_metadata(dist_dir: Path, version: str) -> Message:
    sdist = dist_dir / f"autoblade-{version}.tar.gz"
    if not sdist.is_file():
        raise ValidationError(f"Expected sdist not found: {sdist}")

    with tarfile.open(sdist, "r:gz") as archive:
        metadata_members = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/PKG-INFO")
        ]
        if len(metadata_members) != 1:
            raise ValidationError(
                f"Expected one sdist PKG-INFO file, found {len(metadata_members)}"
            )
        extracted = archive.extractfile(metadata_members[0])
        if extracted is None:
            raise ValidationError("Unable to read sdist PKG-INFO")
        content = extracted.read().decode("utf-8")
    return Parser().parsestr(content)


def _validate_metadata(metadata: Message, version: str, artifact: str) -> None:
    """验证 wheel 与 sdist 必须一致的身份、平台和依赖元数据。"""
    expected_headers = {
        "Name": EXPECTED_PROJECT_NAME,
        "Version": version,
        "License-File": "LICENSE",
        "Summary": EXPECTED_SUMMARY,
    }
    for header, expected in expected_headers.items():
        if metadata.get(header) != expected:
            raise ValidationError(
                f"{artifact} {header} mismatch: {metadata.get(header)!r} != {expected!r}"
            )

    requires_python = metadata.get("Requires-Python", "")
    if set(requires_python.split(",")) != set(EXPECTED_REQUIRES_PYTHON.split(",")):
        raise ValidationError(
            f"{artifact} Requires-Python mismatch: {requires_python!r} != "
            f"{EXPECTED_REQUIRES_PYTHON!r}"
        )

    classifiers = set(metadata.get_all("Classifier", []))
    required_classifiers = {
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.14",
    }
    missing_classifiers = required_classifiers - classifiers
    if missing_classifiers:
        raise ValidationError(
            f"{artifact} missing classifiers: {sorted(missing_classifiers)}"
        )
    if "Operating System :: OS Independent" in classifiers:
        raise ValidationError(f"{artifact} must not claim OS Independent")

    requirements = metadata.get_all("Requires-Dist", [])
    if not any(
        requirement.startswith("pywin32==311;")
        and "sys_platform == 'win32'" in requirement
        for requirement in requirements
    ):
        raise ValidationError(
            f"{artifact} does not declare the supported pywin32 requirement: "
            f"{requirements}"
        )

    project_urls = metadata.get_all("Project-URL", [])
    for label in ("Documentation", "Issues", "Repository"):
        if not any(url.startswith(f"{label}, https://") for url in project_urls):
            raise ValidationError(f"{artifact} missing HTTPS Project-URL: {label}")

    relative_targets = _relative_markdown_targets(metadata.get_payload())
    if relative_targets:
        raise ValidationError(
            f"{artifact} long description contains relative links: {relative_targets}"
        )


def _validate_pyproject() -> None:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project = data["project"]
    if project["name"] != EXPECTED_PROJECT_NAME:
        raise ValidationError("pyproject project name changed unexpectedly")
    if project["description"] != EXPECTED_SUMMARY:
        raise ValidationError("pyproject description differs from product identity")
    if project["requires-python"] != EXPECTED_REQUIRES_PYTHON:
        raise ValidationError("pyproject requires-python differs from support policy")
    if project.get("dynamic") != ["version"]:
        raise ValidationError("pyproject must keep dynamic versioning")
    if project.get("scripts") != EXPECTED_CONSOLE_SCRIPTS:
        raise ValidationError("pyproject console entry points differ from CLI contract")
    version_path = data["tool"]["hatch"]["version"]["path"]
    if version_path != "src/autoblade/__init__.py":
        raise ValidationError("Hatchling version path differs from source contract")
    wheel_packages = data["tool"]["hatch"]["build"]["targets"]["wheel"][
        "packages"
    ]
    if wheel_packages != ["src/autoblade"]:
        raise ValidationError("wheel package whitelist changed unexpectedly")
    sdist_include = set(
        data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    )
    required_sdist_sources = {
        "/CONTEXT.md",
        "/LICENSE",
        "/README.md",
        "/pyproject.toml",
        "/src",
        "/tests",
        "/scripts",
        "/uv.lock",
    }
    if not required_sdist_sources <= sdist_include:
        raise ValidationError(
            "sdist whitelist is missing rebuild sources: "
            f"{sorted(required_sdist_sources - sdist_include)}"
        )


def _validate_readme_links() -> None:
    """PyPI 长描述不能依赖 GitHub 仓库上下文解析相对 Markdown 链接。"""
    content = README_PATH.read_text(encoding="utf-8")
    relative_targets = _relative_markdown_targets(content)
    if relative_targets:
        raise ValidationError(
            f"README contains relative long-description links: {relative_targets}"
        )


def _relative_markdown_targets(content: str) -> list[str]:
    """返回需要仓库上下文才能解析的 Markdown 链接目标。"""
    relative_targets: list[str] = []
    for target in re.findall(r"\]\(([^)]+)\)", content):
        normalized = target.strip().lower()
        if not normalized.startswith(("https://", "http://", "mailto:", "#")):
            relative_targets.append(target)
    return relative_targets


def _validate_cli_version(version: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "autoblade.cli", "--version"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    expected = f"autoblade {version}"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise ValidationError(
            "CLI version mismatch: "
            f"code={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
        )


def _validate_distribution_contents(dist_dir: Path, version: str) -> None:
    """校验归档白名单并写出排序清单，便于发布审计和重复构建比较。"""
    wheel_path = _wheel_path(dist_dir, version)
    sdist_path = _sdist_path(dist_dir, version)
    with ZipFile(wheel_path) as archive:
        wheel_names = sorted(archive.namelist())
        _validate_archive_names(wheel_names, artifact="wheel")
        missing_wheel = REQUIRED_WHEEL_FILES - set(wheel_names)
        if missing_wheel:
            raise ValidationError(
                f"wheel missing initialization resources: {sorted(missing_wheel)}"
            )
        allowed_prefixes = (
            "autoblade/",
            f"autoblade-{version}.dist-info/",
        )
        unexpected = [
            name for name in wheel_names if not name.startswith(allowed_prefixes)
        ]
        if unexpected:
            raise ValidationError(f"wheel contains unexpected roots: {unexpected}")
        _validate_vendor_files(archive.read, "autoblade/_vendor/curveswb/")
        _validate_wheel_entry_points(archive, version)
        _validate_no_local_path_leak(
            ((name, archive.read(name)) for name in wheel_names),
            artifact="wheel",
        )

    sdist_root = f"autoblade-{version}/"
    with tarfile.open(sdist_path, "r:gz") as archive:
        file_members = [member for member in archive.getmembers() if member.isfile()]
        sdist_names = sorted(member.name for member in file_members)
        _validate_archive_names(sdist_names, artifact="sdist")
        relative_names = {
            name.removeprefix(sdist_root)
            for name in sdist_names
            if name.startswith(sdist_root)
        }
        missing_sdist = REQUIRED_SDIST_PATHS - relative_names
        if missing_sdist:
            raise ValidationError(
                f"sdist missing rebuild sources: {sorted(missing_sdist)}"
            )

        def sdist_contents():
            for member in file_members:
                extracted = archive.extractfile(member)
                if extracted is not None:
                    yield member.name, extracted.read()

        def read_sdist(name):
            extracted = archive.extractfile(name)
            if extracted is None:
                raise ValidationError(f"Missing source file: {name}")
            return extracted.read()

        _validate_vendor_files(read_sdist, sdist_root + "src/autoblade/_vendor/curveswb/")
        _validate_no_local_path_leak(sdist_contents(), artifact="sdist")

    _write_content_manifest(dist_dir, wheel_path.name, wheel_names)
    _write_content_manifest(dist_dir, sdist_path.name, sdist_names)


def _validate_vendor_files(read_file, prefix: str) -> None:
    """从归档实际字节验证未修改依赖、双许可证、来源 manifest 和归属说明。"""
    from autoblade.adapters.cad.freecad.protocol import VENDOR_MANIFEST_SHA256

    try:
        data = read_file(prefix + "manifest.json")
        if hashlib.sha256(data).hexdigest() != VENDOR_MANIFEST_SHA256:
            raise ValidationError("Bundled dependency manifest fingerprint mismatch")
        manifest = json.loads(data)
        if not read_file(prefix + "NOTICE.md"):
            raise ValidationError("Bundled dependency notice is empty")
        for item in manifest["files"] + manifest["licenses"]:
            if hashlib.sha256(read_file(prefix + item["path"])).hexdigest() != item["sha256"]:
                raise ValidationError(f"Bundled dependency fingerprint mismatch: {item['path']}")
    except (KeyError, OSError) as error:
        raise ValidationError(f"Missing bundled dependency source or license: {error}") from error


def _validate_wheel_entry_points(archive: ZipFile, version: str) -> None:
    """从实际 wheel 校验三个稳定 console entry，防止只改 pyproject 未落入制品。"""
    path = f"autoblade-{version}.dist-info/entry_points.txt"
    try:
        content = archive.read(path).decode("utf-8")
    except KeyError as error:
        raise ValidationError(f"wheel entry point metadata is missing: {path}") from error
    parser = ConfigParser()
    parser.read_string(content)
    if not parser.has_section("console_scripts"):
        raise ValidationError("wheel has no console_scripts entry point section")
    actual = dict(parser.items("console_scripts"))
    if actual != EXPECTED_CONSOLE_SCRIPTS:
        raise ValidationError(
            f"wheel console scripts mismatch: {actual!r} != "
            f"{EXPECTED_CONSOLE_SCRIPTS!r}"
        )


def _validate_archive_names(names: list[str], *, artifact: str) -> None:
    for name in names:
        normalized = name.replace("\\", "/")
        parts = {part.lower() for part in normalized.split("/")}
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValidationError(f"{artifact} contains absolute path: {name}")
        forbidden = parts & FORBIDDEN_PARTS
        if forbidden:
            raise ValidationError(
                f"{artifact} contains forbidden path {name}: {sorted(forbidden)}"
            )
        if any(normalized.lower().endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            raise ValidationError(f"{artifact} contains forbidden file: {name}")


def _validate_no_local_path_leak(contents, *, artifact: str) -> None:
    local_markers = {
        str(PROJECT_ROOT).encode("utf-8"),
        str(PROJECT_ROOT).replace("\\", "/").encode("utf-8"),
    }
    for name, content in contents:
        if any(marker and marker in content for marker in local_markers):
            raise ValidationError(
                f"{artifact} member leaks the local repository path: {name}"
            )


def _write_content_manifest(
    dist_dir: Path,
    artifact_name: str,
    names: list[str],
) -> None:
    content = "\n".join(names) + "\n"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest = dist_dir / f"{artifact_name}.contents.txt"
    manifest.write_text(content, encoding="utf-8", newline="\n")
    print(
        f"Artifact contents: {artifact_name} ({len(names)} files, "
        f"manifest sha256={digest}) -> {manifest.name}"
    )


def _validate_git_tag(version: str, *, require_tag: bool) -> None:
    result = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValidationError(f"Unable to inspect Git tags: {result.stderr.strip()}")

    version_tags = {
        tag
        for tag in result.stdout.splitlines()
        if re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag)
    }
    expected_tags = {version, f"v{version}"}
    mismatched = version_tags - expected_tags
    if mismatched:
        raise ValidationError(
            f"HEAD version tags do not match {version}: {sorted(mismatched)}"
        )
    if require_tag and not version_tags:
        raise ValidationError(
            f"Release validation requires HEAD tag {version!r} or {f'v{version}'!r}"
        )


def validate(dist_dir: Path, *, require_tag: bool) -> None:
    version = _source_version()
    _validate_pyproject()
    _validate_readme_links()
    _validate_cli_version(version)
    _validate_git_tag(version, require_tag=require_tag)
    _validate_metadata(_read_wheel_metadata(dist_dir, version), version, "wheel")
    _validate_metadata(_read_sdist_metadata(dist_dir, version), version, "sdist")
    _validate_distribution_contents(dist_dir, version)
    print(
        f"Distribution metadata valid: {EXPECTED_PROJECT_NAME} {version} "
        f"(tag required: {require_tag})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="Directory containing one wheel and one sdist for the source version.",
    )
    parser.add_argument(
        "--require-tag",
        action="store_true",
        help="Require HEAD to carry a version tag matching the source version.",
    )
    args = parser.parse_args()
    try:
        validate(args.dist_dir.resolve(), require_tag=args.require_tag)
    except ValidationError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
