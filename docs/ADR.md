# ADR：E11–E12 编排接口与构建日志工具验证

<!-- generated-e11e12-docs-v1:241880331 -->

编号：ADR-E11E12-241880331-01。作者：241880331 / A 组。整理时间：2026-11-18 00:09:36 +08:00。
状态：实现与服务器技术验证完成；原集成仓库 PR/CI 待提交后记录。

## 问题与约束

BuildChecker 实际图需要成为 EChecker 的历史输入；增量报告再被 MDFixer 消费。
报告必须带明确版本、源提交、job_id/trace_id、产物 URI 和 SHA256，防止跨任务或旧提交数据被用于修复。
固定样例的输出 1→2 验证不能代表新日志统计工具的行为，且应保留已有 E8-E12 的调用兼容性。

## 候选方案

|方案|影响|
|---|---|
|把新工具改为只打印固定数字|失去实际日志统计功能，验证不能体现工具行为|
|直接替换原 validate|会影响原有样例和 E8-E10 检查|
|显式可选 validation_profile，独立验证器|保留原缺省逻辑，为新工具执行真实行为断言|

## 采用方案与原因

保留 e11e12-1 外层封装和 e8e10-1 内部 EChecker 数据；使用 `validation_profile=build-log-stats-v1`
选择独立验证器。缺省请求继续调用原 validate；未知配置在修复验证阶段返回 INVALID_REQUEST。
只扩展验证选择，DRAFT、真实 strace 全量采集、增量/全量对照、报告哈希和最终全量复检沿用原流程。

验证器在 sandbox 中校验补丁、干净构建和功能测试，再修改 rules.h 并普通增量 make。
要求 helper.o 更新、main.o 复用、notes 2→0；全部通过后才写回该轮目标工作副本的 Makefile。
失败保留日志与原 Makefile。集成源码与被测工具分别维护、分别留证。

## 输入、输出与来源

输入字段包括 mode、repo、base、target、candidate、expected_output、build_timeout，以及可选 validation_profile。
产物字段保持 schema_version、kind、commit、status、job_id、trace_id、artifacts(uri/sha256/bytes)。
真实源仓库为 https://github.com/WYDTR/build-log-stats.git，C0 `48d8fbf69b100637e1edc085a11c5660ec5a406e`，C1 `2f45f30f288f85c824018202337509f7b569a1f7`。
本轮新工具与受控故障来源在 data/real-dataset.json 如实说明，并记录 AI 辅助开发事实。

## 验证结果与兼容性

新增两个重启契约测试，服务器原 10 项与新增 2 项共 12 项通过。
旧提交报告被拒绝；下载哈希匹配；同键同输入复用原任务、同键异输入返回 409；
实际服务重启后已完成任务仍可查且仍幂等。排队/运行中恢复标记在独立契约测试中验证。
新工具服务端五阶段 `job-79d0575f48f74ada898a8d40292a788a` 完成，修复消费哈希匹配，五项复验全真，最终无 MD。
新工具自身 CI run 44103198658 success；集成 CI 按手册保留 E7/E8-E10，并新增 E11-A/B/E12 矩阵。

## 运行与交付影响

服务绑定宿主回环地址，通过 SSH 转发进行单人双机替代演练；本轮 B 方未参与。
使用显式幂等键及持久化状态恢复。网络超时按新目录重试，保留首轮失败证据。
原始源提交、失败产物、修复补丁和验证日志分别保留；最终提交 SHA 与 CI run 随交付归档。
安装器为 pipeline 保存哈希命名备份、校验已知入口并记录安装收据；重复安装保持幂等。
