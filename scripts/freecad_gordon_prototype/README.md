# FreeCAD Gordon 阶段 2 原型

本目录保存 `0.3.0` 阶段 2 的可丢弃验证工具，不是已集成的 FreeCAD backend。
它证明固定 Runner 能从 Host 已闭合的 SI 单位 JSON 构造 Gordon 几何，并验证
FCStd/STEP 与声明的重建方式；不会改变 CLI、配置 schema 或当前默认 CATIA 行为。

## 数据与进程边界

1. `prepare.py` 复用当前 Parser，在 Host 进程完成 CSV 解析、引用闭合和领域校验，
   输出严格的 `autoblade.freecad-gordon-prototype/request/v2` JSON。
2. `launch.py` 验证请求和固定 CurvesWB 源码摘要，以参数数组启动一个独立
   Flatpak `FreeCADCmd`，并只监督本轮进程组。
3. `runner.py` 只读取闭合 JSON 或 FCStd 内嵌 JSON，不导入 AutoBlade、不扫描
   CSV，也不依赖 `if __name__ == "__main__"`。
4. 输出是静态 `Part::Feature` solid；FCStd 同时保存输入曲线网络和 `Traceability`
   属性。它不宣称原生参数化，重建必须由同一固定 Runner 与依赖重新执行。

Runner 在 FreeCAD 边界把 m 换算为 mm。每个翼型保持 TE→LE→TE 点序：尖尾缘
拆为 upper/lower，钝尾缘用一张 TE-upper→LE→TE-lower full-wrap 曲面并增加显式
ruled closure。profile 按各分区累计弧长参数化；所有 spanwise guide 共享由 LE 和
两条 TE 相邻站位平均距离得到的参数。Runner 直接调用 Gordon builder，不允许其
自动求交、排序或近似重参数化。LE/TE B-spline 是真实网络约束，截面/导引保持
必须小于 `network bbox diagonal × 1e-5`，且每张曲面内部由 degree/knot
multiplicity 证明至少 C2；曲面接缝和封盖只要求 C0 与最终 watertight single solid。

## 固定依赖与许可证边界

原型固定 CurvesWB `0.6.81` commit
`e4972f761d126901d13b3a72be64eb14f7d51c92`，并逐文件验证实际导入的最小源码闭包：

- `gordon.py`、`BSplineAlgorithms.py`、`BSplineApproxInterp.py` 和
  `curve_network_sorter.py` 标记为 `Apache-2.0`；
- `nurbs_tools.py`、`freecad/Curves/__init__.py` 和 `version.py` 标记为
  `LGPL-2.1-or-later`。

因此不能把整个依赖简称为 Apache-2.0。当前仓库没有 vendoring 这些文件，原型
显式接收一个已固定且摘要匹配的本地 checkout。进入阶段 3 前仍须确定内部 wheel
如何随附该源码闭包、许可证文本和归属说明；当前原型成功不等于分发门禁通过。

## 复现

以下命令从公开的 89 截面多翼型案例生成请求并运行一次：

```bash
uv run python -m scripts.freecad_gordon_prototype.prepare \
  --airfoil-dir input/airfoils \
  --sections input/blade_sections/blade_sections-multi-airfoil.csv \
  --output output/gordon-clean/request.json

uv run python -m scripts.freecad_gordon_prototype.launch \
  --request output/gordon-clean/request.json \
  --output-dir output/gordon-clean/initial \
  --curveswb /absolute/path/to/pinned/CurvesWB \
  --timeout-seconds 900
```

按 FCStd 内嵌请求验证声明的重建方式：

```bash
uv run python -m scripts.freecad_gordon_prototype.launch \
  --rebuild-from output/gordon-clean/initial/blade.FCStd \
  --output-dir output/gordon-clean/rebuild \
  --curveswb /absolute/path/to/pinned/CurvesWB \
  --timeout-seconds 900
```

阶段 2 还提供两个只读证据探针。`step_precision_probe.py` 对同一 FCStd 比较 OCCT
STEP writer precision 模式；`compare_catia.py` 对一套已授权生成的 CATIA STEP
报告实体属性、双向有限曲面样本和翼型切换区固定截面距离。二者都由
`FreeCADCmd` 直接执行，输入和输出目录分别通过脚本顶部声明的环境变量传入；
其有限采样结果不是连续 Hausdorff 上界，也不自动成为工程或制造公差。

输出目录必须位于 Flatpak 可见的文件系统。工具拒绝覆盖默认制品；生产 backend
仍需实现完整的暂存、事务发布、timeout/中断映射和失败快照，不能直接复用本原型
作为已完成的 Adapter。
