# 候选矩阵测量与交付（2026-09-21）

本轮完成 6 组 CATIA / FreeCAD 候选及 1 组 FreeCAD 性能案例。用户明确要求：
“和 catia 的对比，只测量结果，判断交给我”，最初要求统一放入 win11 目录，
随后明确改为保存在当前项目目录，后续不再复制到 win11。
因此本记录及检查包只提供实测值，不作几何适用性裁决，不自动批准新的公开
黄金基线或逐案例公差。阶段 4 于 2026-09-22 完成远程验收，阶段 5 未启动。

## 当前项目检查入口

完整公开矩阵的模型与标准报告保存在项目目录
`output/AutoBlade-public-matrix-reproduction-20260921/`，打开其中 `index.html`
即可检查。原始六组人工检查模型在 `output/AutoBlade-review-20260921/`，
对应标准报告与人工结论在 `output/AutoBlade-standard-reports-20260921/`。
这些目录均为本机交付产物，不进入源码提交。

## 首次 win11 检查包记录

Windows 本地目录：`C:\Users\Laxpud\Desktop\AutoBlade-review-20260921`。
打开 `index.html` 可查看测量汇总与模型入口；`measurements.csv` 保存更完整的
双向 max/RMS，`summary.json` 和 `affine.json` 可直接读取数值。

每个对照案例含 `CATIA/blade.CATPart`、`CATIA/blade.stp`、
`FreeCAD/blade.FCStd`、`FreeCAD/blade.stp`、输入 CSV、许可、生成身份和完整
`measurements.json`。建议把同一案例的两个 STEP 叠加检查；原生文件用于各自
特征树检查。`dense-1000` 只有 FreeCAD 文件，不含 CATIA 对照。

交付合计 6 个 CATPart、7 个 FCStd、13 个 STEP；复制后核验全部 73 个内容
文件，另有一个 `SHA256SUMS.json`。清单 SHA-256：
`95753f00239cb5f05e883d4074a3b2ce833299e6483d8cdd63d2bbb2646bad8c`。
本机同字节副本在 `output/AutoBlade-review-20260921/`，交付记录在
`output/golden-matrix-windows-20260921/delivery.json`。

## 输入及生成环境

合成翼型由项目直接定义，使用项目 MIT 许可；不是 NACA 或第三方实测翼型，
也不借用未核实再分发许可的库数据。归一化轮廓位于 YZ 平面，X=0，点序为
TE→LE→TE。弦向坐标采用余弦分布，半厚度和中线为：

```text
h(y) = amplitude * sqrt(y) * (1-y) + gap * y / 2
c(y) = camber * y * (1-y)
z(y) = c(y) ± h(y),  y ∈ [0, 1]
```

尖尾缘保持首尾坐标精确相等，钝尾缘保持显式间隙；CSV 不经过隐式重采样。
五个截面跨越 0–0.5 m，弦长依次为 0.12、0.115、0.105、0.095、0.085 m，
截面扭角依次为 8°、5°、2°、−1°、−4°，另有明确的 Y/Z 平移。
完整配方与输入摘要保存在各案例的 `generation.json`。

| 案例 | 输入特点 |
| --- | --- |
| `single-sharp` | 121 点，amplitude=0.156，camber=0，gap=0 |
| `single-blunt` | 121 点，amplitude=0.156，camber=0，gap=0.004 |
| `multi-blunt` | 121/153/181 点；amplitude=0.156/0.13/0.104，camber=0/0.015/0.025，gap=0.004/0.003/0.002；截面引用 1/1/2/3/3 |
| `affine-05` | single-sharp 整体缩放 0.5，绕 X 轴 −23°，平移 (−0.05, 0.04, −0.02) m |
| `affine-17` | 整体缩放 1.7，绕 X 轴 37°，平移 (0.2, −0.1, 0.3) m |
| `affine-25` | 整体缩放 2.5，绕 X 轴 −41°，平移 (−0.1, 0.2, −0.05) m |
| `dense-1000` | 1000 点尖尾缘，五截面，仅 FreeCAD 性能记录 |

CATIA 在 Windows 11 build 26200 的已登录 Session 1 中显式运行，CNEXT 文件
版本 `5.30.0.19235`。工作区先复制到 Windows 本地临时目录，再从非 editable
wheel 导入，六案均生成 CATPart/STEP，并检查 Loft、闭合实体和导引特征。
CATIA 生成时间为 10:11:26–10:14:24，CNEXT before/after 均为空。

FreeCAD 使用 Linux Flatpak 1.1.3 / OCCT 7.8.1，也从非 editable wheel 调用
后端；每案原生模型和 STEP 均重开，记录 valid、closed、单 solid 和请求摘要。
FreeCAD writer 显式使用 AP242DIS、precision mode 2 / `1e-7 mm`、
surfacecurve mode 1。建模和测量的 FreeCAD instances before/after 均为空。

CATIA 所用 wheel SHA-256 为
`14cf1131f90e33b1a826253f806bfc92ced3d890416594f838ccc33811c335fd`；
源码基于 `8e47cdc8d24917369da069d7d695973b86360470` 的未提交工作区，不能把
该 commit 单独当作本次完整源码身份。产品版本仍为 `0.2.0`。

## 实测值及方法

以下比较 FreeCAD 原生实体与 CATIA STEP。体积列为
`abs(V_FreeCAD / V_CATIA - 1) × 100%`；质心和包围盒列是坐标分量绝对差的
最大值。曲面、截面最大值各取两个投影方向中的最大值，不是单向数据。

| 案例 | 体积读数差 % | 质心分量差 mm | 包围盒分量差 mm | 曲面双向最大 mm | 截面双向最大 mm | 完整站位 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single-sharp | 0.022118801 | 0.073619163 | 0.003887264 | 0.035983388 | 0.048144330 | 79/79 |
| single-blunt | 6.772684229 | 1.608173190 | 0.015904967 | 0.035986684 | 0.048154970 | 79/79 |
| multi-blunt | 4.080524703 | 3.697998604 | 0.106046644 | 0.284459917 | 0.301196956 | 79/79 |
| affine-05 | 0.022322136 | 0.036674250 | 0.070080136 | 0.017413661 | 0.024033184 | 79/79 |
| affine-17 | 0.022356127 | 0.125275770 | 0.393044224 | 0.060895002 | 0.081940005 | 79/79 |
| affine-25 | 0.022523225 | 0.184517466 | 0.449510635 | 0.087579902 | 0.120499912 | 79/79 |

全局采样使用 `tessellate(0.1)` 的网格顶点，每方向确定性选取最多 400 点，
投影到对方裁剪曲面集合。有限采样最大值不是连续 Hausdorff 上界，RMS 按点
计权而非按面积计权。每个相邻输入截面区间预先固定 5%–95% 的 19 个站位，
再加三个内部输入站位，共 79 个；每方向最多 240 个截面样本，完整性与
`0, ±0.0001, ±0.001 mm` 重试记录均保留，没有不完整站位例外。

体积及质心沿用 OCCT 默认积分读数，包围盒沿用 `Shape.BoundBox`。钝尾缘的
体积读数差与曲面采样差同时如表记录，原因尚未通过独立积分收敛测量确认，
不能把默认体积读数直接当成高精度裁判。
[FreeCAD 的 Volume 实现](https://github.com/FreeCAD/FreeCAD/blob/145529fe741292ff0b3977a01195bf0247425794/src/Mod/Part/App/TopoShapePyImp.cpp)
在属性入口调用 `BRepGProp::VolumeProperties(shape, props)`，未指定积分精度。
本轮没有改换测量算法或据此修改模型。

三组仿射案例分别对每个后端自身的基准结果计算 scale³ 体积关系及变换后的
质心残差；FreeCAD 的最大相对体积残差为 `3.667068e-6`、最大质心分量残差
`0.000225743 mm`，CATIA 分别为 `1.451380e-6` 和 `0.000600888 mm`。
逐案例数据见检查包的 `affine.json`，没有阈值裁决。

初测曾沿用首个公开夹具的阈值生成内部诊断。用户明确要求仅测量后，候选
流程停止产生自动裁决；交付工具只提取原报告的测量字段，原始报告留存，
其 SHA-256 写入 `generation.json`，所有数值和模型字节保持不变。初次交付时
`multi-sharp-89` 仍执行旧契约；用户随后明确长期策略后，它也迁移为仅测量、
人工判断，旧阈值仅留作历史背景，详见下方人工检查结论。

## 性能、身份与验证

耗时为后端 build 调用的墙钟时间，峰值内存来自 FreeCAD 子进程；不含后续
跨后端测量时间。这是单次本机记录，不作吞吐承诺。

| 案例 | build 秒 | peak RSS KiB |
| --- | ---: | ---: |
| single-sharp | 3.581 | 128004 |
| single-blunt | 3.975 | 125840 |
| multi-blunt | 4.723 | 129428 |
| affine-05 | 3.252 | 126100 |
| affine-17 | 4.048 | 126448 |
| affine-25 | 3.936 | 126028 |
| dense-1000 | 8.936 | 140052 |

本次 CATIA STEP 原始摘要（仅标识候选，不表示公开分发批准）：

| 案例 | SHA-256 |
| --- | --- |
| single-sharp | `35174a8ad370e010c5fbef38e0cc0734fc9048b05127954e89754d55bcf909b5` |
| single-blunt | `4f6f26142e9f4c282cb32b2a79952cfd221aedb44635b23c0fa1b1950cec985e` |
| multi-blunt | `7b875787f74482afd74822cbad4d3bd535e3c553d76e03cfcbd09b24a024ab65` |
| affine-05 | `91c4e426325b7406671630fcaf17e2fb81759dac84add53fc58359abd56204f2` |
| affine-17 | `d5b45e5f0f93bac5a0aadd8ca2c947bc661ab77bffcd8f059c709793d1bf3f9b` |
| affine-25 | `2904b30d67be27331ba125dee86f5e4d148144dcf7c568130fd2566d52b30f7c` |

Linux `bash scripts/check-linux.sh` 与 Windows `pwsh -File scripts/check.ps1`
均完成 249 项测试、Ruff、构建、非 editable wheel smoke 和分发内容校验。
测试只用 fake/mock CAD；模型生成和测量均由单独的显式命令完成。
Windows 验证副本、虚拟环境、临时产物和一次性桌面任务均已清理，保留日志、
摘要及用户检查包。未执行 git commit。

本机证据目录：

- `output/golden-matrix-20260921/`：候选配方、输入和 CATIA 原始文件。
- `output/golden-matrix-freecad-20260921/`：FreeCAD 原始文件、建模日志和性能。
- `output/golden-matrix-review-20260921/`：原始逐站位测量。
- `output/golden-matrix-windows-20260921/`：环境、进程、清理和交付记录。
- `output/golden-matrix-check-{linux,windows}-delivery-20260921.log`：初次交付检查。

## 复现命令

使用新的输出目录；先安装本次 wheel，再从包含 `scripts/` 的源码目录运行。
所有命令都拒绝覆盖已有模型。`catia` 必须在已登录的 win11 桌面会话中运行，
输入、产物复制时保留字节并校验摘要。

```bash
python -m scripts.golden.candidates prepare --output output/matrix-new
python -m scripts.golden.candidates catia --matrix output/matrix-new
python -m scripts.golden.candidates freecad --matrix output/matrix-new --output output/models-new
python -m scripts.golden.candidates compare --matrix output/matrix-new --models output/models-new --output output/measurements-new
python -m scripts.golden.review --matrix output/matrix-new --models output/models-new --measurements output/measurements-new --output output/review-new
```

初次交付时只生成候选；下方记录用户后续人工结论与独立公开基线授权。
本次工作不扩大已发布支持声明。

## 人工检查结论

2026-09-21 用户已打开 win11 检查包并手动对比，明确表示：

> 我已经能够看到 win11 下的文件并且进行了手动对比，肉眼看不出来区别。
> 对于这类建模，我认为肉眼无法分辨的误差，在实际计算时也可以忽略不计。
> 以后只对模型测量，形成标准误差报告，但实际是否可用一律通过人类来判断。

本次结论对应上述检查包摘要和其中 6 组 CATIA / FreeCAD 对照，记录为用户对
当前建模与计算用途的人工接受。它不是通过有限采样推导出的通用误差定理，
不自动覆盖未来制品。公开分发由下方另一项明确授权覆盖。
后续标准报告与人类决定的长期边界已记录在
[ADR-0007](../adr/0007-measure-geometry-and-defer-usability-to-humans.md)。

标准报告已追加到原检查目录的 `standard-reports/`，包含六组
`error-report.md`、`error-report.csv`、`result.json` 和独立 `human-review.json`。
20 个内容文件复制校验完成，补充包 SHA256SUMS 摘要为
`6cfde1221066943c9557fa762c4020f6111b73ab87fcf4323f9043a416deb2e2`。
原始检查包中的模型字节保持不变。

## 公开测试基线授权

用户随后单独确认“批准这 6 组公开测试基线”，明确覆盖本页六组原创合成输入
与 CATIA STEP 随源码分发。公开副本已加入 `tests/fixtures/golden/`，分别含
许可/授权说明、输入、CATIA STEP、manifest v2 和原始测量参考；不进入 wheel。
每份 STEP 只将 HEADER/FILE_NAME 改为 `catia.stp`，与原始文件的 DATA 段
逐字节一致。源码归档的七个 STEP 例外逐项列出，没有开放通配 CAD 文件。

| 案例 | 公开 STEP SHA-256 |
| --- | --- |
| single-sharp | `82e542626826e0eee16624d122930b74cb017e957987825c3211b89b72ed079d` |
| single-blunt | `f6793575bdb1ebe5a608408cfbb7cf1a48ab16e2fe8039837fea49903f74499c` |
| multi-blunt | `25ffaa0faff664ee5be306979e063e197ab8cf13f96b1abea7a94629cec47484` |
| affine-05 | `8d521fa2ed5f0dfcbfe631bd38ab3c54232459f49dc46e5fe493ca3df625e33c` |
| affine-17 | `e6761a86279364ae783d82281bce29a096ac0712839573ba329cf35dbf75e350` |
| affine-25 | `6516cdfabebae1480a13a351305c78406c427bc86563ef1601427b8d0c8a3cff` |

## 完整公开矩阵复现与最终检查

公开基线加入后，使用独立非 editable wheel 完成完整 CI 测量脚本：

```bash
bash scripts/check-freecad-measurements.sh output/freecad-ci-public-matrix-20260921
```

七组公开参考均生成 `result.json`、Markdown 和 CSV 标准报告，状态为
`measured`，可用性始终标记 `requires_human_judgment`。七组原生模型及自身
STEP 均有效、闭合且为单 solid；摘要与报告逐份一致。六组新基线清理前后
DATA 字节完全一致，实际重开测得的 CATIA 体积、质心和包围盒等属性也逐值
相等。自动检查只确认采集和产物完整性，不以偏差大小作适用性判断。

| 公开案例 | 建模 s | 建模峰值 RSS KiB | 测量 s | 测量峰值 RSS KiB | 完整 / 预定截面 |
| --- | ---: | ---: | ---: | ---: | ---: |
| affine-05 | 1.261 | 126508 | 35.410 | 167556 | 79 / 79 |
| affine-17 | 1.278 | 126172 | 38.836 | 167500 | 79 / 79 |
| affine-25 | 1.278 | 126512 | 36.551 | 166896 | 79 / 79 |
| multi-blunt | 4.937 | 128452 | 57.861 | 345564 | 79 / 79 |
| multi-sharp-89 | 398.317 | 276588 | 317.803 | 549624 | 45 / 46 |
| single-blunt | 1.598 | 126228 | 37.325 | 221896 | 79 / 79 |
| single-sharp | 1.279 | 127808 | 35.440 | 155800 | 79 / 79 |

89 截面案例仍在 `X=310.30718165 mm` 留有原先的闭合截面提取缺口；全部
46 条站位记录保留，缺口的曲面诊断不混入完整截面统计。表中耗时和峰值内存
为单次本机测量，不是性能承诺。

同一脚本还重新生成全部七个合成性能案例；1000 点案例建模 `8.759 s`、峰值
RSS `139908 KiB`。所有公开测量与合成建模的 FreeCAD 实例 before/after 均为
空，脚本临时 venv 已删除。之前一次本机尝试在模型测量完成后遇到 shell
文件执行期间被修改而中断，其日志保留在 `output/freecad-ci-human-review-20260921.log`；
上述最终完整运行使用固定脚本，所有预定产物与最后的性能汇总均已核验。

完整复现包已追加到同一个 Windows 检查目录的 `public-matrix-reproduction/`，
可打开其中 `index.html` 查看各案报告与 STEP。包含七组参考与本次 FreeCAD
模型、输入、报告，以及 1000 点性能模型，共 95 个内容文件，另附摘要清单：
`bddb5c4a472099f8c44cad3b71e91e808cae324a7f7be65758ff09beb79a6339`。
原检查包及其人工结论保持原样；本次重新生成文件仍须由人类决定用途。

最终 Linux 与 Windows 完整检查均通过 262 项测试、Ruff、构建、非 editable
wheel smoke 和分发校验。另从独立 sdist 解包检查了全部七份夹具、输入规划与
许可/摘要契约。Windows 本地验证副本与临时源码/环境已清理，日志及交付物保留。

本机最终证据：

- `output/freecad-ci-public-matrix-20260921/`：环境身份、模型、标准报告、性能和
  `completion-audit.json`；完整执行日志在同名 `.log`。
- `output/public-matrix-check-{linux,windows}-20260921.log`：双平台最终检查。
- `output/public-matrix-clean-source-20260921/preflight.json` 与 `preflight.log`：
  独立源码归档校验，解包的临时源码已删除。
- `output/public-matrix-cleanup-20260921.json`：本机临时环境清理记录。
- `output/golden-matrix-windows-20260921/public-matrix-reproduction-delivery.json`：
  win11 追加包逐文件校验记录。

以上本机验证完成时，Linux non-blocking workflow 尚未推送和远程执行。
随后经用户明确授权推送、提交本轮修复及配置 required 检查，继续下方远程验收。

## 远程 CI 验收

推送 `f5bdebc` 后，GitHub Linux 常规检查通过，Windows 出现 7 项失败，根因
均为干净 checkout 的 `core.autocrlf` 改写 CurvesWB manifest/源码/许可证字节。
之前将 Linux 工作区复制到 Windows 的验证没有触发这条路径。`ec7e8b7` 在
`.gitattributes` 中固定该闭包为 LF，保留既有 SHA-256 契约，没有放宽认证。

同一修复将路径选择移到 job 内部，确保纯文档变更也返回稳定的
`FreeCAD measurement integrity` 状态；PR 比较 merge base 以来的完整差异，
push 比较前后完整树，删除/重命名也能触发测量，未知历史执行完整矩阵。
每周与手动运行始终执行七组公开案例及七组合成性能案例。

修复后的 [Windows/Linux 完整检查](https://github.com/Laxpud/catia-autoblade/actions/runs/35600989620)
均通过 269 项测试、Ruff、wheel/sdist 构建、独立 wheel 安装 smoke 和分发校验；
本机 Linux 同样完成完整检查。Windows 直接使用 GitHub 干净 checkout，未再
复制工作区至 win11。日志、远程制品和核验结果统一保存在
`output/stage4-ci-20260921/`，不进入源码提交。

三个独立 `ubuntu-24.04` runner 均从干净 checkout 构建、安装非 editable wheel，
固定 Flatpak app/runtime commit、FreeCAD 1.1.3 / OCCT 7.8.1，实际安装、测量、
上传步骤全部成功。每轮七组公开案例均为 `measured`，另有七组合成性能模型。
下载后重新核验 manifest/模型摘要、实体属性、预定站位及 JSON→Markdown/CSV
逐字节重建；每轮 520 条站位记录完整，六组各 79/79 完整截面，89 截面案例
保持 45/46 及原有缺口。公开与合成任务的 FreeCAD 实例 before/after 均为空。

| GitHub run | 源码 | 触发 | 89 截面建模 / 测量 s | 建模 / 测量峰值 RSS KiB | 1000 点建模 s / RSS KiB |
| --- | --- | --- | ---: | ---: | ---: |
| [35600566121](https://github.com/Laxpud/catia-autoblade/actions/runs/35600566121) | `f5bdebc` | push | 493.412 / 302.149 | 278376 / 488296 | 12.640 / 141836 |
| [35600989648](https://github.com/Laxpud/catia-autoblade/actions/runs/35600989648) | `ec7e8b7` | push | 492.804 / 296.497 | 280508 / 491440 | 13.105 / 142236 |
| [35601008804](https://github.com/Laxpud/catia-autoblade/actions/runs/35601008804) | `ec7e8b7` | workflow_dispatch | 391.888 / 241.531 | 276728 / 489540 | 9.842 / 139940 |

典型 `single-sharp` 建模 1.777–2.368 s、峰值 RSS 126696–128672 KiB。
三轮覆盖一致，七案的跨后端曲面双向最大值范围均为
`0.017414–0.357179 mm`，最大值对应 `multi-sharp-89`；逐案完整数值保存在
下载报告中。自身 STEP 的曲面交换最大差范围为 `1.12e-12–5.34e-11 mm`。
这三次独立完整复现作为本阶段结束观察期的证据，不代表长期服务可靠性或
吞吐承诺；既定每周完整运行继续提供后续观察。人类对先前模型的结论保持其
原有制品和用途边界，本次 CI 不自动批准新模型。

2026-09-22，提交 `8a11c45` 移除 job 的 `continue-on-error`。随后通过 GitHub
API 实际配置并重新读取 `main` branch protection：required context 为
`FreeCAD measurement integrity`，来源 App ID `15368`（GitHub Actions），
`strict=true`、`enforce_admins=true`，未增加人工 PR review 数量要求。
因此后续变更通过检查后再合并，管理员同样不能绕过此 required 状态。
仅提交 YAML 不算配置完成；实际返回值保存在
`output/stage4-ci-20260921/branch-protection-applied.json`。

证据目录同时保留 `run-<id>.json`、`artifacts-<id>.json` 与各
`run-<id>/download-audit.json`；每份下载包含完整模型、数值报告、建模/测量日志
和 wheel。阶段 4 的完整矩阵、公开许可与摘要、人工结论、重复运行及 required
检查均已有可追溯证据，阶段 5 尚未启动。
