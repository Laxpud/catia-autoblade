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

## 当前状态（2026-09-20）

- `0.2.0` 的单/多翼型、`create`/`batch`/`sweep`、CATIA Adapter、配置 schema
  `3.0.0`、sweep manifest v2 和内部 preview wheel 流程已经完成；证据见下方
  Recently completed。
- 用户已经确认 AutoBlade 多后端设计树，并把第二个真实 CAD 后端从条件性方向
  提升为当前承诺。
- 目标架构、ADR 和实施计划已经建立；阶段 1 的 distribution、Python namespace、
  配置目录和 Linux 无 CAD 路径已实现，Linux 与 Windows 完整检查及安装 gate
  均已通过，阶段 1 已完成。
- 阶段 3 已完成开发集成与 FreeCAD 真实 smoke；当前发布版本仍为 `0.2.0`，
  `0.3.0` preview 的完整黄金矩阵、CI、真实 CATIA 发布回归和正式发布尚未完成。
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

Current focus：**阶段 4：公开黄金夹具与回归数值契约。** 阶段 3 已于
2026-09-20 完成：内部 backend 集成、配置 v4、manifest v3、双平台各 206 项测试
及完整检查、FreeCAD 安装 wheel 三命令/重建/timeout/Ctrl-C 和 89 截面代表模型
均通过。下一项从获批 CATIA STEP 的元数据清理、几何未变验证和夹具 manifest
开始；阶段 4 尚未实施，阶段 5 发布仍待后续门禁。证据见
[阶段 3 验证记录](docs/validation/backend-integration-2026-09-20.md)。
阶段 2 已于 2026-09-16 GO：用户批准 request v2 Gordon 路线、首个可公开分发的
CATIA 黄金 STEP `d9ef236c…824db9`、显式 STEP writer mode 2 / `1e-7 mm` 和四层
软件回归阈值。全局有限曲面最大 `0.357179 mm`、完整固定截面最大
`0.385172 mm`；数值是内部 preview 回归门禁，不是制造公差。证据见
[干净重建与拓扑矩阵](docs/validation/gordon-clean-rebuild-2026-09-15.md)和
[precision 与 v2 CATIA 对照契约](docs/validation/freecad-precision-proposal-2026-09-16.md)。

Dependencies：

- 首个 CATIA STEP 黄金基线及公开再分发已于 2026-09-16 获用户批准；公开夹具
  入库前仍须清理路径元数据、验证几何未变并记录新摘要。
- `0.3.0` 发布前必须补齐单尖、单钝、不同点数多尖、多钝和明显变换的公开黄金
  矩阵。当前代表案例的几何适用性已获批准；仍需把 STEP precision 和各案例
  自动回归阈值写成受版本控制、可复现的数值契约。
- GitHub 仓库改名、PyPI 名称注册、checkout 移动、后续 CATIA 基线批准和 Git
  commit 均需要独立授权，不是本 milestone 的隐含操作权限。

Exit criteria：

- [x] distribution、Python namespace 和规范品牌均为 AutoBlade/`autoblade`；旧
  distribution 不共存，配置 v3→v4 和旧配置目录迁移可预览、备份和回滚。
- [ ] Windows/CATIA 仍是默认 backend，既有输入、命令、CATPart/STEP、真实 CATIA
  会话所有权和零新增 CNEXT 回归全部通过。
- [x] Linux/Flatpak FreeCAD 1.1.3 支持 `create`、`batch`、`sweep`、dry-run、doctor、
  manifest v3、失败快照和每任务隔离，成功产出完整 `.FCStd + .stp` 制品集。
- [ ] FreeCAD 建模路线通过截面、导引与曲面精度验证，覆盖不同点数与尖/钝尾缘；
  FCStd/STEP 为有效闭合实体，保存重开与声明的重建方式可复现，任何拟合误差、
  外部依赖及静态快照属性均显式记录，不静默改变输入或拓扑。
- [ ] 公开 CATIA 黄金矩阵、许可、摘要、工程公差、几何比较和 Linux required CI
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
