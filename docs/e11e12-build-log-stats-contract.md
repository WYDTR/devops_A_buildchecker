# E11-E12：build-log-stats 验证配置

保持外层 `schema_version=e11e12-1`、任务 API、artifact URI、SHA256 和任务状态语义。
新增可选请求字段：

| 字段 | 值 | 行为 |
|---|---|---|
| `validation_profile` | 缺省或 null | 调用原有固定样例 `validate`，兼容现有 E8-E12 请求 |
| `validation_profile` | `build-log-stats-v1` | 调用本工具的行为验证器 |
| `validation_profile` | 其他值 | 修复验证阶段拒绝为 `INVALID_REQUEST` |

该字段只选择 repair 后的验证规则，DRAFT、真实 strace 全量图、增量扫描、报告消费的
commit/hash 校验和最终全量复检继续由原流水线执行。E12 的输入仍是本轮 `incremental-check.json`。

## 本项目验收

- 构建：`make clean app`。
- 功能：目标版本的 `tests/test_cli.py` 全部通过。
- 固定输入：`./app --json tests/fixtures/compiler.log`。
- 初始输出：`{"lines":9,"warnings":2,"errors":2,"notes":2}`。
- 头文件变化：将 `rules.h` 的 `LOG_STATS_COUNT_NOTES` 从 1 改为 0。
- 不清理而再次 `make app`，应仅刷新 `helper.o`，保留 `main.o`，输出仅将 `notes` 改为 0。
- 使用 GCC `-MM` 检查 Make 声明；原流水线随后继续做最终真实全量复检，MD 应消除。

验证在独立 sandbox 中执行；所有检查通过才把修复后的 Makefile 写回该轮目标工作副本。
失败时目标 Makefile 保持原样，并记录 `rollback=true`。源仓库的原始提交保持可追溯。

安装器为 pipeline 保存哈希命名的原始备份和安装收据，且对原有请求保留原验证器。
