# CATIA 候选对照生成：2026-09-07 至 2026-09-08

用户于 2026-09-07 明确授权使用 win11 虚拟机创建 CATIA 模型。现已生成
89 截面、300/253/249 点三翼型的 CATPart 与 AP242 STEP，重开 CATPart 特征树
检查通过，运行前后 CNEXT 均为空。产物是待工程审查的候选对照，不自动成为
已批准黄金基线；未提交 CAD 文件或批准几何公差。

## 生成与检查

- 输入：`input/blade_sections/blade_sections-multi-airfoil.csv` 和
  `airfoil1_sharp.csv`、`airfoil2_sharp.csv`、`airfoil3_sharp.csv`。
  四个文件 SHA-256 与[示例数据审计](../example-data-audit.md)一致。
- 源码：`f63f0cf105ce7987a870225b4a50c24887764478`，dirty worktree；产品版本
  `0.2.0`。本轮没有修改产品源码，未作为干净标签发布候选验收。
- 环境：Windows 11 build 26200，Python 3.14.7，pywin32 311，CATIA
  P3 V5-6R2020，实际 CNEXT 文件版本 `5.30.0.19235`。
- 先将工作区复制到 Windows 本地
  `%LOCALAPPDATA%\AutoBlade-checks\catia-baseline-20260907-160936`。
  通过锁定依赖同步、151 项 pytest、Ruff、构建、非 editable wheel smoke 与
  distribution 校验。Linux 完整 `bash scripts/check-linux.sh` 同样通过。
- 建模从新建环境中安装的 `autoblade-0.2.0-py3-none-any.whl` 执行，不直接导入
  工作区源码；使用相同公开输入和命令 `create --section
  blade_sections-multi-airfoil.csv`，输出到本次独占目录。
- 最终成功任务运行在已登录用户的 Session 1；建模和检查均通过 `DispatchEx`
  创建独占隐藏 CATIA，未连接、复用或关闭用户已有实例。
- CATPart 重开检查包含 `blade_loft_surface`、`blade_closed_solid`、
  `leading_edge_guide`、`trailing_edge_upper_guide`。STEP 存在固体 BREP，实际
  schema 为 `AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF`。
- 2026-09-07 16:22:59 +08:00 任务完成；记录显示 CNEXT before/after 均为 `[]`。

## 保存停顿诊断

直接从 SSH 的 Session 0 执行时，几何建模已完成，但 `SaveAs` 长时间不返回。
只读进程检查显示 CATIA CPU 累计时间几乎不再增长。停止本次拥有的 PID 后，
缓冲日志确认停顿位于保存阶段，而非 Loft 创建。

最小探针只执行 `DispatchEx`、创建空 Part 和保存到同一 Windows 本地目录。
Session 0 下 20 秒栈转储停在 COM `SaveAs`，30 秒超时；切换到已登录用户的
交互 Session 1 后，同一探针保存成功。完整叶片任务随后也成功。这支持本次
保存行为依赖运行会话的判断，但未定位 CATIA 内部原因，不泛化为所有版本均
不支持 Session 0。诊断探针不进入默认 pytest，也没有修改 DCOM 或 CATIA 全局设置。

交互运行通过一次性 Windows 计划任务启动，任务已于 2026-09-08 删除。清理前
核对本地副本与共享归档的 CATPart、STEP、validation JSON 和 wheel SHA-256
一致，随后删除本次 Windows 工作副本及虚拟环境；失败尝试日志保留用于审查。

## 本机证据与摘要

证据根目录：`output/catia-baseline-20260907/`（忽略目录）。成功产物位于
`20260907-160936/real-catia-smoke-interactive-20260907-162158/`，保留
`validation.json`。同一记录目录保存失败和成功日志、wheel/sdist、内容清单及
`cleanup.json`；根目录保存 `environment.json`、`provenance.json`、Linux
检查日志、保存探针及对照脚本。此记录不宣称干净 checkout 已能复现黄金回归。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| CATPart | 7682703 | `a2496f447de5fbe0c9c6cb494f84d2aff46e617baf60abd1688a236fd1a22091` |
| STEP | 1022414 | `d9ef236cb71e2765c69badec9cc7506b4744bb5d133208dc5cc66a9988824db9` |
| wheel | 75345 | `a87434390d7f01e7de40ad28608b02124a526a5a9d87a42db9e23f645f2e02f7` |

输入来源授权见原审计记录；生成授权不自动替代衍生 STEP 公开再分发审查、黄金
基线批准或 precision/工程公差批准。原始 STEP 头包含生成路径，公开夹具入库前
还应审查元数据并重新记录最终摘要。

## 2026-09-08 探索性几何对照

使用 Flatpak FreeCAD 1.1.3 的同一内核读取两份 STEP，并对原生 FCStd 强制重算。
三份 Shape 均有效且为单 solid。对照脚本 `compare.py` 与完整结果
`comparison.json` 保存在本机证据根目录；本轮计算耗时约 191.2 秒。

曲面采样方法：以 `tessellate(0.1)` 得到曲面网格顶点，确定性抽取每方向最多
400 点，计算到对方裁剪曲面集合的最短距离。没有使用离开曲面的三角形重心。
这是有限采样结果，不是连续曲面的 Hausdorff 上界；RMS 按采样点计权，不是
面积加权。截面在模型 X 方向的 9 个代表输入站位切割，各截面边取 40 点。

| 比较项目 | 实测结果 |
| --- | --- |
| FreeCAD STEP 体积 | 1308440.484394318 mm³ |
| CATIA STEP 体积 | 1308523.889727185 mm³ |
| FreeCAD − CATIA 默认体积差 | −83.405332867 mm³，约 −0.006374% |
| 两 STEP 质心距离 | 0.013743956 mm |
| 包围盒坐标分量最大差 | 0.030310050 mm |
| FreeCAD → CATIA 曲面采样最大 / RMS | 0.511785388 / 0.047906432 mm |
| CATIA → FreeCAD 曲面采样最大 / RMS | 0.329635634 / 0.024722772 mm |

FreeCAD 原生模型与自身 STEP 的双向曲面采样最大差为 `6.394e-11 mm`，
9 站位截面双向采样最大差约 `7.21e-11 mm`，但默认体积读数仍差
`162.837118124 mm³`。这些结果支持“默认体积积分存在数值差异”的假设，
尚不能证明整个连续曲面完全一致，也不能把原生体积读数直接作为高精度裁判。
FreeCAD 1.1.3 的 [Volume 实现](https://github.com/FreeCAD/FreeCAD/blob/1.1.3/src/Mod/Part/App/TopoShapePyImp.cpp)
调用 `BRepGProp::VolumeProperties(shape, props)`，未在该属性入口指定积分精度。
后续应补独立积分收敛测量，再提出可靠体积/质心公差。

原始截面比较在 `x=236.22000000000003 mm` 得到异常的单向约 32 mm 差异；
该处 FreeCAD 布尔切面仅返回一条边，故不能把此数值当成完整闭合截面的偏差。
其余 8 个站位双向采样最大差不超过 `0.002722 mm`。必须先验证截面提取的
完整性，不能只检查“有返回边”就将测量用于黄金 gate。

当前结论：CATIA 候选模型已取得，实际跨后端表面差异需要定位，测量器本身也
仍需完善。未批准 STEP precision 或任何工程公差，未形成阶段 2 GO。

单站位后续探针 `check-section.py` / `section-diagnostic.json` 确认：该站位的
原生 Sketch 有两条边且闭合，直接与 CATIA 截面双向比较的最大偏差约
`0.000738615 mm`。FreeCAD 布尔切面长度仅 `164.675082 mm`，CATIA 为
`321.939371 mm`；在明确标记的 `±0.0001 mm` 邻近平面探针中仍漏边。
因此该 32 mm 异常是当前截面测量方法不完整的信号，不能作为几何失败结论。
邻近平面结果只用于诊断，没有替换原始输入站位或静默放宽公差。

后续[偏差诊断](freecad-deviation-analysis-2026-09-08.md)通过逐面投影和独立曲线
取点确认真实差异，叶根观察值提高至 0.571 mm；本报告 0.512 mm 是原有限
采样结果，不是全曲面最大值。
