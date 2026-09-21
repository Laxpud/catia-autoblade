"""用独占 CATIA 实例检查候选 CATPart 的关键特征树，不接触用户会话。"""

from __future__ import annotations

import argparse
import gc
from pathlib import Path


REQUIRED_FEATURES = (
    "blade_loft_surface",
    "blade_closed_solid",
    "leading_edge_guide",
    "trailing_edge_upper_guide",
)


def inspect_artifact(
    path: Path, *, required_features: tuple[str, ...] = REQUIRED_FEATURES
) -> None:
    """重开 CATPart 并检查调用者声明的特征，默认兼容既有尖尾缘 smoke。"""
    import pythoncom
    import win32com.client

    application = None
    document = None
    pythoncom.CoInitialize()
    try:
        # DispatchEx 保证检查器拥有独占实例；finally 只退出该实例，不连接或
        # 退出用户已经打开的 CATIA。任何检查失败仍执行同一清理路径。
        application = win32com.client.DispatchEx("CATIA.Application")
        application.Visible = False
        document = application.Documents.Open(str(path))
        part = document.Part
        if part.Bodies.Count < 1:
            raise RuntimeError("CATPart contains no PartBody.")

        selection = document.Selection
        missing = []
        for name in required_features:
            selection.Clear()
            selection.Search(f"Name={name},all")
            if selection.Count2 < 1:
                missing.append(name)
        selection.Clear()
        if missing:
            raise RuntimeError(f"CATPart feature tree is missing: {missing}")
        print(
            "CATPart feature tree: PASS - "
            + ", ".join(required_features)
        )
    finally:
        if document is not None:
            try:
                document.Close()
            except Exception:
                pass
        document = None
        if application is not None:
            try:
                application.Quit()
            except Exception:
                pass
        application = None
        gc.collect()
        pythoncom.CoUninitialize()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catpart", type=Path)
    args = parser.parse_args()
    path = args.catpart.expanduser().resolve()
    if not path.is_file():
        parser.error(f"CATPart not found: {path}")
    inspect_artifact(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
