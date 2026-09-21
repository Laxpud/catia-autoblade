# 使用经治理的跨后端黄金基线

Status: superseded（2026-09-21）by
[ADR-0007](0007-measure-geometry-and-defer-usability-to-humans.md)。以下保留当时
的决策背景；来源、再分发、摘要和人工更新原则继续适用，数值自动裁决不再适用。

FreeCAD 的正确性不能只由文件存在、人工外观或与自身旧输出比较来证明。项目使用可公开再分发的输入、CATIA STEP、来源与版本 manifest 作为黄金基线，在 Linux 上按工程公差比较有效实体、截面、表面和整体几何；CATIA 是重要参照，但输入契约和经工程批准的公差才是最终裁判。

## Considered Options

- 每次 FreeCAD 调整都在线启动 CATIA，会把 Linux 开发和 CI 绑定到 Windows、许可证及桌面会话。
- 比较 STEP 字节、面数或拓扑编号，会把不同 CAD 内核允许的表达差异误判为回归。
- 只做人工目测无法提供稳定、可审计的发布门禁。

## Consequences

- 黄金夹具可以作为普通 Git 中的受审例外存在，但必须位于专用目录、附再分发依据，并排除在 wheel 之外；普通 CATPart、FCStd、STEP 和私有输入仍不得提交。
- 基线只允许通过显式 CATIA 生成、摘要校验和人工批准更新；FreeCAD 测试不得自动改写裁判。
- 公差使用受版本控制的默认值和有理由的逐案例覆盖，首批数值须由真实对照数据提出并由工程责任人批准。
- 真实 CATIA 主要用于生成或更新基线和发布候选验证，日常 Linux 回归读取已批准 STEP 即可。
