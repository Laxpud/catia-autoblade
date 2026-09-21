# 首个公开黄金夹具与数值回归（2026-09-20）

阶段 4 的首个获批案例已整理为
[`multi-sharp-89`](../../tests/fixtures/golden/multi-sharp-89/manifest.json)：89 截面、
300/253/249 点三翼型、尖尾缘。完整黄金矩阵与 Linux CAD CI 尚未完成，本文
不把该案例外推为其他输入的基线批准，也不构成 `0.3.0` 发布证据。

## 基线身份与公开边界

原始输入和 CATIA 生成来源分别见[示例数据审计](../example-data-audit.md)与
[CATIA 基线批准](catia-baseline-2026-09-07.md)。夹具包含四份获批 CSV、CATIA
STEP、直接授权说明、manifest 和批准时的预计算指标；没有 CATPart、FCStd、
私有输入或本机日志。输入 CSV 与先前审计的包资源逐字节相同，使用 LF。

| 摘要对象 | SHA-256 |
| --- | --- |
| 获批原始 STEP | `d9ef236cb71e2765c69badec9cc7506b4744bb5d133208dc5cc66a9988824db9` |
| 公开清理后 STEP | `0eb34e4a933a395df21e70535197f7ac352e75a9a2cbec9050b38827042dafe0` |
| 两者相同的 DATA 段 | `2a057c92f8f01e3b975135786bcadf4a11021da36cac9d83319e9bd7914d657e` |

清理仅把 HEADER/FILE_NAME 的 Windows 本地路径替换为 `catia.stp`，原始 CRLF
和 DATA 实体字节全部保留。真实 FreeCAD 1.1.3 / OCCT 7.8.1 分别重开清理前后
STEP，双方均为有效闭合单实体，体积、包围盒和质心逐值相同。清理后的摘要是
获批字节的可验证元数据派生，不冒充原始批准摘要。

`.gitignore` 和 Hatch 排除规则只对这个确切 STEP 路径开例外；`.gitattributes`
阻止 STEP 换行转换。夹具进入 sdist，保持在 wheel 外。分发校验从实际归档验证
全部夹具摘要，拒绝未列出的文件和相邻 CAD 产物。

## 回归契约与复现

以下记录 2026-09-20 的历史阈值验收。2026-09-21 用户改为标准测量报告与
人类可用性判断，当前 manifest 已迁移为 v2；现行命令语义见
[标准几何误差报告](../geometry-measurement-reports.md)。原始几何与历史测量值不变。

在已安装项目及 Flatpak FreeCAD 1.1.3 的 Linux 环境，从源码根目录显式运行：

```sh
python -m scripts.golden.run --output output/golden-new
```

输出目录必须不存在。工具在启动 CAD 前校验夹具摘要与输入闭合，再使用产品
FreeCAD backend、固定依赖闭包和独立配置生成 FCStd/STEP；随后由第二个独占
FreeCADCmd 重开、测量并判定。两进程各有默认 900 秒 timeout，可显式覆盖。
输出包括 `build.log`、`measure.log`、`result.json`、`summary.json` 和生成制品。
黄金夹具只读，工具没有自动更新基线或放宽阈值的选项。

首次清理的原始字节审计可额外指定 `--audit-original /path/to/approved.stp`。
此选项先核对原始批准摘要，再比较 DATA 和重开属性；日常回归不依赖原始文件、
本机历史目录、CATIA 许可证或 Windows 会话。

本次落实的门禁来自[已批准的分层数值契约](freecad-precision-proposal-2026-09-16.md)：

- 产品 Runner 继续执行输入/profile/guide 保持、C2 内部 knot、有效闭合单 solid
  和 STEP writer 的既有门禁。
- 原生→STEP 独立检查相对体积、质心和双向曲面距离；较宽的跨后端阈值不能
  覆盖交换层失败。
- 跨后端检查相对体积、质心、包围盒、双向曲面最大/RMS 和固定站位最大/RMS。
  不比较二进制、面数、边数或拓扑编号。
- 全局每方向取 400 个固定 `0.1 mm` tessellation 顶点，投影到对方裁剪曲面。
  它是有限采样证据，不是连续 Hausdorff 上界；RMS 按点计权，不按面积计权。
- 固定 2026-09-16 已测的 46 个站位，截面每方向最多 240 点。按 manifest 的
  `0 / ±1e-4 / ±1e-3 mm` 偏移重试，保存闭合性、偏移与覆盖率。新出现的提取
  缺口直接失败；已知 `X=310.30718165 mm` 缺口必须保留原始平面的双向样本到
  完整对方曲面的距离诊断，不把残缺截面产生的伪峰混入截面统计。

数值阈值逐项保存在 manifest，只覆盖已批准的代表案例。仿射一致性完整矩阵、
其余案例的基线和阈值批准仍待后续工作；不得把当前一个 manifest 当成通用
制造公差或完整矩阵默认值已被验证的证据。

## 本次真实结果

| 指标 | 实测 | 已批准门限 |
| --- | ---: | ---: |
| 原生→STEP 相对体积差 | `3.62821e-13` | `1e-8` |
| 原生→STEP 质心最大分量差 | `2.37094e-10 mm` | `1e-6 mm` |
| 原生↔STEP 曲面最大值 | `1.97291e-11 mm` | `1e-7 mm` |
| FreeCAD/CATIA 相对体积差 | `2.470493e-4` | `5e-4` |
| 质心最大分量差 | `0.0650718 mm` | `0.10 mm` |
| 包围盒最大分量差 | `0.0303866 mm` | `0.05 mm` |
| FreeCAD→CATIA 曲面 max / RMS | `0.357179 / 0.0414702 mm` | `0.45 / 0.06 mm` |
| CATIA→FreeCAD 曲面 max / RMS | `0.330519 / 0.0275312 mm` | `0.45 / 0.06 mm` |
| 完整固定截面 max / RMS 峰值 | `0.385172 / 0.196752 mm` | `0.45 / 0.25 mm` |

46 个站位全部执行，45 个取得完整闭合截面；唯一缺口与批准记录相同，原始站位
的完整曲面诊断最大 `0.0401588 mm`。黄金、原生和 STEP 均为有效闭合单实体。
新运行复现了批准时的跨后端数值，没有调整门限。

首次运行的建模耗时约 `391.337 s`，建模 Child 峰值 RSS `276100 KiB`；测量
耗时约 `307.949 s`、峰值 RSS `491700 KiB`。性能记录不作为新的 SLA。
完整本机证据位于 `output/golden-20260920-run2/`。

另从独立 sdist 解包、在全新 CPython 3.14.4 环境安装非 editable wheel，再运行
同一命令，不提供原始 STEP，也不读取历史产物。实体属性、交换层、全局曲面和
46 个站位报告与首次运行逐值一致，全部门禁通过。此次建模约 `384.207 s`，
Child 峰值 RSS `275296 KiB`；测量约 `305.875 s`、峰值 RSS `563444 KiB`。
FreeCAD 实例 before/after 均为 `[]`；临时源码副本与虚拟环境已清理，制品、
日志、摘要与 provenance 保留在 `output/golden-clean-source-20260920/`。

| 独立复现对象 | SHA-256 |
| --- | --- |
| 输入 wheel | `b0f444e8243a7d9f181944934b11666073fb8529ee554d5b53a63d0fecfcc763` |
| 输入 sdist | `2a8a082b738c1efd29733c378061d4024c0290528f63e98f0017e4598b616482` |
| 黄金 manifest | `4989983a0c53ce65a5cf11617698f95a33af0df59d526fb0f9c9922421427d62` |
| 完整几何结果 JSON | `5426529dfdf3201225c525cb891e37bb7b935e8df6a0fc8cfcbc2fefba7f39c3` |

源码归档中的四个黄金脚本已与工作区逐字节核对，`provenance.json` 记录其摘要
及实际导入的 `site-packages` 路径。上述 sdist 早于本文收尾更新，但包含完整
测量实现和公开夹具；后续文档更新不冒充该输入归档的原始字节。

## 双平台与制品验证

- Linux CPython 3.14.4 通过 `bash scripts/check-linux.sh`：231 项 pytest、Ruff、
  wheel/sdist 构建、非 editable 安装 smoke 和实际分发校验；日志为
  `output/golden-check-linux-20260920.log`。
- Windows CPython 3.14.7 在 `%LOCALAPPDATA%\AutoBlade-checks\golden-20260920`
  的本地副本执行 `pwsh -File scripts/check.ps1`，同样 231 项测试及完整检查
  通过。成功副本、虚拟环境和临时产物已清理；日志、摘要与检查制品保留在同一
  父目录的 `records\golden-20260920\`，日志副本在
  `output/golden-windows-records-20260920/`。
- 两个平台构建的 wheel 均只有 72 个文件且不含黄金夹具；检查时的 sdist 包含
  185 个文件，夹具及脚本齐备，归档内 STEP 摘要均与 manifest 匹配。

本次没有执行新的真实 CATIA 生成、批准其他黄金文件、提交 Git 或发布版本。
上述检查针对开发工作区；本文与 TODO 收尾晚于检查构建，不称为干净标签制品。
