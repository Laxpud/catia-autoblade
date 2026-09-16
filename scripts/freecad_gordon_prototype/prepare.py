"""为阶段 2 原型生成一个闭合、版本化请求。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoblade.core.input_plan import build_blade_input_plan

from .request import apply_global_transform, build_request


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a closed SI-unit request for the FreeCAD Gordon prototype."
    )
    parser.add_argument("--airfoil-dir", required=True, type=Path)
    parser.add_argument("--sections", required=True, type=Path)
    parser.add_argument("--airfoil")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--global-scale", type=float, default=1.0)
    parser.add_argument("--global-rotation-x-deg", type=float, default=0.0)
    parser.add_argument("--global-translate-x-m", type=float, default=0.0)
    parser.add_argument("--global-translate-y-m", type=float, default=0.0)
    parser.add_argument("--global-translate-z-m", type=float, default=0.0)
    args = parser.parse_args()

    plan = build_blade_input_plan(
        args.sections,
        args.airfoil_dir,
        args.airfoil,
    )
    request = build_request(plan)
    transform = (
        args.global_scale,
        args.global_rotation_x_deg,
        args.global_translate_x_m,
        args.global_translate_y_m,
        args.global_translate_z_m,
    )
    if transform != (1.0, 0.0, 0.0, 0.0, 0.0):
        request = apply_global_transform(
            request,
            scale=args.global_scale,
            rotation_x_deg=args.global_rotation_x_deg,
            translate_x_m=args.global_translate_x_m,
            translate_y_m=args.global_translate_y_m,
            translate_z_m=args.global_translate_z_m,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Prepared {args.output.resolve()}")


if __name__ == "__main__":
    main()
