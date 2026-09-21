# 标准几何误差报告

自动化负责测量，模型在实际计算中的可用性由人类判断。长期规则由
[ADR-0007](adr/0007-measure-geometry-and-defer-usability-to-humans.md) 定义。

## 输出契约

显式 `python -m scripts.golden.run` 或 `scripts.golden.candidates compare`
为每个案例生成：

- `result.json`：`autoblade.geometry-measurement/v1` 完整数值与身份。
- `error-report.md`：人工可读摘要、测量局限和制品摘要。
- `error-report.csv`：带 layer、metric、direction、station_x_mm、unit 的数值表。
- 日志及实际 `.FCStd` / `.stp`，用于模型检查和问题复现。

`status=measured` 或 `measured_candidate` 仅表示测量采集成功，
`decision_policy=human_only`、`usability=requires_human_judgment` 始终明确
可用性需要人工判断。`measurement_error` 表示环境、计算或报告完整性错误。
FreeCAD 后端结果中的 `status=passed` 同样只表示构建和制品完整性检查完成，
不表示模型可用性；`measurements` 内另有相同的人工判断标记。

## 必须记录的数据

输入 manifest、请求和三份制品（FreeCAD 原生、自身 STEP、CATIA STEP）的
SHA-256，FreeCAD/OCCT 版本及明确的单位；JSON 字段中的 mm/mm³ 为测量单位，
CSV 输入的 m/deg 契约不变。相对体积差为绝对比值差，展示百分数时乘 100。

测量分成 `exchange`（原生与自身 STEP）和 `cross_backend`（原生与 CATIA
STEP），均记录体积、质心分量差、包围盒分量差和双向曲面 max/RMS。
`stations` 保留全部预定 X 站位、切面重试与完整性；完整截面用截面距离，
不完整截面单独保留曲面诊断。`coverage` 列出预定、已记录、完整数量和缺口。
遗漏整条站位记录或出现 NaN/Inf 是报告错误；数值较大不产生自动裁决。

体积/质心来自 OCCT 默认积分，未证明积分收敛；包围盒是默认算法结果。
曲面采样使用 manifest 固定 deflection 的网格顶点，投影至对方裁剪曲面；
max 是有限采样观察值而非连续 Hausdorff 上界，RMS 按点计权而非按面积计权。
改变采样方法时必须记录新方法身份，不能把不同方法的差异伪装成模型变化。

公开夹具 manifest 使用 `autoblade.golden/v2`；旧阈值保存在
`historical_tolerances`，不参与报告状态或退出码。公开 STEP 和原始参考测量
保持原字节，schema 迁移不重写几何。人工结论只覆盖其指定制品和用途。

## CI 与本机复现

```bash
bash scripts/check-freecad-measurements.sh output/freecad-measurements-new
```

脚本从独立非 editable wheel 运行已公开的全部参考案例，另生成单/多翼型和
1000 点合成性能模型，结束后清理临时 venv。它不连接 CATIA，不依赖私有候选。
固定环境身份在 `scripts/golden/ci-environment.json`，包括 FreeCAD 1.1.3 / OCCT
7.8.1 和实际验证的 Flatpak app/runtime commit。

`.github/workflows/freecad-measurements.yml` 在相关改动、每周和手动触发时
运行，初期为 non-blocking，并上传报告及模型供人类复查。仅环境、制品、测量
完整性与进程清理可以影响任务退出码。远程 workflow 尚需推送后观察稳定性；
新增 YAML 不等于 GitHub 已执行，也不等于 required branch protection 已配置。

安装脚本只允许 GitHub 临时 Linux runner 使用，不修改开发者本机的 Flatpak。
它依照 [Flatpak 的 commit 更新接口](https://docs.flatpak.org/en/latest/flatpak-command-reference.html#flatpak-update)
锁定 app/runtime，历史 commit 无法取得时报告环境失败，不静默改用新版。
报告上传使用 [GitHub 官方 upload-artifact](https://github.com/actions/upload-artifact/tree/v4)。
