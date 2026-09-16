# Gordon 显式参数、拓扑矩阵与干净重建验证（2026-09-15）

结论：request/result v2 固定 Runner 已在 Flatpak FreeCAD 1.1.3 上通过单尖、单钝、
89 截面 300/253/249 点多翼型、1000 点和明显变换矩阵。所有成功项均为有效闭合
单 solid，FCStd 保存重开和 AP242 STEP 往返通过，曲面内部 knot 连续性至少 C2。
89 截面案例又仅从 FCStd 内嵌请求完成一次无 CSV 重建，两次 `measurements` JSON
逐值相等。

这完成了阶段 2 的闭合请求、截面/导引保持、公开拓扑矩阵和声明重建方式验证。
CurvesWB 最小源码闭包的目标随附方式已由 ADR-0006 确定，实际 vendoring 留到
阶段 3；STEP writer precision、黄金基线和跨后端自动回归阈值随后于 2026-09-16
获批，阶段 2 最终状态见本文末节。

## 受版本控制的原型契约

实现入口是 [`scripts/freecad_gordon_prototype/`](../../scripts/freecad_gordon_prototype/)：

- `prepare.py` 在 Host 侧调用现有 Parser，闭合全部 CSV 引用后输出
  `autoblade.freecad-gordon-prototype/request/v2`；JSON 只含 basename、源摘要、
  全部点/截面参数和制品 basename，不含源绝对路径。
- `protocol.py` 拒绝未知字段、未知 schema、非有限数值、后缘拓扑不一致、路径型
  制品名和摘要不匹配；Host 与 Child 使用同一标准库验证器。
- `runner.py` 由 FreeCADCmd 直接执行且末尾无条件调用，不依赖常规
  `if __name__ == "__main__"` 语义，也不导入 AutoBlade 或重读 CSV。
- `launch.py` 使用参数数组启动 Flatpak，每次只监督新建进程组；没有使用
  `flatpak kill`，也没有连接或退出用户 FreeCAD GUI。

89 截面 v2 请求 canonical SHA-256 为
`060cc2052bc137d21b6648e73b07b377210b62173e6c37f8ff23190939feaeb6`；
格式化 JSON 为 89,425 bytes，文件 SHA-256 为
`64cba940be628087d23c163e8c382d7b867e5b102f00d91b2aca65a0b28bab74`。

## 显式参数与数值 gate

1. 输入点的 TE→LE→TE 语义保持权威。每个截面由 OCCT B-spline 全局插值全部
   原始点，不删点、不重采样、不钝化；原始点到曲线的有限精度误差单独报告。
2. 尖尾缘拆成 TE→LE upper 与 LE→TE lower 两张曲面。钝尾缘使用一张
   TE-upper→LE→TE-lower full-wrap 曲面，使 LE 位于曲面内部，再以最终曲面两条
   TE 边创建 ruled closure；根尖封盖也复用最终曲面边。
3. sharp 每侧按自身累计弧长归一到 `[0, 1]`。blunt 上下半边各自按累计弧长
   归一到 `[0, 0.5]` 和 `[0.5, 1]`，因此所有 profile 的 LE 参数严格为 `0.5`。
4. LE、TE-upper、TE-lower 在每对相邻截面上的距离取平均，再累计归一，得到三条
   guide 共享的 span 参数。每个 profile/guide 交点在构造前已经拥有相同参数。
5. Runner 直接调用固定 CurvesWB `GordonSurfaceBuilder`，不再使用会自动求交、
   排序并近似重参数化曲线的 `InterpolateCurveNetwork`。因此 request v2 不含虚假的
   `max_control_points` 近似参数，算法身份是
   `curveswb-gordon-builder-explicit-parameters/v1`。
6. Runner 报告原始点→profile、profile→surface、guide→surface 三层误差，并强制
   后两者的最大有限采样距离不超过 `network bbox diagonal × 1e-5`。该相对 gate
   随模型缩放，只用于捕获算法/参数化失真，不是制造公差或连续 Hausdorff 上界。

每张 Gordon B-spline 曲面的 chordwise U 与 spanwise V 内部 knot 连续性均以
`degree - internal knot multiplicity` 计算并强制至少为 C2。upper/lower 接缝、
根尖封盖和钝尾缘 closure 只承诺 C0 与最终 watertight single solid，不把实体有效
误写为跨面 C1/C2。

## v1 缺陷与修正依据

v1 的 89 截面代表案例曾通过保存、重开和嵌入请求重建，但后续矩阵暴露了不能
接受的静默失真：单尖、单钝、1000 点和明显变换案例虽生成有效 solid，guide hold
最大却达到约 3–11 mm；部分日志还明确报告 B-spline network incompatible。原因是
`InterpolateCurveNetwork` 为统一交点参数会近似重参数化 profile/guide，所得曲线
可能在交点之间明显偏离原始 guide，而 v1 只报告误差、没有失败 gate。

v2 用已知点序和对应截面直接给出共同参数，绕开该近似步骤，并把 hold 报告提升为
强制 gate。修正后所有矩阵项的 section/guide hold 都降到约 `1e-12 mm` 量级，成功
日志不再出现 incompatible、warning、error 或 failed。旧 v1 数值仅保留为缺陷发现
证据，不再作为候选交付契约。

## 公开矩阵结果

所有时间和 RSS 都来自 result JSON；没有据此设置性能 SLA。

| 案例 | 截面/点数 | section hold max | guide hold max | elapsed | peak RSS |
| --- | --- | ---: | ---: | ---: | ---: |
| 单尖 `sc1095_sharp` | 26 × 260 | `9.4645e-13 mm` | `1.1763e-13 mm` | 11.630 s | 136,828 KiB |
| 单钝 `sc1095` | 26 × 260 | `8.0615e-13 mm` | `2.2739e-13 mm` | 15.576 s | 141,728 KiB |
| 多尖 | 89 × 300/253/249 | `8.6399e-13 mm` | `1.1481e-13 mm` | 383.879 s | 307,152 KiB |
| 1000 点单尖 | 26 × 1000 | `2.3609e-12 mm` | `1.1466e-13 mm` | 55.477 s | 177,444 KiB |
| 明显变换单尖 | 26 × 260 | `2.0597e-12 mm` | `2.2914e-13 mm` | 12.407 s | 136,552 KiB |

各项均通过 valid/closed/one-solid、FCStd 重开、AP242 schema 和 STEP one-solid
检查。明显变换为 `scale=1.7`、绕 X `37 deg`、平移 `(0.2, -0.1, 0.3) m`；其
体积比为 `4.9127932755`，理论 `1.7³=4.913`，相对残差约 `-4.21e-5`。该残差与
质心最大约 `0.013 mm` 的仿射一致性残差继续作为 mass-property/STEP precision
候选阈值证据，不把拓扑与 hold 通过扩张成尚未批准的工程公差。

## FCStd 与依赖交付语义

FCStd 中的 `BladeSolid` 是静态 `Part::Feature` 快照，`InputCurveNetwork` 保存
本次曲线网络快照，`Traceability` 保存 canonical 请求、请求摘要、算法、CurvesWB
commit/version、依赖指纹、单位、连续性契约和重建声明。该对象树不声称
Sketch→solid 的原生参数依赖；受支持重建方式是用固定 Runner 和固定依赖重新执行
嵌入请求。

原型使用 CurvesWB `0.6.81` commit
`e4972f761d126901d13b3a72be64eb14f7d51c92`。实际导入的七文件源码闭包指纹为
`973a68bb4b88dcc139316b9acb1ca80f609b3c0de717246b95260c8671d79a70`；其中 Gordon
及三个算法文件标记为 Apache-2.0，`nurbs_tools`、package init 和 version 标记为
LGPL-2.1-or-later。因此不能把整个依赖声称为 Apache-2.0。当前只引用本机固定
checkout，未把第三方源码放入产品 wheel。目标 wheel/sdist 将随附未修改七文件
闭包、双许可证和来源/摘要 manifest，默认验证固定字节，并允许显式的非认证本地
源码 override；完整约束见
[ADR-0006](../adr/0006-bundle-pinned-curveswb-source-closure.md)。

## 89 截面无 CSV 重建

| 项目 | 闭合 JSON 首建 | FCStd 嵌入请求重建 |
| --- | ---: | ---: |
| 请求来源 | `closed_json` | `embedded_fcstd_request` |
| request SHA-256 | `060cc205…feaeb6` | 同左 |
| FreeCAD | 1.1.3 | 1.1.3 |
| elapsed | 383.879 s | 386.464 s |
| peak RSS | 307,152 KiB | 291,972 KiB |
| solid | valid、closed、1 solid | 同左 |
| volume | 1,308,847.1596591389 mm³ | 同左 |
| center of mass | (349.420430348, -21.373832939, 1.469953756) mm | 同左 |
| hold/continuity/solid/reopen JSON | 基线 | 逐值相同 |
| FCStd 重开 | valid、closed、1 solid、嵌入摘要一致 | 同左 |
| STEP 重开 | AP242、valid、1 solid | 同左 |
| STEP volume | 1,308,847.1596586641 mm³ | 同左 |

首建制品：

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| `blade.FCStd` | 2,455,769 | `4cf9b148e526cff82e8625377230a5d565eeef228122411e7329bf78f11501d0` |
| `blade.stp` | 6,862,904 | `b815916a1fee7fcfbf6e78241afbf679c44e54a40652acb5d27a595a16fc3a52` |

嵌入请求重建制品：

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| `blade.FCStd` | 2,455,769 | `c0aa5e2113b763c114e65ff85f70f5bf55cae15cfa940418a7a988dee20f3b38` |
| `blade.stp` | 6,862,904 | `8916ad37219cb6fb9adef671097e00a60c281d991ea9cebf75c78ced017ba377` |

FCStd/STEP 文件摘要不同，不将带序列化元数据的二进制相等作为几何契约。本机
忽略目录 `output/gordon-clean-rebuild-20260915/` 保存请求、完整 result JSON、日志
和制品；Flatpak 不可见的宿主 `/tmp` 不用于 CAD 输入输出。

## 2026-09-16 precision 与 v2 CATIA 对照

同一 v2 FCStd 的 STEP writer 探针确认：显式 mode 2 / `1e-7 mm` 与当前 mode 0
平均 BRep 容差都声明 `1e-7 mm` uncertainty，重开几何和 mass properties 逐值
相同；相对体积差约 `3.63e-13`，双向有限曲面最大约 `1.87e-11 mm`。重新对比既有
CATIA 候选后，全局有限曲面最大为 `0.357179 mm`，完整固定截面最大为
`0.385172 mm`，独立复现此前人工接受的差异量级。完整 writer 设置、v2 对照、
一处 OCCT 截面不完整限制和随后获批的四层阈值见
[precision 与 CATIA v2 对照提案](freecad-precision-proposal-2026-09-16.md)。

## 2026-09-16 阶段 2 Gate

用户已批准首个 CATIA 黄金基线及公开分发、显式 STEP writer mode 2 /
`1e-7 mm`、四层软件回归阈值和 request v2 适用性。阶段 2 的几何路线、输入保持、
尖/钝拓扑、保存重开、声明重建、代表 CATIA 对照与数值契约均具备可复查证据，
因此阶段 2 GO。

以下内容不是阶段 2 遗留失败，而是后续实施边界：ADR-0006 的固定源码闭包尚待
阶段 3 vendoring 与分发测试；连续 Hausdorff/曲率上界不属于当前契约；产品级
Adapter、暂存发布、manifest、失败快照与 CLI 集成均按阶段 3/4 实现。
