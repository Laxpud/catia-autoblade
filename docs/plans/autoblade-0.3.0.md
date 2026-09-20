# AutoBlade 0.3.0 多后端实施计划

> **状态：活动计划。** 根 [`TODO.md`](../../TODO.md) 是唯一活动工作入口；本文
> 保存跨模块实施顺序、阶段门禁、验证和回滚，不承担当前架构说明。目标边界见
> [AutoBlade 0.3.0 目标架构](../architecture-target.md)，关键取舍见
> [`docs/adr/`](../adr/)。

## Outcome

交付一个受控团队使用的 `0.3.0` 内部 preview wheel：产品规范身份为 AutoBlade，
Windows/CATIA 继续工作且仍为默认 backend，Linux/Flatpak FreeCAD 1.1.3 能通过
同一 `create`、`batch` 和 `sweep` 任务体系生成原生 FCStd 与 AP242DIS STEP，并
满足双平台安装、真实 CAD、黄金几何和进程清理门禁。

## 范围与非目标

本计划包含：

- distribution、Python namespace、用户配置目录和发布制品迁移；
- 内部 CAD backend seam 与 backend-aware Planner/Job/Executor；
- Flatpak FreeCADCmd Runner、进程监督、可追溯重建模型和双制品事务；
- 配置 schema v4、sweep manifest v3、CLI、doctor、dry-run 和失败快照；
- 可公开 CATIA 黄金基线、Linux CI、双后端发布验证和当前文档切换。

本计划不包含公共 PyPI、独立 EXE、公共第三方 backend API、Windows FreeCAD
认证、原生 Linux FreeCADLauncher、并行建模、自动安装 CAD、完整 FreeCAD 输入
参数化或任意用户编辑后的几何保证。

## 依赖与治理边界

| 依赖或决定 | 进入条件 | 责任边界 |
| --- | --- | --- |
| 首个 CATIA 黄金样例 | 2026-09-16 已批准 STEP `d9ef236c…824db9`，并允许随公开测试夹具分发 | 入库前清理路径元数据、验证几何未变并记录新摘要 |
| 完整黄金矩阵 | 阶段 4 和 `0.3.0` 发布前齐备 | 包括多钝翼型等当前仓库没有的参考结果 |
| 当前代表案例的几何适用性 | 2026-09-15 已批准用于预期科学计算用途 | 批准覆盖当前 89 截面三翼型模型的已观测差异，不外推为通用制造公差 |
| STEP precision 与矩阵回归阈值 | 阶段 2 已形成实测提案；进入阶段 3 前批准代表案例，阶段 4 和 `0.3.0` 发布前由完整矩阵固化 | 实现者依据已批准用途和实测数据提出；不能为通过测试自行放宽 |
| GitHub 仓库改名 | 阶段 5 切换链接前完成 | 需要用户单独授权或亲自执行 |
| CATIA 发布验证 | 发布候选 wheel 完成后执行 | 需要受支持的 Windows/CATIA 环境 |

PyPI 名称注册、当前 checkout 移动、CATIA 基线批准和 Git commit 都不是执行本
计划的隐含授权。

## 全局执行规则

- 阶段按顺序推进；当前阶段的退出条件未满足时，不把下一阶段标为进行中。
- 每次只改当前阶段所需的接口和文档，不提前宣称目标能力已经可用。
- 输入解析、领域校验、跨文件引用和输出冲突始终在 CAD 启动前完成。
- 新后端失败必须显式暴露；禁止自动回退、静默几何近似或降低退出条件。
- 非简单源码阶段完成时运行仓库统一检查；真实 CAD 门禁只能由对应显式 smoke
  和记录证明。
- 完成一个阶段后在本文记录最小可复查证据，并同步根 TODO 的 Current focus。

## 阶段 0：设计与文档基线

Outcome：把已确认的设计树变成可导航的术语、ADR、目标架构和活动计划，且不把
目标态写成当前能力。

- [x] 固定领域词汇与 AutoBlade/CAD backend/制品集/几何等价语义。
- [x] 记录产品身份、进程边界、FreeCAD 原生模型和黄金基线 ADR。
- [x] 区分 `0.2.0` current architecture 与 `0.3.0` target architecture。
- [x] 将第二后端从条件性方向提升为有退出条件的 primary milestone。

Exit gate：上述文档互相可达，历史归档未被改写，源码和当前能力说明未被提前
迁移。证据是 [`CONTEXT.md`](../../CONTEXT.md)、[目标架构](../architecture-target.md)、
[`docs/adr/`](../adr/) 和本文。

## 阶段 1：产品身份与平台边界

Outcome：代码库以 AutoBlade 为规范身份，在尚未启用 FreeCAD 建模时仍保持
Windows/CATIA 行为，并能在 Linux 安装、导入和执行无 CAD 规划路径。

- [x] 将 distribution 改为 `autoblade`，把源码 package 和全部内部 import 迁移为
  `autoblade`，不保留 `catia_autoblade` shim。
- [x] 保留 `autoblade`、`autoblade-create`、`autoblade-batch` 三个 console entry，
  把产品级文本改为 AutoBlade，保留 backend 专属 CATIA 术语。
- [x] 更新 Hatch 白名单、资源路径、版本唯一来源、锁文件、构建校验和内部发布
  元数据；`uv.lock` 只能由工具同步。
- [x] 使主 wheel 可在 Linux 安装，`pywin32` 继续仅由 Windows marker 引入；核心
  import 和 Planner 不加载任一 CAD 运行时。
- [x] 建立新 `autoblade` 用户配置目录、旧目录 fallback、显式迁移和“双目录时新
  目录胜出”测试。
- [x] 检测旧 `catia-autoblade` distribution 与新 wheel 共存并给出先卸载旧包的
  明确迁移错误。

验证状态（2026-09-07，阶段 1 Exit gate 已通过）：

- 2026-09-03，Linux 已运行 `bash scripts/check-linux.sh`，通过 151 项
pytest、Ruff、`autoblade-0.2.0` wheel/sdist 构建、全新 CPython 3.14.4 非 editable
安装、三个 console entry、Parser/Planner/mock 执行、资源、配置目录迁移、旧
distribution 冲突和分发内容校验。
- 2026-09-07，Win11 在本地目录
  `%LOCALAPPDATA%\AutoBlade-checks\run-20260907-150926` 运行完整
  `pwsh -File scripts/check.ps1`，退出码 0；CPython 3.14.7、uv 0.12.10，151 项
  pytest、Ruff、`autoblade-0.2.0` wheel/sdist 构建、非 editable wheel smoke
  （入口、工作区初始化、配置迁移、输入预检及 mock 建模）和分发元数据/内容校验
  全部通过。日志与摘要保存在同一父目录的
  `records\run-20260907-150926\`，验证通过的运行副本已清理。
- `W:` 共享盘曾在启动器和严格路径解析处失败；同一源码复制到 Windows 本地
  磁盘后完整检查通过。本次未执行真实 CATIA，不作为真实几何或发布候选验收证据。

Exit gate：Windows 现有无真实 CATIA 检查和安装 smoke 通过；Linux 的全新环境能
安装 wheel、导入核心、运行 help/version/Parser/Planner；版本输出、wheel/sdist
根目录、资源和配置来源只使用新规范身份。此阶段不改 GitHub 远程和 checkout。

Rollback：在尚未执行外部仓库改名或分发新 wheel 前恢复旧 distribution/package
路径和构建清单；用户配置迁移只在显式 apply 后发生，并保留原文件备份。

## 阶段 2：FreeCAD 几何精度与路线闸门

Outcome：用最小、可丢弃的 headless Runner 比较精度优先的建模方案，在 FreeCAD
1.1.3 上确定满足几何要求且可复现的交付方式，再决定是否允许正式集成继续。

2026-09-08 范围调整：用户允许其他路线，ADR-0005 替代原生 Loft 的先验限定。
调整的是实现限制，精度、单实体、追溯与重建验收仍未通过，不借变更标记完成。

- [x] 通过固定 Runner 和版本化 JSON，把一个已闭合 SI 单位任务传入 Flatpak
  `FreeCADCmd`；不重新解析 CSV，不依赖 `if __name__ == "__main__"`。
- [x] 以受版本控制的 upper/lower 插值 B-spline 表达截面，在尖尾缘共享顶点，
  在钝尾缘增加显式 closure；原始点保持权威，重新参数化或近似必须记录误差。
  原生 Sketch 限制已由 ADR-0005 替代；钝尾缘实际采用没有 LE 接缝的 full-wrap
  曲面和 TE closure，参数化及误差由 request/result v2 显式记录。
- [x] 对比受约束曲面/Gordon/自定义算法，显式测量截面和导引保持、曲面连续性
  与跨后端偏差；验证有效闭合 `BladeSolid` 并确定依赖/重建交付方式。
- [x] 保存 FCStd，关闭重开并按声明的方式重建，验证仍为有效单 solid；记录任何
  外部依赖/快照语义，导出单位 mm 的 AP242DIS STEP 并验证文件 schema。
- [x] 覆盖单尖、单钝、300/253/249 点多翼型和明显变换；用 1000 点翼型记录耗时
  与峰值内存，不设置尚无证据的性能 SLA。
- [x] 至少取得一套获许可 CATIA STEP，输出几何差异报告和待批准的 precision/
  tolerance 建议。

验证进展（2026-09-07）：五个公开输入/派生案例通过本机原型的闭合 Sketch、
原生 Loft 单实体、保存重开强制重算、AP242 schema/mm 单位和 STEP 重开检查；
包含 89 截面不同点数、1000 点和明显变换，耗时/峰值内存已记录。详细证据与
本机复现边界见[阶段 2 实测记录](../validation/freecad-prototype-2026-09-07.md)。
多翼型 STEP 往返体积相对差约 0.0124467%，尚未定位；没有获许可 CATIA
对照、precision/公差批准或 GUI 可见性验收，因此 checklist 保持未完成，
未形成 GO。下一步先补差异定位与基线，不提前进入阶段 3。

后续进展（2026-09-08）：用户授权后已在 win11 交互 Session 1 从非 editable
wheel 生成 89 截面 CATPart/AP242 STEP，特征树、零新增 CNEXT、双平台完整
检查和 Windows 临时副本清理通过。候选输入/产物摘要和保存会话诊断见
[CATIA 候选对照记录](../validation/catia-baseline-2026-09-07.md)。双向曲面
采样最大差约 0.512 mm；截面提取完整性和默认体积积分仍需完善。
截至该次记录只取得候选对照，尚未批准黄金基线或工程公差，阶段 2 未 GO；
黄金与公开分发后来于 2026-09-16 获批，数值仍按下方后续进展治理。

偏差诊断（2026-09-08）：逐面投影和独立后缘参数取点确认真实偏差，叶根
实测至少 0.571 mm；前后缘驱动约束及展向插值不同是主要方向，详见
[偏差诊断](../validation/freecad-deviation-analysis-2026-09-08.md)。改变 MaxDegree
的显式重建实验未得到有效修复，不用于 gate；不得以加密采样或放宽公差替代修复。

新路线验证（2026-09-08）：固定 CurvesWB 版本的 Gordon 原型生成有效闭合
单实体、可重开静态 FCStd 和 AP242 STEP。固定叶根 X=83 mm 偏差从 0.571 mm
降到 0.000336 mm，但反向曲面采样仍约 0.330 mm。截面/导引误差、性能、
静态交付限制及下一步见[Gordon 实测](../validation/gordon-prototype-2026-09-08.md)。
当时尚未完成干净输入重建、完整矩阵或公差批准，保持未 GO。

切换区诊断（2026-09-09）：两个翼型切换区共 39 个固定站位均取得完整闭合
截面；输入截面保持最大约 0.0014 mm，但收敛后的固定截面差异分别达到约
0.2023 mm 和 0.3857 mm，后一极值点到完整三维曲面仍约 0.3818 mm。同弧长
对应只增加较小偏差，支持把主要问题定位为截面间曲面选择而非输入保持或单纯
参数错位。方法、限制及下一步见[切换区固定采样诊断](../validation/gordon-transition-analysis-2026-09-09.md)。
当时的下一步是定义显式展向插值与连续性规则并比较候选；未选定算法或批准
CATIA 真值，保持未 GO。

人工验收（2026-09-15）：用户手动对比当前 Gordon FreeCAD 模型和 CATIA 候选
模型，判断两者视觉上几乎完全重合，当前已观测差异不会对预期科学计算造成明显
问题，并批准该代表案例的当前公差。此前约 `0.3857 mm` 的固定截面峰值和约
`0.3818 mm` 的三维曲面距离继续作为已知测量边界，不再要求为贴合 CATIA 黑盒
行为继续选择候选。后续以 Gordon 路线完成展向插值/连续性契约、干净 JSON 输入
重建、依赖/许可证和 FCStd 交付方式，并补齐剩余矩阵。详细范围见
[人工验收记录](../validation/gordon-transition-analysis-2026-09-09.md#2026-09-15-人工验收)。
此次批准不等于 CATIA 黄金基线、通用制造公差或 STEP writer precision 批准，
因此阶段 2 仍未 GO。

干净重建与拓扑矩阵（2026-09-15）：新增 wheel 外的阶段 2 固定 Runner、严格
request/result JSON、Host 请求生成器与受控 Flatpak Launcher。初版实测暴露
CurvesWB 自动近似重参数化会让部分案例的 guide 漂移 3–11 mm；v2 改为 AutoBlade
显式提供 profile/span 共同参数并直接调用 Gordon builder，同时把截面/导引保持
提升为按模型尺度计算的强制 gate。单尖、单钝、300/253/249 点多翼型、1000 点和
明显变换均生成有效闭合单 solid，FCStd/AP242 STEP 重开通过，内部 knot 连续性
至少 C2；1000 点耗时约 55.5 s、峰值 RSS 177,444 KiB，多翼型耗时约 383.9 s、
峰值 RSS 307,152 KiB。依赖的 Apache-2.0/LGPL-2.1-or-later 混合边界已显式记录。
证据见[干净输入与嵌入请求重建](../validation/gordon-clean-rebuild-2026-09-15.md)。
依赖随附目标已由
[ADR-0006](../adr/0006-bundle-pinned-curveswb-source-closure.md) 固定为 wheel 内未修改
最小源码闭包、双许可证、来源/摘要 manifest 和显式非认证 override；实际 vendoring
及分发测试属于阶段 3。截至该次记录 STEP precision 和黄金基线仍未完成，阶段 2
保持未 GO；二者后来按下方 2026-09-16 记录获批。

precision 与 v2 对照提案（2026-09-16）：显式 OCCT STEP writer mode 2 /
`1e-7 mm` 与当前平均 BRep 容差得到相同往返几何；request v2 重新对比 CATIA 候选
得到全局有限曲面最大 `0.357179 mm`、完整固定截面最大 `0.385172 mm`、相对体积
差 `2.4705e-4` 和质心最大分量差 `0.0651 mm`。四层候选门限、制品摘要及一处
OCCT 固定截面提取不完整限制见
[FreeCAD precision 与 CATIA v2 对照提案](../validation/freecad-precision-proposal-2026-09-16.md)。
这是所需差异报告和数值建议。2026-09-16 用户已批准 CATIA STEP
`d9ef236c…824db9` 作为首个黄金基线并允许公开分发；STEP writer 设置、分层阈值
和 v2 适用性在解释其软件回归语义后也获批准。阶段 2 checklist 与 Exit gate
因此完成并 GO；这些阈值不是制造公差，完整矩阵固化仍属于阶段 4。

Exit gate：截面/导引保持、曲面精度、尖/钝拓扑、不同点数、保存重开与声明的
重建方式及至少一个 CATIA 对照均通过；算法、依赖、近似参数和测量误差可复查，
无用户偏好污染，基线和公差获批准。形成明确 GO 后才能进入阶段 3。

No-go：任一关键契约失败时停止，不先完成 CLI/config 基础设施；保留事实报告并
按 ADR-0005 重新评估路线。禁止静默改变输入或把未声明依赖/静态结果冒充可重建模型。

## 阶段 3：完整 backend 集成

> **状态：已完成（2026-09-20）。** 用户于 2026-09-19 明确恢复阶段 3；内部
> backend 集成、双平台完整检查和真实 FreeCAD 退出门禁均已通过。

Outcome：FreeCAD 作为内部正式 backend 接入现有单任务执行链，三个建模命令及其
规划、错误和制品语义完整可用。

- [x] 定义内部类型化 backend factory、backend-specific artifact plan 和结构化错误；
  不公开动态插件发现 API。
- [x] 让 CLI/config 在 Planner 前确定 backend，使输出冲突、预览和 dry-run 使用
  `.CATPart + .stp` 或 `.FCStd + .stp` 的真实路径。
- [x] 实现配置 schema `3.0.0 → 4.0.0` 显式迁移、命令级 `--backend`、900 秒默认
  timeout 与 CLI 覆盖；默认 backend 继续为 CATIA。
- [x] 实现每任务独立 FreeCADCmd 进程、严格 Runner 协议、stdout/stderr 捕获、
  timeout、Ctrl-C、owned-process 清理和未认证版本警告。
- [x] 实现目标文件系统内暂存、FCStd/STEP 验证、逻辑事务发布和部分发布回滚；
  任一目标存在都走完整冲突流程。
- [x] 实现 `--keep-failed-model`，并将 `--keep-failed-part` 保留为弃用 alias；timeout
  只在已有可识别 FCStd 时尽力保留。
- [x] 将 sweep manifest 升为 v3，记录 backend 和 typed artifacts，不保留 v2
  `output_files`；create、batch、sweep 不能在一次调用中混用 backend。
- [x] 使 doctor 按选定 backend 检查，FreeCAD 路径执行最小 headless 创建/重开
  探针；`--all` 中任一 backend FAIL 都返回非零。
- [x] 保持 batch/sweep 串行且每任务隔离；任务失败后继续，用户中断则停止整个调用。

验证状态（2026-09-20，阶段 3 Exit gate 已通过）：

- Linux CPython 3.14.4 与 Windows CPython 3.14.7 各通过 206 项 pytest、Ruff、
  构建、非 editable wheel 安装 smoke 和分发内容/依赖摘要校验；Windows 本地
  验证副本已清理，日志与摘要保留。
- 最终开发 wheel 在 Flatpak FreeCAD 1.1.3 上通过 doctor、尖尾缘 create、钝尾缘
  batch、尖/钝 sweep、FCStd 嵌入请求重建、timeout 和 Ctrl-C，任务进程与暂存均
  清理；另完成 89 截面多翼型代表模型，约 391.079 s、峰值 RSS 275,560 KiB。
- ADR-0006 的七文件未修改闭包、双许可证、来源/摘要 manifest、Host/Child 校验
  和显式非认证 override 已实现；最终 sdist 重建的 67 个包内文件逐字节一致。
- 原型两截面“无内部 knot”的连续性误判已修正并有回归；既有 knot 的 C2 门槛
  和已批准 STEP precision 均未降低。详细摘要、命令、日志和认证边界见
  [阶段 3 验证记录](../validation/backend-integration-2026-09-20.md)。

Exit gate：三个命令的普通、交互、dry-run、覆盖、失败继续和中断路径都有 mock
测试；本机 Flatpak 1.1.3 能通过 create/batch/sweep 真实 smoke；任何 return code
为零但结果 JSON 或双制品缺失的情形都判定失败；用户现有 CATIA/FreeCAD 会话不受
影响。

Rollback：在尚未发布 `0.3.0` 前可以移除 FreeCAD backend 路由并恢复 schema v3/
manifest v2 代码，但不得把已经显式迁移的用户配置无备份降级；回滚说明必须指出
如何恢复迁移前备份。

## 阶段 4：黄金回归与 Linux CI

Outcome：把 FreeCAD 从本机成功提升为可重复、可审计的 Linux preview 支持。

- [ ] 建立专用公开黄金夹具目录，只允许许可清晰的输入、CATIA STEP、manifest 和
  预计算指标；为全局忽略和构建排除设置精确例外，夹具不进入 wheel。
- [ ] 覆盖单尖、单钝、不同点数多尖、多钝以及明显旋转/缩放/平移；1000 点案例
  作为稳定性/性能 smoke。
- [ ] 实现 STEP 重开、单 solid、体积、包围盒、质心、站位截面和表面最大/RMS
  偏差比较；不比较二进制、面数、边数或拓扑编号。
- [ ] 把经批准的默认公差和有理由的逐案例覆盖写入 manifest；基线更新必须经过
  显式 CATIA 生成、SHA-256 校验和人工批准。
- [ ] 增加独立 Linux FreeCAD CI job；初期 non-blocking，稳定后对 backend、核心
  几何、输入拓扑和 Runner 相关变更设为 required，并定时运行完整套件。
- [ ] 固定 CI 认证环境为 Flatpak FreeCAD 1.1.3，记录典型、89 截面和 1000 点案例
  的耗时与峰值内存。

Exit gate：完整公开矩阵、许可、摘要、公差批准和 Linux CI 均可从干净 checkout
复现；FreeCAD 测试不能更新自己的黄金结果；相关变更 required 检查稳定通过。

Rollback：CI 未稳定前只允许从 non-blocking 回退并记录原因；一旦被 `0.3.0`
支持声明引用，不得为发布临时跳过黄金检查，必须修复或撤回该支持声明。

## 阶段 5：当前文档切换与 0.3.0 发布

Outcome：只有实现和证据完成后，才把 current documentation、支持矩阵和内部制品
切换到 AutoBlade 双后端事实。

- [ ] 更新 README 与中文镜像、AGENTS、current architecture、design principles、
  CLI、配置、安装、测试、分发和发布文档；保留历史归档及 `v0.2.0` release notes
  的原名称。
- [ ] 将唯一版本源迁移到 `src/autoblade/__init__.py` 并设为 `0.3.0`；整理
  `release-notes/unreleased.md` 和 `v0.3.0` 正式说明。
- [ ] 更新内部制品为 `autoblade-0.3.0...`，发布 manifest 使用
  `autoblade-internal-release/v2`，并检查旧 distribution 不共存。
- [ ] 在干净标签提交上通过 Windows 常规检查、Linux 常规检查和两个平台的 wheel
  安装/CLI smoke。
- [ ] 使用候选 wheel 完成真实 Windows/CATIA 与 Linux/FreeCAD 1.1.3 回归，检查
  native model、STEP、特征树、黄金几何和零残留 owned CAD 进程。
- [ ] 在获得单独授权并实际完成 GitHub 仓库改名后更新绝对仓库 URL；不注册或发布
  PyPI，不移动当前 checkout。

Exit gate：根 TODO 的全部 milestone exit criteria 都有可复查证据，wheel/sdist、
release notes、SHA-256、验证记录和内部 manifest 作为一个制品集交付。任何缺少
真实 CAD 或黄金证据的构建仍是开发产物，不得标为 `0.3.0` preview release。

Rollback：标签前修复并重新运行全部门禁；标签后不得替换同版本制品，必须递增
patch。已分发版本失败时停止分发、恢复上一批准 wheel，并按配置备份恢复；远程
仓库改名和用户 checkout 由其独立流程回滚。

## 验证矩阵

| 层级 | 环境 | 必须证明 |
| --- | --- | --- |
| 纯 Python | Windows 与 Linux | import 边界、输入契约、backend 选择、Planner、manifest、配置迁移和错误映射 |
| Fake CAD | 默认 pytest | COM/进程调用顺序、timeout、中断、失败继续、暂存/回滚和制品校验 |
| FreeCAD 原型 | Linux + Flatpak 1.1.3 | 精度、尖/钝、不同点数、保存重开/声明的重建、AP242DIS 和性能证据 |
| FreeCAD 黄金回归 | Linux + Flatpak 1.1.3 | 全案例工程公差、可重复性和无 owned-process 残留 |
| CATIA 回归 | Windows + CATIA P3 V5-6R2020 | 既有 CATPart/STEP 行为、黄金基线来源和无新增 CNEXT |
| 安装与发布 | 两个平台的干净环境 | wheel/sdist 身份、入口、依赖 marker、资源、文档、摘要和发布 manifest |

## Plan 生命周期

里程碑完成后，把目标架构中已经实现的部分合并进 current architecture，把最终
支持事实写入现有技术文档，并将本文与 TODO 的详细证据按仓库规则归档到
`docs/archive/`。未实现的 NativeLauncher、Windows FreeCAD、公共 PyPI、独立 EXE
和公共插件 API 留在 backlog，不得借归档隐藏。
