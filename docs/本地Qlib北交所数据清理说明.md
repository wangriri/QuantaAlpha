# 本地 Qlib 北交所数据清理说明

本项目运行时使用的是本地 Qlib 数据目录，当前默认路径是：

```text
/Users/wangjiayi/Downloads/QuantaAlpha/data/qlib/cn_data
```

清理边界：

- 只处理本地 Qlib 数据，不连接、不读取、不修改 MongoDB。
- 活跃 Qlib 数据中移除 `bj` 开头的北交所标的。
- `features/bj*` 目录会被移动到本地备份目录。
- `instruments/*.txt` 中 `bj` 开头的标的行会被删除，并在备份目录中保留原始文件。

执行方式：

```bash
.venv/bin/python scripts/remove_bse_from_qlib.py --qlib-dir data/qlib/cn_data
.venv/bin/python scripts/remove_bse_from_qlib.py --qlib-dir data/qlib/cn_data --apply
```

重新从 MongoDB 导出并构建 Qlib 时，`scripts/build_qlib_bin.py` 默认会过滤 `bj` 前缀，避免北交所数据重新进入本项目使用的 Qlib 数据。

如需恢复，可以从脚本输出的 `backup_dir` 中把 `features/` 下的目录移回 `cn_data/features/`，并用 `instruments_original/` 中的文件替换当前 `cn_data/instruments/` 文件。
