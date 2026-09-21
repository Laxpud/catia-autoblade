# 再分发依据与批准边界

本目录的四份 CSV 来自 Hannnk（https://github.com/Hannnk）。维护者于
2026-08-12 确认作者直接授权，可随本项目公开仓库、源码归档及 wheel 分发。
详细文件身份见 `docs/example-data-audit.md`；本夹具按 LF 保存这些获批字节。

CATIA STEP 由项目维护者使用上述输入在 CATIA P3 V5-6R2020 生成；维护者于
2026-09-16 批准原始 SHA-256 `d9ef236cb71e2765c69badec9cc7506b4744bb5d133208dc5cc66a9988824db9`
作为黄金基线，并允许随公开测试夹具分发。来源与批准记录见
`docs/validation/catia-baseline-2026-09-07.md`。公开副本仅将 HEADER/FILE_NAME
路径替换为 `catia.stp`；DATA 段字节和原始 CRLF 完整保留。manifest 分别记录
原始文件、清理后文件和 DATA 段摘要。

这是项目内的直接授权记录，不宣称获得另一份标准开源数据许可证，也不扩大到
其他模型或用途。本夹具只进入源码归档，不进入 wheel。软件回归阈值的批准见
`docs/validation/freecad-precision-proposal-2026-09-16.md`；它们不是制造公差。
