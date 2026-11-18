# E11–E12 集成 CI 与客户端原件核验

集成 PR：[第 4 号](https://github.com/WYDTR/devops_A_buildchecker/pull/4)。
已核验的实现提交：`936ebe62f77ef0fa372d8cb0988988f7623751be`。

## CI 运行

|工作流|事件|运行|结果|
|---|---|---|---|
|E11-E12 integration|pull_request|[44126139598](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126139598)|completed / success|
|E11-E12 integration|push|[44126128070](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126128070)|completed / success|
|E7 A quality gate|pull_request|[44126139529](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126139529)|completed / success|
|E7 A quality gate|push|[44126128009](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126128009)|completed / success|
|E8-E10 teaching validation|pull_request|[44126139582](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126139582)|completed / success|
|E8-E10 teaching validation|push|[44126127675](https://github.com/WYDTR/devops_A_buildchecker/actions/runs/44126127675)|completed / success|

三类工作流的 push 与 pull_request 共六项检查全部通过，headSha 均与上述实现提交一致。
原始运行清单：`work/ci-e11e12/runs.json`；PR 快照：`work/ci-e11e12/pr-4.json`。
PR 的三份运行产物和日志已下载，核验收据为 `work/ci-e11e12/evidence.json`；收据保存下载位置和阶段显式产物 SHA256。

## 门禁与阶段结果

- E7：8 个用例通过。
- E8–E10：A 轨道 30 行、B 轨道 3 行通过。
- E11–E12：阶段顺序、封装版本、job_id/trace_id、基线/目标提交与显式产物哈希核验通过；B/E12 复验的五项检查均为 true，最终无 MISSING。

|CI 模式|job_id|结果|
|---|---|---|
|e11-a|`job-a323e313b4c14f9090f4d4702b85190d`|SUCCEEDED|
|e11-b|`job-04ac00244f7644d39ad972b3f501ad23`|SUCCEEDED|
|e12|`job-37e2fd556d8d4e05bd1a5a306e58fc72`|SUCCEEDED|

这里的 E11-B 是 CI 执行的独立模式，不代表 B 方同学参与了分机演练。

## Windows 原始客户端文件

A 组本人使用 Windows 客户端，经 SSH 转发访问 Linux 服务器；B 方未参与。
原件已回传 `work/e12-crosshost-client/`，六个文件与 Windows 原件的 SHA256 逐一匹配。
job_id：`job-edb62b56b71c48ce9e91bc5eb4fdcaa4`；trace_id：`trace-0fe9b48533b74fe7a063c8b208b63d90`。
补丁 SHA256：`88074f66c291dcad1344c48f6a2b9ddd42d235d9d0415c85fb33310c5b7cb2af`。
核验收据：`work/e12-crosshost-client/verification.json`。

## 交付版本

上述六项 CI 对应已存在的实现提交。本次补齐文档后的最终提交 SHA、后续 CI 运行记录及合并 SHA 在归档阶段另存，避免报告自引用提交 SHA。
data/ 与 work/ 按手册独立归档；本记录不把尚未发生的文档补全提交 CI 或合并写作已完成。
