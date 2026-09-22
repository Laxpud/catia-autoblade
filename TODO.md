# 项目任务清单

本文件是唯一活动工作入口，只记录已承诺里程碑、当前焦点、阻塞项和可验证退出
条件。跨模块实施细节由 [`docs/plans/`](docs/plans/) 维护，稳定技术契约见
[`docs/index.md`](docs/index.md)，已完成计划见 [`docs/archive/`](docs/archive/)。

## 执行与维护规则

- 用户明确指定的工作优先；否则执行 primary milestone 的 Current focus。
- Current focus 尚未通过其阶段 gate 时，不提前推进后续阶段。
- 任务只有在全部验收条件满足并记录可复查证据后才能标记 `[x]`；部分完成保持
  `[ ]`，不得通过删除或弱化退出条件制造完成状态。
- 复杂实施步骤、验证和回滚只在对应 Plan 中维护；本文件不复制第二套 checklist。
- 里程碑完成后，把持久事实写回技术文档，将详细记录归档到 `docs/archive/`，再从
  backlog 或用户新指令中提升下一项工作。

## 当前状态（2026-09-22）

- `0.2.0` 的单/多翼型、`create`/`batch`/`sweep`、CATIA Adapter、配置 schema
  `3.0.0`、sweep manifest v2 和内部 preview wheel 流程已经完成；证据见下方
  Recently completed。
- 用户已经确认 AutoBlade 多后端设计树，并把第二个真实 CAD 后端从条件性方向
  提升为当前承诺。
- 目标架构、ADR 和实施计划已经建立；阶段 1 的 distribution、Python namespace、
  配置目录和 Linux 无 CAD 路径已实现，Linux 与 Windows 完整检查及安装 gate
  均已通过，阶段 1 已完成。
- 阶段 3 的开发集成、FreeCAD 真实 smoke，以及阶段 4 的完整公开黄金矩阵和
  Linux 测量 CI 已完成；当前发布版本仍为 `0.2.0`，阶段 5 的真实 CATIA 发布
  回归、当前文档切换和正式发布尚未启动。
- 用户已人工对比当前 Gordon FreeCAD 模型与 CATIA 候选模型，确认两者视觉上
  几乎完全重合，并批准当前已观测差异用于预期科学计算用途；批准边界见
  [人工验收记录](docs/validation/gordon-transition-analysis-2026-09-09.md#2026-09-15-人工验收)。

## Primary milestone：AutoBlade 0.3.0 多后端内部 preview

Outcome：把产品规范身份迁移为 AutoBlade，保持 Windows/CATIA 既有行为，并在
Linux/Flatpak FreeCAD 1.1.3 上通过同一任务体系生成可追溯、可重建的 FCStd 和 AP242DIS
STEP，最终以一个经过双平台、双 CAD 和黄金几何验证的内部 `0.3.0` 制品集交付。

权威设计与执行入口：

- [领域词汇](CONTEXT.md)
- [目标架构](docs/architecture-target.md)
- [实施计划](docs/plans/autoblade-0.3.0.md)
- [架构决策](docs/adr/)

Current focus：**阶段 4 已完成；下一阶段为阶段 5，尚未启动。**
7 组公开参考覆盖单尖、单钝、不同点数多尖、多钝和三组明显变换，另有 1000 点
性能案例。人工结论与公开授权均可追溯；自动化只测量和生成标准报告，实际
可用性由人类判断，见 [ADR-0007](docs/adr/0007-measure-geometry-and-defer-usability-to-humans.md)。

GitHub 三轮独立 runner 完成全部公开矩阵和合成性能案例，下载后的报告、模型
摘要及零残留进程证据均已核验。Windows 干净 checkout 的 CurvesWB 换行问题
已修复，双平台各 269 项测试及完整检查通过。`main` 已要求
`FreeCAD measurement integrity`，相关改动执行完整测量，每周和手动运行同样
覆盖完整套件；纯文档变更返回状态并跳过 CAD。检查产物统一保留在项目
`output/stage4-ci-20260921/`，后续不再复制到 win11。完整本机模型与报告入口为
`output/AutoBlade-public-matrix-reproduction-20260921/index.html`，原人工结论在
`output/AutoBlade-standard-reports-20260921/human-review.json`。
具体数据与当前证据见[矩阵测量与交付](docs/validation/golden-matrix-2026-09-21.md)，
完整实施边界见[阶段 4 计划](docs/plans/autoblade-0.3.0.md#阶段-4黄金回归与-linux-ci)。

Dependencies：

- 首个 CATIA STEP 黄金基线及公开再分发已于 2026-09-16 获用户批准；公开夹具
  已完成路径元数据清理、几何未变验证，新摘要为 `0eb34e4a…42dafe0`。
- 单尖、单钝、多钝和三组变换的公开基线已于 2026-09-21 获独立授权，完整
  矩阵已齐备。STEP precision 保持既定设置，测量方法、标准报告和人工结论
  已版本化；完整 CI 脚本已在本机和独立 GitHub runner 复现，远程重复运行和
  required 配置证据见[远程验收记录](docs/validation/golden-matrix-2026-09-21.md#远程-ci-验收)。
- GitHub 仓库改名、PyPI 名称注册、checkout 移动、后续 CATIA 基线批准和 Git
  commit 均需要独立授权，不是本 milestone 的隐含操作权限。

Exit criteria：

- [x] distribution、Python namespace 和规范品牌均为 AutoBlade/`autoblade`；旧
  distribution 不共存，配置 v3→v4 和旧配置目录迁移可预览、备份和回滚。
- [ ] Windows/CATIA 仍是默认 backend，既有输入、命令、CATPart/STEP、真实 CATIA
  会话所有权和零新增 CNEXT 回归全部通过。
- [x] Linux/Flatpak FreeCAD 1.1.3 支持 `create`、`batch`、`sweep`、dry-run、doctor、
  manifest v3、失败快照和每任务隔离，成功产出完整 `.FCStd + .stp` 制品集。
- [x] FreeCAD 建模路线通过截面、导引与曲面精度验证，覆盖不同点数与尖/钝尾缘；
  FCStd/STEP 为有效闭合实体，保存重开与声明的重建方式可复现，任何拟合误差、
  外部依赖及静态快照属性均显式记录，不静默改变输入或拓扑。
- [x] 公开 CATIA 黄金矩阵、许可、摘要、标准误差报告、人工结论和 Linux 测量完整性 CI
  均可从干净 checkout 复现，1000 点样例具有性能记录。
- [ ] Windows 与 Linux 的常规检查、干净 wheel 安装 smoke、真实 CATIA、真实
  FreeCAD、双后端 STEP 和 owned-process 清理证据全部通过。
- [ ] README/中文镜像、AGENTS、current architecture、CLI、配置、安装、测试、
  分发、发布和 `v0.3.0` release notes 只在能力实现后同步为当前事实。

Tasks：

- [x] 2026-09-03：确认设计树并建立 glossary、四个 accepted ADR、target
  architecture 和分阶段 Plan；验证边界见[阶段 0](docs/plans/autoblade-0.3.0.md)。
- [ ] 按 [`docs/plans/autoblade-0.3.0.md`](docs/plans/autoblade-0.3.0.md) 顺序完成
  阶段 1–5，并在每个 gate 后记录证据和更新 Current focus。

## Backlog（未承诺）

- 认证带类型校验 executable path 的 NativeLauncher。
- 认证 Windows/FreeCAD 组合。
- 评估公共 PyPI 与名称注册。
- 评估独立 Windows EXE。
- 评估公共第三方 CAD backend API。
- 依据真实性能数据评估并行 CAD 调度。

## Recently completed

- [截至 `0.1.1` 的里程碑](docs/archive/milestones-through-0.1.1.md)
- [`0.2.0` 内部 preview wheel](docs/archive/internal-preview-wheel-0.2.0.md)
- [显式参数扫描 `sweep`](docs/archive/explicit-parameter-sweep.md)
- [真实示例与内置翼型目录](docs/archive/real-example-and-airfoil-library.md)
- [`section_params` → `blade_sections` 命名迁移](docs/blade-sections-migration.md)
