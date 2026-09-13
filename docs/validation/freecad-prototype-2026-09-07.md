# FreeCAD 阶段 2 原型实测：2026-09-07

后续进展：2026-09-08 已取得用户授权生成的 CATIA 候选对照，见
[生成与探索性比较](catia-baseline-2026-09-07.md)。以下保留本次原型运行时的事实，
其中“尚无 CATIA 对照”描述 2026-09-07 初次原型时的状态。

结论：公开输入上的原生模型机制初步可行；**阶段 2 尚未 GO**。缺少获许可
CATIA STEP 对照，且 89 截面多翼型的 STEP 往返体积差异需要继续定位，不能批准
precision 或工程公差，也不能进入完整 backend 集成。

## 环境与复现边界

- Linux x86_64，Flatpak `org.freecad.FreeCAD` stable 1.1.3。
- Flatpak commit：`c8bae9a419fcddf1f40c046b064be3b8b98144734b1828428f6a2a944312dd29`。
- FreeCAD：`1.1.3R44987`，源码 commit
  `145529fe741292ff0b3977a01195bf0247425794`。
- 原型和全部本机证据保存在忽略目录 `output/freecad-prototype-20260907/`，包括
  `prepare.py`、`runner.py`、`run.py`，以及每案例的 request/result JSON、独立
  user/system 配置、stdout、FCStd 和 STEP。此路径是本机证据，不是干净 checkout
  已可复现的黄金夹具；原型未进入正式 package，也未提交或创建分支。
- 本机复现入口：`.venv/bin/python output/freecad-prototype-20260907/prepare.py`，
  然后 `.venv/bin/python output/freecad-prototype-20260907/run.py`。
  后者显式启动真实 CAD，按顺序执行，失败停止，每案例 timeout 为 900 秒。
- 本轮只更新验证记录和计划，未修改产品源码、依赖或版本；未运行 Windows/CATIA
  或发布验收，不把本记录当作双平台检查证据。

原型源码 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| runner.py | `99097a23d68cd7c7e573acac7ca808d8b0b527f51f84b5b07d0993f6c128c3c1` |
| prepare.py | `e1ea926deafb932c50282df9de02a1de91be7e5c08c21ff8b9650f9c36e9a329` |
| run.py | `a7192bd6a172ad7f2fba9a6ba6d0afa4a9c1d33e97ee131b5af349a1e68d36c2` |

## 已验证机制

1. Host 使用既有 `build_blade_input_plan` 解析和闭合输入；固定 Runner 只读取
   `schema_version=1`、`length_unit=m` 的 JSON，不读取 CSV，不依赖 `__main__`
   判断。此协议是可丢弃原型，不是阶段 3 的生产级严格协议。
2. Parser 返回的点已转换到模型坐标 `y=-input_y+0.25`，不能再次转换；在离散
   模型 Y 最大点处分成 upper/lower 插值 B-spline，两支共享前缘。尖尾缘首尾
   相同，钝尾缘使用显式 LineSegment 闭合。未删点、移动点或重采样。
3. Sketch 局部 XY 映射到模型 YZ，弦长在边界转换为 mm，通过 Placement 实现
   X 轴旋转与三维平移。每截面验证恰有一个闭合 Wire。
4. `BladeSolid` 是 `Part::Loft`，`Solid=True`，链接全部原生
   `Sketcher::SketchObject`；前后缘仅为带 `ReferenceOnly=True` 的冻结参考
   Shape，不驱动 Loft。截面和参考设置隐藏、最终实体显示；尚未做 GUI 视觉验收。
5. 保存 FCStd，关闭并重开后调用 `recompute(None, True, True)` 强制重算，
   检查 Loft 类型与截面链接数量，并验证有效且恰有一个 solid。没有 FeaturePython
   或以静态 Shape 替代最终叶片。
6. 使用 `Import.export` 导出 AP242DIS，检查实际 `FILE_SCHEMA` 为
   `AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF`；所有文件都有
   `SI_UNIT(.MILLI.,.METRE.)`。STEP 用 `Part.read` 重开后均有效且恰有一个 solid。
7. 每案例启动独立 FreeCADCmd；运行前删除本次目录内的 user/system 配置，从全新
   配置验证。执行后进程查询未发现 FreeCADCmd 残留。没有连接或关闭用户 GUI。

导出探索中发现：`Part.export` 在本次探针中写出 AP214；仅在运行后期设置 STEP
`Scheme` 会出现配置缓存问题。最终原型在导入 Part/Import **之前**设置 AP242DIS，
再使用 `Import.export`，五个案例均从全新配置通过文件 schema 检查。此前失败
尝试已被最终运行覆盖，不作为通过证据。

配置隔离入口依据 [FreeCAD 官方启动配置文档](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Start_up_and_Configuration.md)
中的 `--user-cfg` 与 `--system-cfg`；具体导出行为以本机 1.1.3 实测为准。

## 最终一轮数据

耗时从 Runner 开始到验证结束，不含 Flatpak 启动时间；峰值 RSS 是 FreeCADCmd
进程 `resource.getrusage(RUSAGE_SELF).ru_maxrss`，不是整个进程树峰值。每个案例
只记录一轮，不构成性能 SLA。

| 案例 | 输入与截面数 | 耗时 s | 峰值 RSS KiB | FCStd 体积 mm³ | STEP 往返体积 mm³ |
| --- | --- | ---: | ---: | ---: | ---: |
| sharp | sc1095_sharp，blade_sections-1，26 | 0.508 | 135120 | 340777.360750306 | 340777.360750439 |
| blunt | sc1095，blade_sections-1，26 | 0.528 | 136592 | 346489.760768620 | 346489.760768077 |
| multi | 300/253/249 点，blade_sections-multi-airfoil，89 | 4.176 | 277808 | 1308277.647276194 | 1308440.484394318 |
| dense | airfoil1_sharp_dense_1000，blade_sections-1，26 | 2.816 | 196376 | 681675.726513999 | 681675.726518721 |
| transformed | sharp 全局旋转/缩放/平移，26 | 0.513 | 135668 | 1674239.173751934 | 1674239.173745930 |

明显变换案例对整片叶片绕 X 轴旋转 37°、缩放 1.7 倍，再平移
`(0.2,-0.1,0.3) m`。相对于 sharp 的解析预期：体积与 `1.7³` 倍基准体积之差
为 `0.000385682 mm³`，质心分量最大残差约 `1.133e-7 mm`。这些是测量结果，
不是已批准的公差。

## 未满足项与下一步

- multi 的 STEP 往返体积差为 `162.837118124 mm³`，相对差约 `0.0124467%`。
  其原因尚未定位；须区分数值积分差异、writer 设置和实际表面变化，补做包围盒、
  截面和表面偏差检查。不能仅以 `isValid()` 或“单 solid”宣布几何等价。
- 本轮使用隔离配置中的 writer 默认 precision，未调优或批准 precision 数值。
- 尚无用户或工程责任人确认的许可清晰 CATIA STEP 基线；现有输入授权不自动
  等于黄金基线批准，也未启动 CATIA 生成或批准基线。
- 尚未做 GUI 可见性检查、完整黄金矩阵、多钝、干净 checkout 重现或正式发布回归。
- 阶段 2 gate 保持未通过。先解决上述对照与测量问题，形成明确 GO 后才进入阶段 3。
