# AutoBlade 0.3.0 目标架构

> **状态：已接受的目标设计，尚未实现。** 本文不能作为当前版本已经支持
> FreeCAD、Linux 建模或 `autoblade` Python namespace 的证据。当前 `0.2.0`
> 实现见[架构说明](architecture.md)，迁移顺序和退出门槛见
> [`0.3.0` 实施计划](plans/autoblade-0.3.0.md)。

## 目标与系统边界

`0.3.0` 把产品身份从 CATIA AutoBlade 迁移为 AutoBlade，并在保留
Windows/CATIA 建模能力的同时增加 Linux/FreeCAD 后端。两个后端共享输入、
任务和命令语义，但各自拥有 CAD 进程、原生特征和导出实现；共享核心不加载
CATIA COM 或 FreeCAD Python 模块。

首个目标支持矩阵为：

| 平台 | CAD 后端 | `0.3.0` 目标状态 |
| --- | --- | --- |
| Windows 11 x64 | CATIA P3 V5-6R2020 | 保持既有 preview 支持和默认 backend |
| Linux x86_64 | Flatpak FreeCAD 1.1.3 | 新增 preview 支持 |
| Windows | FreeCAD | 后续认证，不是 `0.3.0` 退出条件 |
| Linux | 原生 `FreeCADCmd` | 保留类型化 Launcher 扩展点，尚不认证 |

`0.3.0` 仍只交付受控团队使用的内部 wheel。公共 PyPI、独立 EXE、第三方
CAD 插件 API、并行 CAD 调度和完整 FreeCAD 参数化输入编辑器不是目标。

## 目标组件与数据流

```mermaid
flowchart LR
    User[工程人员或 CI] --> CLI[autoblade CLI]
    Config[config schema v4] --> Select[Backend selection]
    CLI --> Select

    subgraph Host[AutoBlade host Python process]
        Select --> Planner[Parser / Validation / Planner]
        Planner --> Job[Closed BladeBuildJob]
        Job --> Executor[Executor]
        Executor --> Factory[Internal CAD backend factory]
        Planner --> Manifest[Dry-run / manifest v3]
    end

    Factory --> CatiaAdapter[CATIA Adapter]
    CatiaAdapter --> COM[Owned COM session]
    COM --> CATIA[CATIA V5]
    CATIA --> CatiaArtifacts[CATPart + STEP]

    Factory --> FreeCADAdapter[FreeCAD Adapter]
    FreeCADAdapter --> Supervisor[Owned process supervisor]
    FreeCADAdapter --> Request
    Supervisor --> Flatpak[Flatpak launcher]

    subgraph Child[Isolated FreeCADCmd process]
        Flatpak --> Runner[Versioned runner]
        Request[Closed SI-unit JSON request] --> Runner
        Runner --> NativeModel[Accuracy-validated geometry engine]
        NativeModel --> FreeCADArtifacts[FCStd + STEP]
        Runner --> Result[Structured JSON result]
    end

    Result --> FreeCADAdapter
```

### Host 进程职责

- 配置选择、CSV 解析、领域校验、跨文件引用闭合、任务展开和输出冲突检查；
- 在 Planner 阶段确定 backend 和真实制品路径，使 dry-run 无需启动 CAD；
- 通过内部类型化 factory 把任务交给一个后端，不做自动探测或静默回退；
- 监督 FreeCAD 子进程，解释 timeout、退出码和结构化结果，并验证最终制品；
- 批任务记录单项结果并继续，但用户中断会停止整个调用。

### CAD 后端职责

- 把共享的 m/deg 领域数据转换为 CAD 边界要求的单位和对象；
- 创建原生几何、更新模型、保存原生文件并导出 STEP；
- 只管理自己创建的会话、文档、进程和暂存文件；
- 把厂商异常映射为 backend unavailable、timeout、protocol、geometry、
  artifact validation 或 cleanup 等项目错误。

Backend factory 是内部模块 seam，不是动态发现的公共插件协议。CATIA 继续使用
每任务一个 `DispatchEx` 独占 COM 会话；FreeCAD 使用每任务一个
`FreeCADCmd` 子进程。共享核心不得导入任何一方的运行时对象。

## CLI、配置与规划契约

`create`、`batch` 和 `sweep` 都增加命令级 `--backend catia|freecad`；独立入口
继续拥有同一选项。解析优先级固定为 CLI 参数、选中配置、内置 `catia` 默认值，
不同操作系统不会改变默认 backend。

目标配置 schema 为 `4.0.0`：

```toml
version = "4.0.0"

[defaults]
backend = "catia"

[freecad]
launcher = "flatpak"
app_id = "org.freecad.FreeCAD"
timeout_seconds = 900
```

`3.0.0 → 4.0.0` 使用既有显式预览、摘要校验、备份和原子替换流程。规范用户配置
目录迁移为 `autoblade`；仅当新目录不存在时才读取旧 `catia-autoblade` 目录并
警告，持久化只写新目录。如果两个目录同时存在，新目录唯一胜出。

`sweep` manifest 直接升级到 schema v3：顶层记录唯一 `backend`，每个任务使用
带类型的 `artifacts` 描述 native model 和 STEP，不保留 v2 `output_files` 过渡
字段。一次命令不能混用后端。

`--dry-run` 执行完整输入验证、任务展开、制品规划和冲突检查，但不检查 CAD 是否
安装，也不启动外部进程。`doctor` 默认只检查最终选中的 backend，可由
`--backend` 覆盖；`--all` 显式检查全部后端，任何一个 FAIL 都返回非零。
FreeCAD doctor 会运行短暂 headless 探针，检查 launcher、版本、FCStd 创建与重开、
以及目标路径可见性，而不是生成完整叶片。

## FreeCAD 进程与协议边界

首个认证命令为：

```text
flatpak run --command=FreeCADCmd org.freecad.FreeCAD <runner.py>
```

本机已验证该入口可返回 FreeCAD 1.1.3；AutoBlade 不负责安装或升级 Flatpak。
1.1.3 是无警告的认证版本；其他 `>=1.1` 版本允许运行但报告未认证警告，低于
1.1 的版本拒绝运行。CI 和 `0.3.0` 发布证据固定使用 1.1.3。

Runner 是随 wheel 分发的固定脚本，不能由请求指定任意模块或函数。Host 与 Runner
通过请求和结果 JSON 通信；两者都有严格 `schema_version`，遇到未知版本立即失败。
请求只包含已经校验、闭合的任务数据、明确的 `length_unit = "m"`、尾缘拓扑、
暂存目标和建模选项，不重新读取或解释 CSV。Runner 在 FreeCAD 边界把长度转换为
mm，并只向结果 JSON 和捕获的 stdout/stderr 报告状态。

每个任务在目标输出文件系统内获得独立隐藏暂存目录，以便 Flatpak 访问并保持
同文件系统发布。成功或失败结束后清理请求、结果和非保留中间文件。Host 完整
捕获输出，普通模式只显示结构化摘要，`--verbose` 才呈现完整诊断；成功任务不
额外生成日志文件。

单任务默认 timeout 为 900 秒，可由配置和命令行覆盖，不自动重试。Timeout 只在
已经得到可识别 FCStd 时尽力保留失败快照；不能安全取得时只报告 timeout。
Ctrl-C 终止当前 AutoBlade 所属进程、清理暂存并停止整个调用。实现不得使用会
终止用户 FreeCAD GUI 的全局 `flatpak kill`。

未来 NativeLauncher 只能接受经类型、存在性和可执行性校验的 executable path，
不能退化为自由 shell command。

## FreeCAD 几何构造与模型交付

**阶段 2 已选 Gordon 路线并于 2026-09-16 GO。** 用户于 2026-09-08 明确要求
精度优先，[ADR-0005](adr/0005-prioritize-geometric-accuracy.md) 替代原生 Loft
限定；2026-09-15 又批准当前代表案例的已观测差异用于预期科学计算。固定 Runner
现已从闭合 JSON 干净重建同一案例，并仅从 FCStd 嵌入请求得到逐值一致测量，证据
见[干净重建验证](validation/gordon-clean-rebuild-2026-09-15.md)。黄金基线、STEP
设置、分层回归阈值和 v2 适用性也已获批准；这允许正式集成继续，不代表 FreeCAD
已经是当前产品能力。

Host 仍只传入已闭合 SI 单位任务；CAD 子进程负责几何构造和边界单位转换。
当前候选保持 TE→LE→TE 点序：尖尾缘拆为 upper/lower B-spline，钝尾缘使用一张
TE-upper→LE→TE-lower full-wrap 曲面并增加显式 ruled closure。profile 按分区累计
弧长参数化；LE 与两条 TE guide 共享按相邻站位三边平均距离得到的 span 参数。
固定 Runner 直接调用 CurvesWB Gordon builder，绕开其会改变曲线几何的自动求交、
排序和近似重参数化。每张曲面内部 knot 连续性至少为 C2；曲面接缝、根尖封盖和
钝后缘 closure 只要求 C0 与最终 watertight single solid。阶段 2 Runner 还强制
截面/导引有限采样保持不超过 `network bbox diagonal × 1e-5`；该数值是算法完整性
gate，不是制造公差或连续 Hausdorff 上界。

不要求不同翼型点数相同；保持 TE→LE→TE 输入语义、变换顺序与尖/钝拓扑。
任何重新参数化、近似或采样均必须显式记录参数及对原始输入的几何误差。
不得为绕过失败静默删点、移动点或钝化尾缘。

目标 FCStd 采用静态 Shape 加可重建输入/算法参数：`BladeSolid` 是快照，
`InputCurveNetwork` 保存曲线网络快照，`Traceability` 内嵌 canonical 闭合请求、
摘要、算法/依赖版本、单位、连续性和重建声明。它不宣称拥有 Sketch→结果的原生
参数化依赖；受支持重建是用随版本固定的 Runner 和算法源码重新执行嵌入请求，
且不依赖用户工作区绝对路径。CurvesWB 最小源码闭包同时含 Apache-2.0 和
LGPL-2.1-or-later 文件；当前原型只引用本机固定 checkout，尚不是可分发实现。
源码、许可证文本和归属说明的目标交付已由
[ADR-0006](adr/0006-bundle-pinned-curveswb-source-closure.md) 固定：wheel/sdist
随附未修改的七文件最小源码闭包、双许可证和来源/摘要 manifest，默认认证模式
验证固定字节；显式 developer override 允许替换源码但标记为非认证结果。阶段 3
实现前不把该目标写成当前 wheel 能力。

精度优先不等于放弃生命周期、依赖许可、headless、有效单实体或 STEP 验证。
2026-09-15 用户已批准当前 89 截面三翼型 Gordon/CATIA 代表案例的已观测差异
用于预期科学计算用途；这是一项逐案例适用性判断，尚未定义通用制造公差、完整
矩阵回归阈值或 STEP writer precision。仍须区分求解容差、测量误差、输入保持
误差和跨后端差异。

## 制品与 STEP 契约

| 后端 | 原生模型 | 中性模型 |
| --- | --- | --- |
| CATIA | `.CATPart` | `.stp` |
| FreeCAD | `.FCStd` | `.stp` |

两个文件组成一个逻辑制品集。Planner 发现任一目标已存在时都执行现有冲突与覆盖
流程，不能把两次运行产生的文件拼成一个结果。跨后端比较由调用者指定不同输出
目录，不自动增加 backend 后缀。

FreeCAD 在同一暂存目录生成 FCStd 和 STEP，依次验证文件存在、非空、FCStd 可
重开并按声明方式重建、STEP 可重开且包含一个有效实体后，才发布到最终位置。文件系统
不能把两个文件通过一次 rename 同时提交，因此 Adapter 必须以回滚保护发布步骤；
任何部分发布都不能返回成功。

FreeCAD STEP 固定为 AP242DIS 几何、单位 mm，并在独立进程内显式设置 schema、
单位、精度和曲面写出参数；不读取或持久修改用户 GUI 偏好，也不宣称完整 AP242
产品数据交换。阶段 2 已依据 FreeCAD 1.1.3 / OCCT 7.8.1 实测并批准
`write.precision.mode=2`、`write.precision.val=1e-7 mm` 和
`write.surfacecurve.mode=1`；完整依据和已批准的分层回归阈值见
[precision 与 CATIA v2 对照提案](validation/freecad-precision-proposal-2026-09-16.md)。
FreeCAD headless 与 OCCT STEP writer 的能力依据见
[Headless FreeCAD](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Headless_FreeCAD.md)
和 [OCCT STEP guide](https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/step/step.md)。

`--keep-failed-model` 在几何失败且仍有可保存文档时提升一个不覆盖历史结果的失败
FCStd，不导出 STEP；旧 `--keep-failed-part` 暂作为弃用 alias。成功的普通
`create`/`batch` 不增加 sidecar JSON，来源元数据保存在 FCStd；sweep manifest
仍是扫描级可序列化记录。

## 正确性与认证边界

默认 pytest 使用 fake COM、fake process runner 和临时文件，不启动真实 CAD。
真实 Linux FreeCAD job 使用经过许可审查的 CATIA STEP 黄金基线，比较：

- STEP 可重开、形状有效且恰有一个 solid；
- 体积、包围盒和质心；
- 输入站位截面偏差；
- 表面采样最大值和 RMS 偏差。

跨后端不比较 CAD 文件字节、面数、边数或拓扑编号。黄金基线是重要参照，但输入
契约和经批准的工程公差拥有最终权威；更新必须由 CATIA 显式生成、记录版本与摘要
并人工批准，FreeCAD 测试不能改写期望结果。详细案例、CI 和发布门禁由
[`0.3.0` 实施计划](plans/autoblade-0.3.0.md)维护，决策理由见
[ADR-0004](adr/0004-use-curated-cross-backend-golden-baselines.md)。

## 已通过的可行性闸门与后续矩阵

阶段 2 已用原型、真实证据和用户批准确定以下边界，不能因实现需要自行放宽：

- 受约束曲面、Gordon 或自定义算法对 300/253/249 点多翼型、260 点钝尾缘和
  1000 点密集轮廓的精度、稳定性、重建依赖与性能；
- AP242DIS writer 固定显式 `1e-7 mm`；
- 体积、截面、表面、质心和包围盒的代表案例默认值已经批准，仍须由阶段 4 完整
  黄金矩阵验证默认值与逐案例覆盖；
- 首个公开 CATIA STEP `d9ef236c…824db9` 的黄金身份与再分发已于 2026-09-16
  获批；入库前仍须清理路径元数据、验证几何未变并记录最终摘要，完整矩阵未齐备。

如果几何精度、尖/钝拓扑、保存重开/声明的重建方式或黄金对照任一关键条件失败，
正式集成停止并返回设计决策。替代路线按 ADR-0005 显式评估，不允许静默改变输入。

## 决策记录

- [ADR-0001：采用 AutoBlade 多后端产品身份](adr/0001-adopt-autoblade-multi-backend-identity.md)
- [ADR-0002：隔离 CAD 后端与 FreeCAD 进程](adr/0002-isolate-cad-backends-and-freecad-processes.md)
- [ADR-0003（已替代）：生成原生可重算的 FreeCAD 模型](adr/0003-build-native-recomputable-freecad-models.md)
- [ADR-0005：以几何精度决定建模路线](adr/0005-prioritize-geometric-accuracy.md)
- [ADR-0004：使用经治理的跨后端黄金基线](adr/0004-use-curated-cross-backend-golden-baselines.md)
