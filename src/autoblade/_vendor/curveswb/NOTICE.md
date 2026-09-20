# CurvesWB source closure

AutoBlade 随附 CurvesWB 0.6.81 的七文件未修改源码闭包。来源、固定 commit、
逐文件摘要、SPDX 与上游版权声明见 manifest.json；原始源码头保持不变。

TiGL 派生文件遵循 LICENSE-TIGL (Apache-2.0)，其余文件遵循 LICENSE-CODE
(LGPL-2.1-or-later)。本项目的许可证不替代第三方许可证。完整上游源码可从
manifest 中的 repository 与 commit 获取。

源码仅在 FreeCAD 子解释器中加载。开发者可通过 --freecad-dependency-dir 指向
具有相同七文件布局的本地修改副本；修改后结果标记 unverified_custom_dependency，
不用于认证或发布门禁。FCStd 会记录实际逐文件摘要和 fingerprint。
