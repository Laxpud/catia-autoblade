# 随 wheel 提供固定 CurvesWB 最小源码闭包

Status: accepted（2026-09-16）。本 ADR 确定 `v0.3.0` 目标交付方式；当前
`v0.2.0` wheel 不因此新增 FreeCAD 能力或第三方源码。

阶段 2 选定的 Gordon 路线依赖 CurvesWB `0.6.81` commit
`e4972f761d126901d13b3a72be64eb14f7d51c92`。实际导入闭包只有七个 Python
文件，但同时包含 Apache-2.0 与 LGPL-2.1-or-later 源码，并在 FreeCAD 子解释器
中传递依赖 NumPy。依赖用户通过 Addon Manager 安装会引入网络、用户配置和浮动
版本，不能满足离线内部 wheel、干净重建和逐字节追溯要求。

## 决策

- `v0.3.0` wheel 和 sdist 将随附上述 commit 的七文件**未修改源码闭包**，放在
  `autoblade` 包内专用 `_vendor` 资源目录；它不是 Host Python 的常规依赖，也不
  并入 `autoblade.core`。Host 只定位已安装资源并把只读绝对路径交给受控
  `FreeCADCmd` 子进程。
- 同一资源目录必须随附上游 LGPL-2.1-or-later 与 Apache-2.0 完整许可证文本，
  以及机器可读 manifest。manifest 至少记录上游名称、仓库 URL、版本、commit、
  获取日期、每个文件的相对路径/SHA-256/SPDX 标识、上游版权声明和本项目是否
  修改；未修改文件保留原 SPDX/版权头。
- Launcher 和 Child 都验证 manifest 与文件摘要；dependency fingerprint 写入
  result、FCStd `Traceability` 和发布验证记录。升级 CurvesWB 必须显式更新
  manifest、重新审计许可证和导入闭包，并重跑完整 FreeCAD 黄金矩阵，不能由
  Addon Manager 或用户目录静默替换。
- 默认认证模式只运行随 wheel 固定的闭包。为保留源代码替换、修改和调试能力，
  阶段 3 另提供显式 developer override：接受本地源码目录、记录实际逐文件摘要并
  把结果标记为 `unverified_custom_dependency`。该模式不得通过 release/golden
  gate，也不得伪装成固定依赖结果；普通 `create` 不做隐式依赖发现。
- FreeCAD `doctor` 和安装 smoke 必须验证固定 FreeCAD 版本能导入闭包与 NumPy；
  NumPy 属于 CAD 子解释器能力，不加入 Host wheel 的 Python 依赖。当前闭包不导入
  SciPy，不因完整 CurvesWB `package.xml` 的工作台级依赖声明而扩大产品依赖面。
- 分发校验必须同时断言源码文件、双许可证文本、manifest 和摘要存在，且 sdist
  能重建同一 wheel 内容。项目自有代码继续按项目许可证分发，第三方文件保持各自
  许可证和归属；首次对外或跨组织分发前仍须由责任人完成许可证合规复核。

## Considered Options

- **要求用户安装完整 CurvesWB/Add-on。** 安装简单，但版本与用户状态不可控，
  离线重建失败时也无法证明实际运行源码，因此拒绝。
- **发布独立 sidecar ZIP。** 许可证边界直观，但会把一个可运行版本拆成多个必须
  原子匹配的制品，并增加查找、缓存和升级失败面；内部单 wheel 目标下不采用。
- **随附整个 CurvesWB 工作台。** 会扩大体积、导入面、许可证审计和未使用依赖，
  与实际七文件闭包不相称。
- **把 TiGL/CurvesWB 算法重写进项目。** 可以减少运行依赖，但会引入新的数学实现
  和精度风险，现有 Gordon 验证不能直接继承；仅在未来无法满足分发要求时重开。
- **只允许固定摘要，禁止任何替换。** 有利于认证结果，但不利于修改和调试第三方
  源码；改为默认固定、显式非认证 override 的双模式。

## Consequences

- wheel 会增加少量 Python 源码、许可证和 manifest，但不依赖网络、用户 FreeCAD
  配置或完整工作台，且重建输入、算法和实际字节都可追溯。
- 阶段 3 必须新增资源定位、developer override、依赖状态字段、doctor/smoke 和
  分发内容测试；在这些实现与许可证复核完成前，ADR 只确定目标，不构成发布许可。
- 对闭包中任一文件的本地补丁都必须保留上游声明、添加显著修改说明并使用新的
  dependency fingerprint；补丁结果需重新跑全部几何证据。
