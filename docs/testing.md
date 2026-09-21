# 自动化测试

项目的 `pytest` 基线不依赖已安装或正在运行的 CATIA。核心导入、CSV、Planner 和坐标测试不需要 `pywin32`；Windows 与 Linux 都运行纯 Python/fake COM 矩阵，所有 COM 应用创建均被隔离。

## 运行命令

常规开发和发布前检查统一使用一个入口：

```powershell
pwsh -File scripts/check.ps1
```

该脚本按顺序执行冻结锁文件同步、pytest、Ruff、Hatchling wheel/sdist 构建、
全新 Python 3.14 环境的非 editable wheel 安装冒烟，以及实际产物元数据和内容
清单校验。安装冒烟会验证三个入口的 help/version、示例和完整翼型目录的
`autoblade init`、配置读取、输入发现、目录摘要、完整 Parser/Planner 预检和
注入 fake Builder 的执行路径；它明确清空
`PYTHONPATH` 并确认导入文件位于新环境的 `site-packages`。

`.github/workflows/checks.yml` 在 Windows CI 中调用该脚本；Linux CI 调用
`bash scripts/check-linux.sh`，执行同一组 pytest、Ruff、构建、非 editable wheel
安装冒烟和分发校验，并确认 `pywin32`/旧 namespace 均未进入 Linux 环境。
诊断时可使用 `-SkipSync` 或 `-SkipInstalledSmoke` 缩小范围，但里程碑和发布验收
不得跳过安装冒烟。正式版本标签构建还应使用：

```powershell
pwsh -File scripts/check.ps1 -RequireTag
```

`-RequireTag` 要求当前提交存在与 `src/autoblade/__init__.py` 相同的 `0.2.0` 或 `v0.2.0` 标签。普通开发检查允许尚未打标签，但发现不一致的版本标签仍会失败。

排查单个阶段时可分别使用 `uv run --extra dev pytest -q`、`uv run --extra dev
ruff check src tests scripts`、`uv build`、`pwsh -File
scripts/smoke_installed_wheel.ps1 -WheelPath <wheel>` 和 `uv run python
scripts/validate_distribution.py`。这些命令是诊断入口，完整验收仍以
平台对应的 `scripts/check.ps1` 或 `scripts/check-linux.sh` 为准。

## 分层回归策略

| 层级 | 自动化范围 | 能发现的问题 | 不能替代的检查 |
| --- | --- | --- | --- |
| 单元层 | m/mm 单位、旋转、缩放、平移、零位移和输出命名 | 数学顺序、符号、单位边界和纯函数回归 | CATIA 特征是否可更新 |
| Parser / Planner 层 | CSV schema、跨文件引用闭合、`BladeBuildJob` 列表、显式扫描清单和输出冲突 | 缺文件、非法字段、任务数量、隐式组合、排序和 COM 前失败 | Loft 的真实几何质量 |
| mock CATIA 层 | 唯一基准几何复用、调用顺序、异常清理和批任务隔离 | COM 编排、重复创建、资源泄漏路径 | CATIA 内核的样条、Loft、`CloseSurface` 结果 |
| 真实 CATIA 层 | 版本化代表输入的人工冒烟与回归 | 几何内核、特征树、实体封闭、格式导出和真实进程残留 | 不进入默认 `pytest`，不能作为低成本提交前检查 |

pytest 专用预期失败数据不得放入 `input/` 扫描目录。小型测试使用 `tmp_path`
构造；公开 CAD 黄金夹具维护在 `tests/fixtures/golden/`，默认 pytest 只校验
身份与报告完整性，真实 FreeCAD 测量必须显式运行。首个案例的历史命令、数值契约与
阶段 4 边界见[公开黄金验证记录](validation/golden-fixture-2026-09-20.md)。版本化
输入的分类和推荐命令见 [`input/README.md`](../input/README.md)。

新 CATIA 候选使用 `scripts.golden.candidates` 显式生成和测量，并通过
`scripts.golden.review` 整理双后端模型、实测 JSON/CSV 和检查入口。按用户要求，
候选和公开夹具都只记录误差，不给出模型可用性裁决；2026-09-21 用户的新规则
取代历史数值自动裁决。格式、覆盖要求与 CI 见[标准几何误差报告](geometry-measurement-reports.md)。
候选尚未获公开基线批准时留在 `output/`，不能通过本轮测量自动进入公开夹具。
命令与真实结果见[候选矩阵测量记录](validation/golden-matrix-2026-09-21.md)。

## 覆盖范围

| 测试模块 | 主要契约 |
| --- | --- |
| `test_input_validation.py` | 翼型和截面 CSV 解析、schema、数值、点序、行号与字段错误定位 |
| `test_input_plan.py` | 单/多翼型模式、受限路径解析、唯一读取、后缘拓扑和 COM 前失败 |
| `test_job_planner.py` | `BladeBuildJob` 输入闭合、稳定排序、无笛卡尔积、输出冲突和共享 Executor |
| `test_sweep.py` | 显式 Cartesian product、十任务稳定顺序、自包含文件隔离、JSON 清单、dry-run 和输出冲突 |
| `test_repository_inputs.py` | 版本化输入命名、89 行多翼型样例、引用完整性与唯一翼型顺序 |
| `test_airfoil_library.py` | 内置目录来源授权、清单完整性、点数、SHA-256 和仓库参考输入一致性 |
| `test_geometry_math.py` | m/mm 边界、截面缩放以及旋转→缩放→平移顺序 |
| `test_multi_airfoil_geometry.py` | 唯一 CATIA 基准几何创建和逐截面引用编排 |
| `test_platform_boundary.py` | 核心无 COM 导入、全新解释器导入和不可用 CATIA 后端能力错误 |
| `test_runtime_config.py` | 配置路径、文件扫描、CLI 输出覆盖和输出命名 |
| `test_config_compatibility.py` | 配置发现优先级、新旧用户目录、历史 schema、迁移备份/回滚边界、未来/未知/废弃字段和并发修改防护 |
| `test_workspace_init.py` | 外部工作区、示例/目录资源边界、覆盖授权、只读目录和 site-packages 隔离 |
| `test_doctor.py` | 诊断摘要、COM 初始化配对、配置目录与失败退出边界 |
| `test_distribution_workflow.py` | Hatchling 白名单、禁止产物路径和真实 CATIA 发布证据门槛 |
| `test_distribution_identity.py` | 规范 namespace、旧 distribution 共存失败和可执行卸载提示 |
| `test_golden_fixture.py` | 公开黄金摘要、元数据清理、许可入口、实测数值合法性、站位覆盖和源码归档例外 |
| `test_golden_candidates.py` | 原创合成翼型、精确尖钝拓扑、候选输入身份、建模前冲突检查和仿射残差 |
| `test_golden_review.py` | 检查包的输入/模型/测量关联、原字节保真及只导出实测字段 |
| `test_cli.py` | 主命令、独立入口、长短选项与参数分派 |
| `test_catia_lifecycle.py` | COM 初始化、文档关闭、应用退出、异常清理和批处理隔离 |

`tests/conftest.py` 在已安装 `pywin32` 时禁止调用真实 `win32com.client.Dispatch` 和 `DispatchEx`。如果未来新增代码绕过 mock 并尝试启动 CATIA，测试会立即失败，而不是在开发机上留下隐藏进程。静态与全新解释器测试同时阻止核心层重新引入 COM 导入。

预览支持组合及验证日期维护在[分发范围与支持策略](distribution-scope.md)的兼容性表中。仅有 pytest 通过不能扩大 CATIA 支持矩阵。

## 自动化与真实 CATIA 的边界

自动化测试验证 Python 领域逻辑、参数契约和 COM 生命周期编排，但不会验证 CATIA 的样条拟合、Loft 或 `CloseSurface` 几何结果。涉及真实几何内核的回归仍需使用代表性输入执行 CLI，并检查：

- `.CATPart` 和 `.stp` 均成功生成；
- CATIA 特征树和实体几何符合预期；
- 命令结束后没有新增的 `CNEXT` 进程残留。

真实 CATIA 冒烟测试不属于默认 `pytest` 套件，以免自动化检查依赖许可证、桌面会话或特定 CATIA 版本。每次人工回归至少记录：

```text
date:
command:
Windows / Python / pywin32:
CATIA version and configuration:
input model:
CATPart result:
STEP result and topology:
feature-tree / geometry observations:
new CNEXT processes after exit:
```

候选 wheel 的标准入口为：

```powershell
pwsh -File scripts/smoke_real_catia.ps1
```

该脚本只在维护者显式调用时运行。它从候选 wheel 创建独立环境，复制版本化的
89 截面输入到外部临时工作区，执行真实建模，再通过第二个 `DispatchEx` 独占
实例打开 CATPart，检查 `blade_loft_surface`、`blade_closed_solid`、
`leading_edge_guide` 和 `trailing_edge_upper_guide`；同时检查 STEP 中的固体
BREP 实体和运行前后新增 `CNEXT` PID。产物与
JSON 记录保存在忽略的 `output/real-catia-smoke-<时间>/`，不能提交 Git。

2026-08-07 已使用 CATIA P3 V5-6R2020 对 `blade_sections-multi-airfoil.csv` 执行真实回归：三个不同点数翼型完成 89 截面 Loft 和实体封闭，CATPart 与 STEP AP242 均成功输出；STEP 包含闭合实体 BREP，命令结束后没有残留 `CNEXT` 进程。详细记录见[展向多翼型设计](multi-airfoil-design.md)。

2026-08-11 使用从 dirty worktree 构建并安装到全新 CPython 3.14.4 环境的
`0.2.0` 候选 wheel 重复同一 89 截面回归：CATPart 为 7,689,114 字节，STEP 为 1,022,363
字节并包含固体 BREP；重新打开 CATPart 后确认 `blade_loft_surface`、
`blade_closed_solid`、`leading_edge_guide` 和 `trailing_edge_upper_guide`，运行前后
新增 `CNEXT` 为 0。该记录证明候选 wheel 路径可行，但不替代最终干净标签提交的
重新验证；本地产物位于忽略的 `output/real-catia-smoke-20260811-165054/`。
