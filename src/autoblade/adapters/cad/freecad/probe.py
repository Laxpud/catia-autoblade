"""FreeCAD doctor 的最小 headless 探针；不构造叶片，不触碰用户文档。"""

import json
import os
from pathlib import Path
import sys
import traceback

from protocol import validate_curveswb_checkout
import FreeCAD as App
import Part


def run() -> None:
    """验证固定依赖、NumPy 和目标文件系统中的 FCStd 创建/重开能力。"""
    output = Path(os.environ["AUTOBLADE_FREECAD_OUTPUT_DIR"])
    result = {"schema_version": "autoblade.freecad/probe/v1", "status": "failed"}
    try:
        root = Path(os.environ["AUTOBLADE_FREECAD_CURVESWB_DIR"])
        validate_curveswb_checkout(root)
        sys.path.insert(0, str(root))
        import freecad

        freecad.__path__ = [str(root / "freecad")]
        from freecad.Curves.gordon import GordonSurfaceBuilder
        import numpy

        assert GordonSurfaceBuilder is not None
        path = output / "probe.FCStd"
        document = App.newDocument("AutoBladeDoctor")
        document.addObject("Part::Feature", "Probe").Shape = Part.makeBox(1, 1, 1)
        document.recompute()
        document.saveAs(str(path))
        App.closeDocument(document.Name)
        reopened = App.openDocument(str(path))
        shape = reopened.getObject("Probe").Shape
        if not shape.isValid() or not shape.isClosed() or len(shape.Solids) != 1:
            raise ValueError("Doctor FCStd reopen failed.")
        App.closeDocument(reopened.Name)
        result.update(
            status="passed",
            freecad_version=list(App.Version()),
            numpy_version=numpy.__version__,
        )
    except Exception:
        result["error"] = traceback.format_exc()
    (output / "result.json").write_text(json.dumps(result), encoding="utf-8")


run()
