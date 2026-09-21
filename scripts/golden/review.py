"""把已有双后端候选打包为人工检查目录；只整理实测数据，不作阈值判断。

此工具不启动 CAD，不修改源模型或候选身份。先校验输入、模型和测量报告的
摘要关联，再创建新目录；Windows 复制后可用 SHA256SUMS.json 再次校验字节。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
import shutil

from .candidate_contract import PENDING, affine_residual, load_candidate
from .fixture import DIRECTIONS, fixture_path, sha256


POLICY = "measurements_only_user_judgment"
NOTES = """这些候选仅供人工检查，几何适用性由用户判断，尚未成为公开黄金基线。
每个案例含相同输入生成的 CATIA/CATPart、CATIA/STEP、FreeCAD/FCStd、FreeCAD/STEP。
建议先打开同一案例的两个 STEP 进行叠加；CATPart 和 FCStd 用于检查各自特征树。
dense-1000 仅记录 FreeCAD 性能，没有 CATIA 对照。

测量长度单位为 mm、体积为 mm³；输入 CSV 的长度单位为 m、角度为 deg。
cross_backend 比较 FreeCAD 原生实体与 CATIA STEP；exchange 比较原生实体与自身 STEP。
体积和质心使用 FreeCAD/OCCT 默认积分读数。钝尾缘案例的较大读数差与较小曲面采样差
同时存在，原因尚未独立验证；这些读数不能直接视为高精度积分结果或实际几何缺陷。
包围盒采用 Shape.BoundBox 默认算法，没有另做紧致极值求解。
全局曲面在 0.1 mm 网格顶点中每方向固定抽取最多 400 点，投影到对方裁剪曲面集合。
有限样本最大差不是连续曲面的 Hausdorff 上界，RMS 按点计权，未按面积计权。
每案在建模前固定 79 个 X 站位，每方向最多抽取 240 个截面点；完整性与重试偏移保留在 JSON。
汇总的截面最大差只汇集完整截面；原始站位、每个方向的 RMS 和最差点坐标见 measurements.json。
affine-* 是 single-sharp 的整体缩放、绕 X 轴旋转及平移；affine.json 记录各后端自身的变换残差。

本目录只导出实测字段，不使用早期试测中的拟议阈值或通过/失败结论。
原始测量报告保留在工作区；这里的 generation.json 保存其 SHA-256 与输入身份供追溯。
"""


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def measurement_view(report: dict) -> dict:
    """兼容早期候选报告，只导出测量字段，原始报告仍留存以供审计。"""
    if report["status"] != "measured_candidate":
        raise ValueError("Expected a completed candidate measurement.")
    return {
        "schema": "autoblade.golden.review-measurements/v1",
        "comparison_policy": POLICY,
        **{
            key: report[key]
            for key in (
                "freecad_version",
                "occt_version",
                "manifest_sha256",
                "baseline_sha256",
                "artifacts",
                "properties",
                "exchange",
                "cross_backend",
                "stations",
                "elapsed_seconds",
                "peak_rss_kib",
            )
        },
    }


def summary_row(name: str, report: dict) -> dict:
    """最大值只汇集完整截面；分母显式保留，避免掩盖测量覆盖缺口。"""
    cross = report["cross_backend"]
    complete = [row for row in report["stations"] if row["complete"]]
    result = {
        "case_id": name,
        "freecad_volume_mm3": report["properties"]["native"]["volume_mm3"],
        "catia_volume_mm3": report["properties"]["catia"]["volume_mm3"],
        "volume_difference_percent": cross["volume_relative"] * 100,
        "centroid_max_component_difference_mm": cross["centroid_max_mm"],
        "bbox_max_component_difference_mm": cross["bbox_max_mm"],
        "complete_stations": len(complete),
        "total_stations": len(report["stations"]),
    }
    for direction in DIRECTIONS:
        for metric in ("max_mm", "rms_mm"):
            result[f"surface_{direction}_{metric}"] = cross["surface"][direction][
                metric
            ]
        result[f"section_{direction}_max_mm"] = max(
            (row["section"][direction]["max_mm"] for row in complete), default=None
        )
    return result


def package_review(
    matrix: Path, models: Path, measurements: Path, output: Path
) -> dict:
    """生成供人工检查的完整目录，拒绝覆盖或导出身份不一致的 CAD 制品。"""
    built = json.loads((models / "summary.json").read_text(encoding="utf-8"))
    if built["schema"] != "autoblade.golden.candidate-build/v1":
        raise ValueError("Expected completed candidate builds.")
    # 1. 复制之前验证整个矩阵，不让部分旧模型混入同名新测量。
    planned = []
    for record in built["cases"]:
        name = record["case_id"]
        case = fixture_path(matrix, name)
        performance = record["role"] == "performance"
        data = load_candidate(case, require_catia=not performance)
        if data["case_id"] != name or data["role"] != record["role"]:
            raise ValueError("Candidate case identity mismatch.")
        manifest_digest = sha256((case / "candidate.json").read_bytes())
        if manifest_digest != record["input_manifest_sha256"]:
            raise ValueError("Candidate input identity changed.")
        model = fixture_path(models, name + "/model")
        if set(record["artifacts_sha256"]) != {"blade.FCStd", "blade.stp"}:
            raise ValueError("Incomplete FreeCAD artifact set.")
        for filename, digest in record["artifacts_sha256"].items():
            if sha256(fixture_path(model, filename).read_bytes()) != digest:
                raise ValueError("FreeCAD artifact fingerprint mismatch.")
        report, report_digest = None, None
        if not performance:
            source = fixture_path(measurements, name + "/result.json")
            report_digest = sha256(source.read_bytes())
            report = measurement_view(json.loads(source.read_text(encoding="utf-8")))
            if (
                report["manifest_sha256"] != manifest_digest
                or report["baseline_sha256"]
                != sha256((case / "catia/blade.stp").read_bytes())
                or report["artifacts"]
                != {
                    "native_sha256": record["artifacts_sha256"]["blade.FCStd"],
                    "step_sha256": record["artifacts_sha256"]["blade.stp"],
                    "request_sha256": record["request_sha256"],
                }
            ):
                raise ValueError("Measurement artifact identity mismatch.")
        planned.append((case, data, model, record, report, report_digest))
    if not any(item[4] for item in planned):
        raise ValueError("No completed cross-backend measurements to export.")

    # 2. 模型字节原样复制；测量视图只去掉自动判断，不修改数值或源报告。
    output.mkdir(parents=True, exist_ok=False)
    rows, reports, transforms, links = [], {}, {}, []
    for case, data, model, record, report, report_digest in planned:
        name = data["case_id"]
        destination = output / name
        shutil.copytree(case / "input", destination / "input")
        shutil.copyfile(case / "LICENSE.md", destination / "LICENSE.md")
        (destination / "FreeCAD").mkdir()
        for filename in record["artifacts_sha256"]:
            shutil.copyfile(model / filename, destination / "FreeCAD" / filename)
        if report:
            (destination / "CATIA").mkdir()
            for filename in ("blade.CATPart", "blade.stp", "record.json"):
                shutil.copyfile(
                    case / "catia" / filename, destination / "CATIA" / filename
                )
            write_json(destination / "measurements.json", report)
            rows.append(summary_row(name, report))
            reports[name] = report
            links.append(
                f"<li><b>{html.escape(name)}</b> — "
                f'<a href="{name}/CATIA/blade.CATPart">CATPart</a> · '
                f'<a href="{name}/CATIA/blade.stp">CATIA STEP</a> · '
                f'<a href="{name}/FreeCAD/blade.FCStd">FCStd</a> · '
                f'<a href="{name}/FreeCAD/blade.stp">FreeCAD STEP</a> · '
                f'<a href="{name}/measurements.json">完整测量</a></li>'
            )
        else:
            links.append(
                f"<li><b>{html.escape(name)}</b> — FreeCAD 性能案例（无 CATIA 对照） · "
                f'<a href="{name}/FreeCAD/blade.FCStd">FCStd</a> · '
                f'<a href="{name}/FreeCAD/blade.stp">STEP</a></li>'
            )
        if data["origin"]["transform"]:
            transforms[name] = data["origin"]["transform"]
        write_json(
            destination / "generation.json",
            {
                "case_id": name,
                "approval_status": PENDING,
                "origin": data["origin"],
                "input": data["input"],
                "input_sha256": data["files"],
                "environment": data["environment"],
                "sampling": data["sampling"],
                "step_writer": data["step_writer"],
                "input_manifest_sha256": record["input_manifest_sha256"],
                "source_report_sha256": report_digest,
                "request_sha256": record["request_sha256"],
                "freecad_build_seconds": record["build_seconds"],
                "freecad_peak_rss_kib": record["peak_rss_kib"],
                "freecad_properties": record["properties"],
            },
        )
    affine = {
        name: {
            kind: affine_residual(
                reports["single-sharp"]["properties"][kind],
                reports[name]["properties"][kind],
                transform,
            )
            for kind in ("native", "catia")
        }
        for name, transform in transforms.items()
    }
    write_json(output / "affine.json", affine)
    summary = {"comparison_policy": POLICY, "cases": rows}
    write_json(output / "summary.json", summary)
    with (output / "measurements.csv").open(
        "x", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "README.txt").write_text(NOTES, encoding="utf-8-sig")
    headings = [
        "案例",
        "体积读数差 %",
        "质心分量差 mm",
        "包围盒分量差 mm",
        "曲面双向最大 mm",
        "截面双向最大 mm",
        "完整站位",
    ]
    table = []
    for row in rows:
        section_max = (
            f"{max(row[f'section_{direction}_max_mm'] for direction in DIRECTIONS):.9g}"
            if row["complete_stations"]
            else "无完整截面"
        )
        values = [
            row["case_id"],
            *(
                f"{row[key]:.9g}"
                for key in (
                    "volume_difference_percent",
                    "centroid_max_component_difference_mm",
                    "bbox_max_component_difference_mm",
                )
            ),
            f"{max(row[f'surface_{direction}_max_mm'] for direction in DIRECTIONS):.9g}",
            section_max,
            f"{row['complete_stations']}/{row['total_stations']}",
        ]
        table.append(
            "<tr>"
            + "".join(f"<td>{html.escape(value)}</td>" for value in values)
            + "</tr>"
        )
    page = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        "<title>AutoBlade 双后端模型测量</title><style>"
        "body{font:16px/1.65 system-ui;margin:40px;max-width:1400px;color:#172330}"
        "table{border-collapse:collapse;font-size:14px}td,th{border:1px solid #cbd3dd;padding:8px;text-align:left}"
        "th{background:#eef2f6}pre{white-space:pre-wrap}li{margin:8px 0}a{color:#1357a6}"
        "</style><h1>AutoBlade 双后端模型测量</h1>"
        f"<p>{len(rows)} 组 CATIA / FreeCAD 对照及 {len(planned) - len(rows)} 组 FreeCAD 性能案例。以下为实测值，判断由你作出。</p>"
        '<p><a href="measurements.csv">完整汇总 CSV</a> · <a href="summary.json">汇总 JSON</a> · '
        '<a href="affine.json">各后端变换残差</a></p><table><tr>'
        + "".join(f"<th>{value}</th>" for value in headings)
        + "</tr>"
        + "".join(table)
        + "</table><h2>模型文件</h2><ul>"
        + "".join(links)
        + "</ul><h2>测量说明</h2><pre>"
        + html.escape(NOTES)
        + "</pre></html>"
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    write_json(
        output / "SHA256SUMS.json",
        {
            path.relative_to(output).as_posix(): sha256(path.read_bytes())
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("matrix", "models", "measurements", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    package_review(
        args.matrix.resolve(strict=True),
        args.models.resolve(strict=True),
        args.measurements.resolve(strict=True),
        args.output.resolve(),
    )


if __name__ == "__main__":
    main()
