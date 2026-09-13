# 技术文档索引

本目录保存实现约束、数据契约和设计说明。项目介绍与使用入口见[英文 README](../README.md)，中文入口见[中文 README](README.cn.md)，领域术语见[领域上下文](../CONTEXT.md)，当前工作见 [TODO](../TODO.md)。

## 当前文档

- [当前架构](architecture.md)：`v0.2.0` 的模块边界、CATIA 建模流程、资源生命周期和当前限制。
- [设计原则](design-principles.md)：`create`、`batch`、`sweep` 的职责，模型输入模式和任务边界。
- [CLI 参考](cli.md)：命令参数、交互模式、任务预览、覆盖规则、退出码和示例。
- [输入数据格式](input-formats.md)：坐标系、CSV schema、单位、点序以及多翼型扩展状态。
- [真实示例数据审计](example-data-audit.md)：真实示例及其三个依赖翼型的来源、授权、脱敏边界、修改记录和 SHA-256。
- [内置翼型目录](airfoil-library.md)：已审计目录清单、显式复制语义、排除资产和目录变更门槛。
- [`section_params` → `blade_sections` 命名迁移](blade-sections-migration.md)：当前契约、破坏性边界、配置迁移和旧工作区操作。
- [展向多翼型设计](multi-airfoil-design.md)：输入路径、文件命名、逐截面引用、兼容模式、批处理和 Loft 对齐策略。
- [运行时配置](configuration.md)：配置来源、路径解析基准、CLI 覆盖优先级和输出命名模板。
- [安装、工作区与升级](installation.md)：内部 wheel、`init`、配置发现、升级、卸载和常见失败。
- [分发范围与支持策略](distribution-scope.md)：首个预览版本的目标用户、渠道、已验证环境、外部依赖和非目标。
- [内部 preview 发布与回滚](releasing.md)：标签、候选验证、SHA-256、发布 manifest 和失败处理。
- [未发布变更](release-notes/unreleased.md)：尚未进入新版本制品集的功能与分发边界变化。
- [自动化测试](testing.md)：无 CATIA 测试入口、覆盖范围、COM 隔离和真实几何回归边界。

## 已接受的目标设计与活动计划

以下文档描述尚未完成的 `v0.3.0` 目标，不代表当前版本已经支持 FreeCAD 或新的包名：

- [AutoBlade `v0.3.0` 目标架构](architecture-target.md)：多后端边界、FreeCAD 进程协议、精度优先的可追溯重建模型、产物事务和验证门禁。
- [AutoBlade `v0.3.0` 实施计划](plans/autoblade-0.3.0.md)：按依赖顺序拆分的阶段、退出条件、证据和回滚边界。

## 架构决策

- [ADR-0001：采用 AutoBlade 多后端身份](adr/0001-adopt-autoblade-multi-backend-identity.md)。
- [ADR-0002：隔离 CAD 后端与 FreeCAD 进程](adr/0002-isolate-cad-backends-and-freecad-processes.md)。
- [ADR-0003（已替代）：构建原生、可重算的 FreeCAD 模型](adr/0003-build-native-recomputable-freecad-models.md)。
- [ADR-0004：使用受控的跨后端黄金基线](adr/0004-use-curated-cross-backend-golden-baselines.md)。
- [ADR-0005：以几何精度决定 FreeCAD 建模路线](adr/0005-prioritize-geometric-accuracy.md)。

## 内容归属

- `README.md`：公开项目入口、当前能力、环境要求和最短使用路径。
- `CONTEXT.md`：跨模块共享的领域术语及其关系，不承载实现方案。
- `TODO.md`：唯一活动工作入口，只保留当前焦点、里程碑退出条件和到详细计划的链接。
- `docs/architecture.md`：已经实现的当前架构事实。
- `docs/architecture-target.md`：已接受但尚未全部实现的目标系统结构与长期约束。
- `docs/adr/`：重要架构决策、备选方案和后果；不代替当前或目标架构总览。
- `docs/plans/`：有结束条件的实施计划、依赖、验证证据和回滚策略。
- 其他 `docs/*.md`：稳定的技术契约、设计理由和长篇实现说明。
- `docs/archive/`：已经完成或被当前架构取代的历史计划；现有记录见[截至 0.1.1 的已完成里程碑](archive/milestones-through-0.1.1.md)、[`v0.2.0` 内部 preview wheel 里程碑](archive/internal-preview-wheel-0.2.0.md)、[显式参数扫描 `sweep` 里程碑](archive/explicit-parameter-sweep.md)和[真实示例与内置翼型目录里程碑](archive/real-example-and-airfoil-library.md)。

新增文档应优先补充现有主题。只有当内容具有独立维护边界时，才创建新的技术文档。
