# FreeCAD STEP precision 与 CATIA v2 对照提案（2026-09-16）

> **状态：已批准。** 2026-09-16，用户批准 CATIA STEP 作为首个黄金基线并允许
> 随公开测试夹具分发；在理解各层语义后，又批准 STEP writer 设置、分层软件回归
> 阈值和 request v2 适用性。它们是内部 preview 的软件回归契约，不是制造公差。

## 结论摘要

- 建议固定 FreeCAD 1.1.3 / OCCT 7.8.1，并显式设置 STEP `AP242DIS`、`MM`、
  `write.surfacecurve.mode=1`、`write.precision.mode=2` 和
  `write.precision.val=1e-7 mm`。这使当前隐式平均 BRep 容差的结果变成确定性会话
  配置，不读取或修改用户 GUI 偏好。
- `1e-7 mm`、平均 BRep 容差和 `1e-6 mm` 三次导出都得到相同实体属性与有限曲面
  距离；只有 STEP 声明的 uncertainty 和文件摘要变化。因此选择 `1e-7 mm` 是固定
  当前已验证语义，不是声称更小 writer 数值会提升 Gordon 几何精度。
- request v2 的 89 截面 Gordon 模型重新对比既有 CATIA 候选后，全局双向 400 点
  曲面最大值为 `0.357179 mm`，完整固定截面最大值为 `0.385172 mm`；与 2026-09-15
  人工接受的约 `0.382 mm` 三维差异属于同一量级。
- 建议把算法保持、原生→STEP、仿射一致性和跨后端黄金回归分成四层门禁，避免用
  较宽的跨后端阈值掩盖输入保持或 STEP 往返回归。

## 固定环境与输入身份

| 项目 | 值 |
| --- | --- |
| FreeCAD | 1.1.3，commit `145529fe741292ff0b3977a01195bf0247425794` |
| OCCT | 7.8.1 |
| Gordon 算法 | `curveswb-gordon-builder-explicit-parameters/v1` |
| CurvesWB | 0.6.81，commit `e4972f761d126901d13b3a72be64eb14f7d51c92` |
| v2 request SHA-256 | `060cc2052bc137d21b6648e73b07b377210b62173e6c37f8ff23190939feaeb6` |
| Gordon FCStd SHA-256 | `4cf9b148e526cff82e8625377230a5d565eeef228122411e7329bf78f11501d0` |
| CATIA STEP SHA-256 | `d9ef236cb71e2765c69badec9cc7506b4744bb5d133208dc5cc66a9988824db9` |
| 对照 JSON SHA-256 | `79439bbce75241c00c8000c114039d6799663c2a841204b23ce1037ad3fca989` |

CATIA STEP 是按用户授权在 CATIA P3 V5-6R2020 中从仓库已审计输入生成的基线，
生成过程见[CATIA 候选记录](catia-baseline-2026-09-07.md)，输入来源与授权边界见
[真实示例数据审计](../example-data-audit.md)。2026-09-16 用户已明确批准该摘要
作为首个黄金基线且允许公开分发。当前文件仍位于忽略目录；入库前须清理 STEP
头中的本机路径元数据、复核几何未变并记录清理后新摘要。

## STEP writer 依据与探针

OCCT 7.8.1 官方 STEP 指南定义 `write.precision.mode`：`-1/0/1` 分别取 BRep
最小/平均/最大容差，`2` 使用 `write.precision.val` 的会话值，并把相应 uncertainty
写入 STEP。FreeCAD 1.1.3 的 STEP 设置实现把首选项映射到这些 OCCT static
parameters；阶段 3 Runner 应直接使用子进程内的 `Part.setStaticValue`，不能读取或
写入用户首选项。依据见 [OCCT 7.8.1 STEP guide](https://github.com/Open-Cascade-SAS/OCCT/blob/V7_8_1/dox/user_guides/step/step.md)
与 [FreeCAD 1.1.3 STEP settings source](https://github.com/FreeCAD/FreeCAD/blob/145529fe741292ff0b3977a01195bf0247425794/src/Mod/Part/App/STEP/ImportExportSettings.cpp)。

同一 89 截面 FCStd 的只读探针结果：

| writer 设置 | STEP uncertainty | bytes | native→STEP max | STEP→native max | STEP volume |
| --- | ---: | ---: | ---: | ---: | ---: |
| mode 0，平均 BRep 容差 | `1e-7 mm` | 7,010,685 | `6.56e-12 mm` | `1.87e-11 mm` | 1,308,847.159658664 mm³ |
| mode 2，`1e-7 mm` | `1e-7 mm` | 7,010,685 | `6.56e-12 mm` | `1.87e-11 mm` | 同左 |
| mode 2，`1e-6 mm` | `1e-6 mm` | 7,010,685 | `6.56e-12 mm` | `1.87e-11 mm` | 同左 |

三项均以 AP242 声明重开为一个有效 solid，有限曲面样本和 mass properties 逐值
相同。原生 FCStd 体积为 1,308,847.159659139 mm³，mode 2 / `1e-7 mm` 的相对体积
差约 `-3.63e-13`，质心最大分量差约 `2.37e-10 mm`。探针脚本是
[`step_precision_probe.py`](../../scripts/freecad_gordon_prototype/step_precision_probe.py)；
完整本机结果保存在忽略目录
`output/gordon-clean-rebuild-20260915/step-precision-probe-100/`。

## request v2 与 CATIA 候选差异

[`compare_catia.py`](../../scripts/freecad_gordon_prototype/compare_catia.py) 只读 v2
FCStd 与 CATIA STEP，先验证双方都是有效闭合单 solid，再报告 mass properties、
双向有限曲面样本和两个翼型切换区的固定 X 截面。结果不是连续 Hausdorff 上界，
也不是面积加权 RMS。

| 指标 | v2 实测 |
| --- | ---: |
| 体积相对 CATIA 差 | `+2.470493e-4`（`+323.269932 mm³`） |
| 质心最大分量差 | `0.0650718 mm` |
| 包围盒最大分量差 | `0.0303866 mm` |
| Gordon→CATIA 全局 400 点 max / RMS | `0.357179 / 0.041470 mm` |
| CATIA→Gordon 全局 400 点 max / RMS | `0.330519 / 0.027531 mm` |
| 第一切换区完整截面最大值 | `0.205053 mm` |
| 第二切换区完整截面最大值 | `0.385172 mm` |
| 固定截面极值点到完整对方曲面 | `0.381422 / 0.381260 mm` |

每个切换区测量 5% 网格并在网格峰值附近细化，共 46 个站位。第一切换区 5% 站位
在原平面及 `±1e-4/±1e-3 mm` 重试后，OCCT `section()` 仍只从 Gordon solid 返回
一条开边；若把 CATIA 点投影到残缺截面会产生约 `32.9 mm` 伪峰。探针不把它计入
固定截面最大值，并明确记录为 1 个不完整站位；该站位的有限样本投影到完整对方
三维曲面最大约 `0.04014 mm`。完整报告保存在忽略目录
`output/gordon-clean-rebuild-20260915/v2-catia-comparison-3/result.json`，文件为
117,639 bytes。

## 已批准的分层数值契约

下面是实现阶段 3/4 时的默认值。每层独立失败；跨后端门限不得覆盖前一层。

### 1. 算法完整性

- 原始输入点到插值 profile：有限样本最大 `≤ 1e-7 mm`；不允许删点、移动点或
  改变 TE→LE→TE 语义。
- profile→surface 与 guide→surface：各自最大值
  `≤ max(1e-7 mm, network bbox diagonal × 1e-5)`。
- 每张 Gordon 曲面内部 U/V knot 连续性至少 C2；跨面接缝只要求 C0，最终结果
  必须 valid、closed 且恰有一个 solid。

当前 89 截面案例的 profile、section hold、guide hold 最大分别约
`2.28e-13 / 8.64e-13 / 1.15e-13 mm`；比例 gate 为 `0.0072886 mm`。这个比例值只
捕获算法失真，不是对外几何公差。

### 2. 原生 FCStd → STEP 数据交换

| 指标 | 候选阈值 | 当前实测 |
| --- | ---: | ---: |
| STEP schema/unit/uncertainty | AP242DIS / MM / `1e-7 mm`，精确匹配 | 匹配 |
| 重开拓扑 | valid、1 solid | 通过 |
| 相对体积差 | `≤ 1e-8` | `3.63e-13` |
| 质心最大分量差 | `≤ 1e-6 mm` | `2.37e-10 mm` |
| 双向有限曲面样本 max | `≤ 1e-7 mm` | `1.87e-11 mm` |

### 3. 仿射一致性

对固定输入分别覆盖 scale `0.5/1/1.7/2.5`、正负旋转和正负平移，重建后的体积
与理论 `scale³` 比值相对残差候选阈值为 `≤ 1e-4`，质心相对理论仿射位置的最大
分量残差为 `≤ 0.05 mm`。当前最大实测分别约 `4.21e-5` 和 `0.0174 mm`。

### 4. 跨后端黄金回归

这些候选值只对当前 89 截面多尖代表案例有直接证据；阶段 4 必须逐案例写入
manifest，并用单尖、单钝、多尖、多钝和明显变换矩阵验证默认值是否可复用。

| 指标 | 候选阈值 | 当前实测 |
| --- | ---: | ---: |
| 相对体积差 | `≤ 5e-4` | `2.47e-4` |
| 质心最大分量差 | `≤ 0.10 mm` | `0.0651 mm` |
| 包围盒最大分量差 | `≤ 0.05 mm` | `0.0304 mm` |
| 双向全局有限曲面 max | 每方向 `≤ 0.45 mm` | `0.3572 / 0.3305 mm` |
| 双向全局有限曲面 RMS | 每方向 `≤ 0.06 mm` | `0.0415 / 0.0275 mm` |
| 完整固定截面 max | 每方向 `≤ 0.45 mm` | `0.3852 mm` |
| 完整固定截面 RMS | 每方向 `≤ 0.25 mm` | `0.1968 mm` |

固定截面工具必须记录计划站位、重试偏移、闭合性和覆盖率；不完整站位不得静默
进入或退出统计，必须改用同站位的双向完整曲面距离作诊断。全局三维曲面指标是
强制主 gate，固定截面是定位性附加 gate。`0.45 mm` 只是把当前已人工接受的
`0.385172 mm` 峰值向上取整并留约 16.8% 回归余量；它没有制造学含义，不能在
测试失败时由实现者自行放宽。

## 批准与后续动作

阶段 2 所需批准已经完成：

1. [x] 2026-09-16：用户批准 CATIA STEP SHA-256 `d9ef236c…824db9` 作为首个
   黄金基线，并允许随公开测试夹具分发。
2. [x] 2026-09-16：用户在理解设置与分层语义后，批准显式 STEP writer
   `mode=2 / 1e-7 mm` 以及上面的四层软件回归阈值。
3. [x] 2026-09-16：用户把 2026-09-15 对代表案例的适用性批准延伸到 request v2
   和上述 FCStd 摘要；v2 已独立复现同量级差异。

阶段 2 因此 GO。阶段 3 把数值写入类型化配置与 Runner 契约，阶段 4 再写入
golden manifest 并用完整公开矩阵验证默认值；任何调整仍须有新证据和显式批准。
