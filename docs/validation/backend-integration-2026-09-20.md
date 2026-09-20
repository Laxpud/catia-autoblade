# 阶段 3：内部 backend 集成验证

本记录对应 2026-09-19 恢复、2026-09-20 收尾的阶段 3 开发工作。包版本仍为
`0.2.0`；本次 dirty worktree 制品只用于开发验证，不是 `0.3.0` preview 发布。
阶段 4 的完整公开黄金矩阵、CI 和阶段 5 的正式发布门禁仍需独立完成。

## 已实现契约

- `core.backend` 定义内部 backend 名称、类型化制品和错误类别；工厂只显式装载
  CATIA 或 FreeCAD。CATIA 仍是所有平台默认值，继续使用原 Builder 和每任务
  `DispatchEx` 会话；共享核心不导入 COM/FreeCAD 运行时。
- Planner 保存原始 CSV 字节摘要和已解析数据，执行时不再读取工作区输入；
  规划后输入移动/删除不会改变请求，解析窗口内检测到编辑则在 CAD 前失败。
- CLI/config 在 Planner 前确定 backend；三个命令共用真实 `.CATPart + .stp`
  或 `.FCStd + .stp` 路径。`create`、`batch` 新增 dry-run，`sweep` manifest v3
  只记录唯一 backend 和 typed artifacts，不再写 v2 `output_files`。
- 配置 schema v4 增加 `defaults.backend` 与 `freecad` 表；v3 通过现有显式
  预览、源摘要检查、备份与原子替换迁移，不能重复套用 v1/v2 的路径修正规则。
  CLI `--backend` 优先于配置；FreeCAD 默认 timeout 为 900 秒，可用
  `--timeout-seconds` 覆盖。
- 每个 FreeCAD 任务启动独立 Flatpak `FreeCADCmd`，使用隔离 user/system cfg、
  stdout/stderr 捕获和严格 request/result v1。未知 schema、非零退出码、结果缺失、
  不完整双制品、摘要错误、无有效单实体重开证据均失败。其他 `>=1.1` 版本给出
  未认证警告；低于 1.1 拒绝运行。
- 同目标文件系统暂存；完整验证 FCStd ZIP、内核重开、AP242/mm/`1e-7 mm`
  STEP 声明和文件摘要后才发布。发布中途失败恢复旧集合；恢复失败保留 staging
  及备份并报告位置，不伪装成成功。普通成功任务不增加日志或 JSON sidecar。
- `--keep-failed-model` 对可识别文档尽力保留唯一失败快照，旧
  `--keep-failed-part` 显示弃用警告并转发；timeout 仅保存已有可识别 FCStd。
  Ctrl-C 清理当前 owned process group 并停止整个调用；不执行全局 `flatpak kill`。
- `doctor --backend freecad` 执行固定依赖/NumPy 导入、最小 FCStd 创建与重开。
  `doctor --all` 汇总两个后端，任一 FAIL 都返回非零。

### 几何和追溯

正式 Runner 保留阶段 2 的 Gordon 网络、变换顺序、尖/钝后缘构造及精度门槛。
STEP 的批准值明确写入请求和 FCStd：precision mode 2、`1e-7 mm`、surfacecurve
mode 1、AP242DIS/mm。`BladeSolid` 是静态 Shape，`InputCurveNetwork` 是审计快照，
`Traceability` 保存完整闭合请求、摘要、算法和实际 dependency fingerprint。

两截面测试发现原型把“没有内部 knot 的一次多项式”错误报告为内部 C1。修正后
`minimum_interior_continuity_order = null` 表示没有内部接缝需要检查；存在内部 knot
时仍按 degree − multiplicity 判断，C2 门槛没有放宽。该修正不改变几何构造，已有
内部 C1 接缝仍失败。

固定七文件 CurvesWB 闭包随 wheel/sdist 提供，源码未修改，附带双许可证、来源/
逐文件摘要 manifest 和 NOTICE。Host/Child 都验证固定摘要。显式
`--freecad-dependency-dir` 可用于本地修改副本，结果标为
`unverified_custom_dependency`，不适用于 release/golden gate。

## 验证证据

默认 pytest 不启动真实 CAD。新增 FreeCAD 进程防护与已有 COM 防护并存；mock
覆盖后端优先级、三命令普通/交互/dry-run、已有单个制品、覆盖回滚、部分发布、
回滚失败留证、结果协议、超时、快照、失败继续、中断停止及 doctor 汇总。

最终源码通过 Linux CPython 3.14.4 与 Windows CPython 3.14.7 的完整检查：
两端各 **206 项 pytest**、Ruff、wheel/sdist 构建、非 editable wheel 安装 smoke、
版本/内容/固定依赖摘要检查均通过。Linux 日志为
`output/stage3-check-linux-final-20260920.log`；Windows 最终摘要退出码为 0，
本地运行副本和虚拟环境已清理，回收日志位于
`output/stage3-windows-records-20260919/`。

最终 wheel 与由其 sdist 重建的 wheel，67 个 `autoblade/` 包内文件逐字节一致。
这包含固定 Runner、协议、七文件源码闭包、manifest 和双许可证。

原始日志保存在忽略的
`output/stage3-*`，Windows 日志还保留于
`%LOCALAPPDATA%\AutoBlade-checks\records\stage3-20260919\`。


### 真实 FreeCAD wheel smoke：通过

最终源码 wheel 在 Linux/Flatpak FreeCAD 1.1.3、子解释器 NumPy 2.4.4 中通过：

| 路径 | 案例与结果 |
| --- | --- |
| doctor | 固定依赖、NumPy、最小 FCStd 创建/重开通过 |
| create | `naca0012_sharp.csv` + 两截面 `blade_sections-naca.csv`，单有效闭合 solid、FCStd/STEP 通过 |
| batch | `sc1095.csv` 钝尾缘 + 同一两截面模板，双制品通过 |
| sweep | 上述尖/钝两任务依次独立执行，2/2 成功 |
| 嵌入请求重建 | 不读取 CSV，原请求 SHA-256 与全部几何测量逐值相同 |
| timeout | 显式 `0.1 s`，退出码 1，无新制品、无 owned instance 残留 |
| Ctrl-C | 在独立 CAD 子进程启动后向 Host 发 SIGINT，退出码 130，无 owned instance 残留 |

完整记录：`output/stage3-final-wheel-smoke-20260920/summary.json`；各命令、stdout/
stderr 和制品位于同目录。运行前后 FreeCAD 实例集合均为空，所有任务隐藏暂存
目录已清理。普通测试不曾启动真实 CATIA，也未连接或退出用户的 CATIA 会话。

### 89 截面多翼型代表模型：通过

公开 `blade_sections-multi-airfoil.csv` 与 300/253/249 点三翼型从已安装 wheel
执行真实 create，约 **391.079 s**、峰值 RSS **275,560 KiB**。结果为有效闭合
单实体，FCStd 与 AP242 STEP 重开均通过；截面保持最大 `8.640e-13 mm`，guide
保持最大 `1.148e-13 mm`，均小于该模型 `0.007288627 mm` 的已批准相对网络门槛。
这些是网络保持的有限采样值，不是 CATIA 黄金差异或制造公差。

- 原生体积：`1308847.159659139 mm³`；STEP 重开体积：`1308847.159658664 mm³`。
- FCStd：2,456,240 字节，SHA-256
  `11c7d7a6f3a9a6976868f40a0194fbaa64df98c8910bed980f12e89f7e390a16`。
- STEP：7,010,685 字节，SHA-256
  `13b67dab504759c983fb85e0de614e55d8088ca0de3e395892362f78ca77c308`。
- 请求 SHA-256：
  `4b5d6f63b02b18e6859f2949f07bb400016e3dfd3a64e03dfedee5f2c014ba43`。
- Runner SHA-256：
  `76bbf2181fa826de5d344463d527884601779df815b1ca167f1f530ab8a7dd3b`。
- 固定 dependency fingerprint：
  `973a68bb4b88dcc139316b9acb1ca80f609b3c0de717246b95260c8671d79a70`。

该长任务使用先前安装的本阶段候选 wheel；后续修改只涉及 Host 输入摘要闭合与
失败路径。已逐字节确认其 Runner 与最终 wheel 相同，并重新用最终 Planner
计算出同一请求摘要。日志、完整测量和制品在
`output/stage3-wheel-multi-20260920*`。

### 制品与 gate 边界

完成代码检查的最终开发 wheel SHA-256：
`b0f444e8243a7d9f181944934b11666073fb8529ee554d5b53a63d0fecfcc763`；对应 sdist：
`29c6ecbc0d7957f02a8094ef7518fb5cc07c4671306a00e4e3f650cc3b9cf227`。
上述摘要对应最终代码检查时的开发制品；本验证记录及 TODO 收尾更新晚于该构建，
不把它们称为干净标签发布制品。重建内容比较见
`output/stage3-final-sdist-rebuild/`，摘要保存在
`output/stage3-final-artifact-sha256.json`。

阶段 3 的 Exit gate 已满足。阶段 4 仍要固化完整公开黄金矩阵、逐案例阈值和
Linux CAD CI；阶段 5 才执行真实 CATIA 发布回归、当前文档整体切换和版本发布。
本轮没有 Git commit、仓库改名或发布操作。

## 复现入口

常规双平台检查：

```sh
bash scripts/check-linux.sh
```

```powershell
pwsh -File scripts/check.ps1
```

真实 FreeCAD 安装 smoke 只能显式运行；先把候选 wheel 安装到全新环境，再执行：

```sh
python scripts/smoke_real_freecad.py \
  --python /path/to/clean-venv/bin/python \
  --output output/freecad-wheel-smoke-new
```

输出目录必须不存在。脚本验证安装来自 `site-packages`，使用公开两截面尖/钝
案例运行 doctor/create/batch/sweep，直接用固定 Runner 从 FCStd 嵌入请求重建，
逐值比较请求与几何测量，并以独立案例验证 timeout 返回 1、Ctrl-C 返回 130、
任务暂存清理和 Flatpak 实例集合恢复。Flatpak 实例登记晚于进程退出时，脚本会
等待有限窗口，避免把上一任务的登记误认为下一任务已经启动。

schema v3 用户应先执行 `autoblade config migrate` 检查预览，再按需执行
`autoblade config migrate --apply`。回滚配置时使用该命令创建的迁移前备份；
不能把 v4 用户配置无备份降级。公开帮助与支持声明的整体切换保留到阶段 5。
