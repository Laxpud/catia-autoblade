"""将标准几何误差数据写为人工可读的 Markdown/CSV，不生成可用性裁决。

JSON 保存原始坐标、逐站位覆盖和完整测量方法；本模块生成便于人工扫读的
数值表，不能用表格中的有限采样最大值冒充连续几何误差上界。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .fixture import DIRECTIONS


def write_error_report(report: dict, output: Path) -> None:
    """把测量结果导出为两份配套报告，状态只代表测量完成程度。"""
    rows = []

    def add(layer, metric, unit, value, *, direction="", station=""):
        rows.append(
            dict(
                layer=layer,
                metric=metric,
                unit=unit,
                direction=direction,
                station_x_mm=station,
                value=value,
            )
        )

    for name, props in report["properties"].items():
        add(name, "volume", "mm^3", props["volume_mm3"])
        for index, axis in enumerate("xyz"):
            add(name, "centroid_" + axis, "mm", props["center_of_mass_mm"][index])
        for name_part, value in zip(
            ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"),
            props["bounding_box_mm"],
            strict=True,
        ):
            add(name, "bbox_" + name_part, "mm", value)
    for layer in ("exchange", "cross_backend"):
        data = report[layer]
        for metric, unit in (
            ("volume_relative", "ratio"),
            ("centroid_max_mm", "mm"),
            ("bbox_max_mm", "mm"),
        ):
            add(layer, metric, unit, data[metric])
        for direction in DIRECTIONS:
            for metric in ("max_mm", "rms_mm"):
                add(
                    layer,
                    "surface_" + metric,
                    "mm",
                    data["surface"][direction][metric],
                    direction=direction,
                )
    for station in report["stations"]:
        layer = "section" if station["complete"] else "surface_diagnostic"
        for direction in DIRECTIONS:
            for metric in ("max_mm", "rms_mm"):
                add(
                    layer,
                    metric,
                    "mm",
                    station[layer][direction][metric],
                    direction=direction,
                    station=station["requested_x_mm"],
                )
    with (output / "error-report.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    coverage = report["coverage"]
    data = report["cross_backend"]
    text = [
        "# 标准几何误差报告",
        "",
        f"案例：`{report['case_id']}`。测量状态：`{report['status']}`。模型可用性：**由人类判断**。",
        "",
        f"FreeCAD {report['freecad_version']} / OCCT {report['occt_version']}；长度 mm，体积 mm³，相对体积差为比值。",
        "",
        "| 指标 | 实测值 |",
        "| --- | ---: |",
        f"| 相对体积读数差 | {data['volume_relative']:.12g} |",
        f"| 质心最大坐标分量差 mm | {data['centroid_max_mm']:.12g} |",
        f"| 包围盒最大坐标分量差 mm | {data['bbox_max_mm']:.12g} |",
    ]
    for direction in DIRECTIONS:
        distances = data["surface"][direction]
        text.append(
            f"| 曲面 {direction} max / RMS mm | {distances['max_mm']:.12g} / {distances['rms_mm']:.12g} |"
        )
    text += [
        f"| 完整截面 / 已记录 / 预定站位 | {coverage['complete_stations']} / {coverage['recorded_stations']} / {coverage['planned_stations']} |",
        "",
        "体积和质心为 OCCT 默认积分读数，未作独立积分收敛确认；包围盒使用默认算法。",
        "曲面与截面 max 均为有限采样值，不是连续 Hausdorff 上界；RMS 按点计权。",
        "不完整截面保留独立曲面诊断，不混入完整截面的统计。",
        "",
        f"不完整截面站位 mm：`{coverage['incomplete_stations_mm']}`。",
        "",
        f"参照 STEP SHA-256：`{report['baseline_sha256']}`。",
        f"原生模型 SHA-256：`{report['artifacts']['native_sha256']}`。",
        f"本次 STEP SHA-256：`{report['artifacts']['step_sha256']}`。",
        "",
        "完整采样方法、最差点坐标、逐站位重试和输入身份见 `result.json`；全量数值表见 `error-report.csv`。",
        "人工检查结论应另行记录日期、用途和本次制品摘要，不自动继承旧模型的批准。",
        "",
    ]
    (output / "error-report.md").write_text("\n".join(text), encoding="utf-8")
