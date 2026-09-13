# 生成原生可重算的 FreeCAD 模型

Status: superseded by [ADR-0005](0005-prioritize-geometric-accuracy.md)（2026-09-08）

以下保留原决定及其历史约束。

FreeCAD 的 FCStd 必须由标准 App、Part、PartDesign 和 Sketcher 对象组成：截面使用原生 Sketch，最终叶片使用链接这些截面的原生实体 Loft。禁止把一次性计算结果包装成静态 Shape，也禁止依赖 FCStd 不会内嵌实现代码的自定义 FeaturePython；这样生成文件在标准 FreeCAD 中保存重开后仍可无修改 `recompute()`。

## Considered Options

- 静态 `Part::Feature.Shape` 最容易生成，却不能满足截面到实体的原生依赖关系。
- 自定义 FeaturePython 可以表达更多几何逻辑，但会让重算依赖安装 AutoBlade 或额外模块，破坏文件自包含性。
- 完整参数化 CSV、弦长和扭转会扩大为另一个产品能力，不属于本里程碑。

## Consequences

- 每个截面以统一前后缘拓扑保存插值 B-spline；不同翼型不要求相同点数，也不默认重采样。
- 尖尾缘保持共享顶点，钝尾缘使用显式闭合边；不能为绕过 OCC 失败而静默改变拓扑。
- 前后缘 Guide 只是标记为 `ReferenceOnly` 的冻结参考快照，不驱动 Loft，也不保证用户编辑后同步更新。
- AutoBlade 保证初始依赖和保存重开后的无修改重算；用户修改截面后的几何有效性由用户负责。
- 几何原型若不能满足这些条件，必须停止正式集成并重新决策，不能降级成静态或近似模型。
