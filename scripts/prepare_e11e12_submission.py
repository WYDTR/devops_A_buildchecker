"""Generate E11-E12 submission documents from existing server evidence."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT_REPORT_TEMPLATE = """# E11–E12 个人报告

学号/小组/轨道：
仓库与提交 SHA：

## E11 轨道集成
上游输出、下游输入、版本及字段映射；本人的代码修改和测试。

## E12 联调
请求 JSON、job_id、trace_id、阶段产物清单、补丁和复验结果。

## 真实数据
项目来源、base/target 完整 SHA、变化、适配代码、实际结果。

## 故障与处理
错误码、日志位置、原因、修改及重跑结果。

## 交付索引
|任务|文件/URL|结果|
|---|---|---|
|E11|||
|E12|||
|真实项目|||"""

ADR_TEMPLATE = """# ADR：集成接口决策

编号、日期、作者：
问题：
候选方案：
采用方案与原因：
输入输出字段：
兼容性与测试："""

TOOL_CI = {
    "repository": "WYDTR/build-log-stats", "run_id": 44103198658,
    "head_sha": "b7f9f3000a62210c09bbe4ecec4d34fc4231515e",
    "conclusion": "success",
    "url": "https://github.com/WYDTR/build-log-stats/actions/runs/44103198658",
    "evidence_source": "Authenticated gh run list output supplied by the student",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalize(text):
    return text.replace("\r\n", "\n").strip()


def prepare(root):
    root = Path(root).resolve()
    require((root / "run_e11e12.py").is_file(), "Run from the A-buildchecker checkout")
    top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()).resolve()
    require(top == root, "The lab directory must be the Git repository root")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    require(branch == "e11-e12-integration", "Use the e11-e12-integration branch")

    def path(relative):
        result = root / relative
        require(result.resolve().is_relative_to(root), f"Path leaves the checkout: {relative}")
        return result

    a = read_json(path("work/e11-a-01/result.json"))
    a_inc = read_json(path("work/e11-a-01/incremental-report.json"))
    reuse = read_json(path("work/e11-a-02/result.json"))
    reuse_inc = read_json(path("work/e11-a-02/incremental-report.json"))
    stale = read_json(path("work/e11-stale-01/result.json"))
    fixed = read_json(path("work/e12-02/result.json"))
    fixed_recheck = read_json(path("work/e12-02/recheck.json"))
    api = read_json(path("work/api-client/result.json"))
    repeated = read_json(path("work/api-client/repeat-submit.json"))
    restarted = read_json(path("work/api-client/status-after-restart.json"))
    restart_repeat = read_json(path("work/api-client/repeat-after-restart.json"))
    conflict = read_json(path("work/api-client/conflict.json"))
    real = read_json(path("work/e12-real-review.json"))
    run, dataset = real["run"], real["dataset"]
    receipt_path = path("work/e11e12-document-receipt.json")
    previous_receipt = read_json(receipt_path) if receipt_path.exists() else {}

    for name, record in (("E11-A", a), ("E11-A reuse", reuse), ("E12 fixed", fixed), ("API", api), ("E12 project", run)):
        require(record.get("status") == "SUCCEEDED", f"{name} has not succeeded")
    require(reuse_inc["refreshed"] == [] and sorted(reuse_inc["reused"]) == ["helper.o", "main.o"], "Cache reuse evidence differs")
    require(stale["envelope_check"] == stale["repair_check"] == "STALE_REPORT" and stale["makefile_unchanged"], "Stale report was not safely rejected")
    require([s["name"] for s in run["stages"]] == ["draft", "full-check", "incremental-check", "repair", "recheck"], "Project stage sequence differs")
    require(real["consumed_hash_matches"] is True, "Consumed report hash did not match")
    require(real["incremental"]["findings"] == [{"type": "MISSING", "target": "helper.o", "dependency": "rules.h"}], "Unexpected project findings")
    verdict = real["recheck"]["data"]["validation"]
    require(verdict["accepted"] and all(verdict["checks"].values()) and real["recheck"]["data"]["findings"] == [], "Project repair has not passed")
    require(real["header_before"]["notes"] == 2 and real["header_after"]["notes"] == 0, "Header behaviour evidence differs")
    require(real["history"]["passed"] is True, "Project history replay failed")
    require(run["base_commit"] == dataset["base_commit"] and run["target_commit"] == dataset["target_commit"], "Source commit mismatch")
    require(real["request"]["validation_profile"] == verdict["profile"] == "build-log-stats-v1", "Wrong validation profile")
    raw_result = read_json(path("work/e12-real-01/result.json"))
    for key in ("status", "job_id", "trace_id", "base_commit", "target_commit"):
        require(raw_result.get(key) == run.get(key), f"Raw project result differs: {key}")
    for stage in run["stages"]:
        name = stage["name"]
        raw_path = path(f"work/e12-real-01/{name}.json")
        require(stage["artifact"]["uri"] == f"artifact://{run['job_id']}/{name}.json", f"Wrong {name} URI")
        require(hashlib.sha256(raw_path.read_bytes()).hexdigest() == stage["artifact"]["sha256"], f"Changed stage artifact: {name}")
        envelope = read_json(raw_path)
        expected_commit = dataset["base_commit"] if name == "full-check" else dataset["target_commit"]
        require(envelope["schema_version"] == "e11e12-1" and envelope["status"] == "SUCCEEDED"
                and envelope["job_id"] == run["job_id"] and envelope["trace_id"] == run["trace_id"]
                and envelope["commit"] == expected_commit, f"Envelope mismatch: {name}")
    consumed = real["repair"]["data"]["input_report"]
    require(consumed["uri"] == f"artifact://{run['job_id']}/incremental-check.json"
            and consumed["sha256"] == hashlib.sha256(path("work/e12-real-01/incremental-check.json").read_bytes()).hexdigest(),
            "Raw consumed report hash mismatch")
    for key, filename in (("repair", "repair.json"), ("recheck", "recheck.json"), ("incremental", "incremental-report.json")):
        require(read_json(path("work/e12-real-01/" + filename)) == real[key], f"Review differs from raw {key}")
    for state in (repeated, restarted, restart_repeat):
        require(state["job_id"] == api["job_id"] and state["status"] == "SUCCEEDED", "API identity/status mismatch")
    require(restarted["trace_id"] == restart_repeat["trace_id"], "Restart trace mismatch")
    require(conflict["error"] == "IDEMPOTENCY_CONFLICT", "Conflict response differs")
    require(fixed_recheck["data"]["validation"]["accepted"] and not any(
        item["type"] == "MISSING" for item in fixed_recheck["data"]["findings"]), "Fixed-sample recheck differs")
    api_uri = f"artifact://{api['job_id']}/candidate.patch"
    manifest_hash = next(item["sha256"] for item in api["artifacts"] if item["uri"] == api_uri)
    patch_hash = hashlib.sha256(path("work/api-client/candidate.patch").read_bytes()).hexdigest()
    require(patch_hash == manifest_hash, "Downloaded API patch hash mismatch")
    headers = path("work/api-client/candidate.headers").read_text(encoding="iso-8859-1")
    header_hash = re.search(r"^X-Content-SHA256:\s*([a-f0-9]{64})\s*$", headers, re.M | re.I)
    require(header_hash is not None and header_hash[1].lower() == patch_hash, "API response header hash mismatch")

    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S +08:00")
    report = f"""# E11–E12 个人报告

<!-- generated-e11e12-docs-v1:241880331 -->

学号/小组/轨道：241880331 / A 组 / BuildChecker → EChecker；E12 共享编排联调。
整理时间：{stamp}。

## 仓库与版本

集成实现仓库：https://github.com/WYDTR/devops_A_buildchecker ，分支 `e11-e12-integration`。
最终集成实现提交、PR 和 CI run 以交付归档的 CI 记录为准；本报告随实现分支提交，避免自引用提交 SHA。
被测工具仓库：{dataset['source_repository']}。

|版本|完整提交 SHA|作用|
|---|---|---|
|C0|`{dataset['base_commit']}`|基础日志统计实现|
|C1|`{dataset['target_commit']}`|大小写兼容、note 统计及明确注入的漏依赖|
|C2|`{dataset['fixed_commit']}`|修复依赖声明与回归验证|

## E11 轨道集成

BuildChecker 在基线提交执行真实 strace 和 Make 数据库采集，实际图投影为 main.o/helper.o 的本地依赖，
写入 EChecker 历史缓存。目标提交增量检测后，与目标全量检查的发现集合比较。
外层报告版本为 `e11e12-1`；内部 EChecker 报告沿用 `e8e10-1`，二者分别表示编排封装和组件数据。
外层 job_id/trace_id 串联各阶段；原始检测器的内层 trace_id 保留用于定位采集证据。

固定样例：基线 `{a['base_commit']}`，目标 `{a['target_commit']}`，
job_id `{a['job_id']}`，trace_id `{a['trace_id']}`。
新增缺失依赖为 main.o → extra.h，保留原 config.h 缺失依赖及 unused.h 冗余依赖。
该次刷新 {len(a_inc['refreshed'])} 个目标、复用 {len(a_inc['reused'])} 个目标；预处理指令变化使全局缓存键失效。

复用对照：基线 `{reuse['base_commit']}`，目标 `{reuse['target_commit']}`，
仅加入 Dockerfile.broken，源码预处理指令和 Make 编译规则未变，刷新 0 个、复用 main.o/helper.o 两个目标。
这是课堂生成样例的额外提交范围对照，与后述新开发工具分别记账。

旧报告实验分别在封装校验和修复入口得到 STALE_REPORT，Makefile 保持不变。
新增两项重启契约测试覆盖已完成任务恢复、排队/运行中任务的 SERVER_RESTARTED、同键复用与新键重试；
服务器已验证原 10 项加新增 2 项共 12 项测试。日志：`work/e12-contract-tests.log`。
A 组独立轨道证据在 `work/e11-a-01/`、`work/e11-a-02/`；E11-B 独立模式由课程 CI 矩阵另行验证。

## E12 固定样例与 API 联调

固定样例在 `work/e12-02/` 完成 draft、full-check、incremental-check、repair、recheck 五阶段，
job_id `{fixed['job_id']}`，trace_id `{fixed['trace_id']}`。
复验 accepted={str(fixed_recheck['data']['validation']['accepted']).lower()}，MD 消除，允许保留 RD。

API 的固定样例任务为 `{api['job_id']}`，trace_id `{restarted['trace_id']}`。
相同键和输入返回同一任务；同键修改 target 返回 HTTP 409 / IDEMPOTENCY_CONFLICT。
下载补丁与清单及响应头的 SHA256 核对通过，补丁哈希为 `{patch_hash}`。
服务实际重启后，原任务仍可查询为 SUCCEEDED，再提交同键同输入仍返回原任务。
重启中的未完成状态处理由新增契约测试验证，不将该模拟测试表述为实际中断了一次构建。

分机演练形式：A 组本人使用 Windows 本地客户端，经 SSH 隧道的 18080 端口访问服务器回环 8080。
完成健康检查、提交、查询和补丁下载，Windows 文件哈希与服务器一致；B 方未参与本次替代演练。
Windows 原始客户端文件在本机 `work/e12-crosshost-client/`，最终归档时一并回传。

## 新开发项目接入与验收

本轮新开发 C 构建日志统计工具，支持文件/标准输入、JSON/文本输出、颜色日志和长行。
基础和功能扩展使用实际开发提交，开发中有 AI 编程辅助；没有将其描述为已有长期生产历史的项目。
C1 的 helper.o → rules.h 漏依赖以及 Dockerfile 缺少工具链，均为本轮明确注入的受控故障。

请求：`data/real-request.json`；来源清单：`data/real-dataset.json`；验证配置：`build-log-stats-v1`。
完整输入记录：`work/e12-real-01/request.json`；运行结果：`work/e12-real-01/result.json`。
job_id `{run['job_id']}`，trace_id `{run['trace_id']}`，五阶段全部 SUCCEEDED。
DRAFT 的镜像真实运行退出码为 {real['draft']['verification']['exit_code']}，输出与预期完全一致。
增量结果唯一新增 MD 为 helper.o → rules.h；该次刷新两个检测缓存目标、没有复用。

修复直接消费本轮 incremental-check.json，内容哈希为
`{real['repair']['data']['input_report']['sha256']}`，与实际文件一致。
补丁只增加该头文件声明。验证在独立 sandbox 中完成：干净构建、功能测试和实际头文件变化。
修改 rules.h 的 note 配置后，普通 make 只刷新 helper.o，保留 main.o，notes 从 2 变为 0；
这是 Make 增量重建的检查，与前述 EChecker 缓存刷新计数分别解释。

patch_applies、build、test、header_change、no_missing 五项全部为 true，accepted=true，
最终全量 findings=[]。修复后的 Makefile SHA256 为
`{real['recheck']['data']['patched_makefile_sha256']}`。
报告 commit 仍标识被检测的 C1 源提交，派生修复文件另以补丁和文件哈希定位；未改写源 Git 历史。
历史复现 `work/real-history-01/result.json` 的 passed=true，C0/C1/C2 功能与依赖差异均验证通过。

新工具 CI：[{TOOL_CI['run_id']}]({TOOL_CI['url']})，状态 completed/success，
head SHA `{TOOL_CI['head_sha']}`。它是新工具仓库的 CI；原集成仓库的 PR CI 结果在后续交付记录单独保存。

## 故障与处理

1. 固定样例首次 E12 在 DRAFT 第二轮 apt-get update 阶段超过 600 秒，证据保留 `work/e12-01/`。
   沿用实验环境的镜像源配置、IPv4 和重试，超时调整为 1800 秒，在新目录 `work/e12-02/` 成功。
2. STALE_REPORT 通过消费前提交校验阻止修复，原始报告与 Makefile 保留。
3. 服务窗口的 SSH 连接中断后，旧容器仍占用 127.0.0.1:8080；按端口、镜像和命令定位原容器，
   显式 docker stop 后重建服务，随后验证持久化状态与幂等键恢复。
4. 新工具本地历史复现曾遇到 CRLF 补丁与 LF 源文件不匹配；统一补丁为 LF 后历史修复通过，失败记录保留。
5. 新 SSH 会话未找到 gh 认证时，source 课程 github_session.sh 恢复学号配置，再查询/提交。

## 交付索引

|任务|证据位置|结果|
|---|---|---|
|E11-A 固定样例|work/e11-a-01/|SUCCEEDED|
|E11-A 复用对照|work/e11-a-02/|两目标复用|
|旧报告拒绝|work/e11-stale-01/|两入口 STALE_REPORT|
|E12 失败与重跑|work/e12-01/、work/e12-02/|保留失败，重跑成功|
|API、哈希、幂等和重启|work/api-client/、work/api-jobs/|已验证|
|单人双机替代演练|Windows 本机 work/e12-crosshost-client/|待最终归档回传原始客户端文件|
|新工具历史复现|work/real-history-01/|passed=true|
|新工具五阶段|work/e12-real-01/|SUCCEEDED、最终无 MD|
|请求与来源|data/real-request.json、data/real-dataset.json|完整 SHA 与受控故障来源|
|适配接口|docs/e11e12-build-log-stats-contract.md|兼容原有缺省请求|
|最终提交与集成 CI|后续 work/ci-e11e12/ 记录、PR 检查与归档|提交后核验|

data/ 和 work/ 按手册单独归档；新工具源代码与历史在新工具仓库，集成代码、接口和本文在原个人集成仓库。

## AI 辅助与个人工作

本轮工具、验证适配、测试及文档有 AI 编程辅助。本人选择并组织实验，在 Windows/服务器执行命令、
完成 GitHub 上传及认证、核对实验输出，并保留实际运行结果。两个新工具故障均如实标注为受控注入。
"""

    adr = f"""# ADR：E11–E12 编排接口与构建日志工具验证

<!-- generated-e11e12-docs-v1:241880331 -->

编号：ADR-E11E12-241880331-01。作者：241880331 / A 组。整理时间：{stamp}。
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
真实源仓库为 {dataset['source_repository']}，C0 `{dataset['base_commit']}`，C1 `{dataset['target_commit']}`。
本轮新工具与受控故障来源在 data/real-dataset.json 如实说明，并记录 AI 辅助开发事实。

## 验证结果与兼容性

新增两个重启契约测试，服务器原 10 项与新增 2 项共 12 项通过。
旧提交报告被拒绝；下载哈希匹配；同键同输入复用原任务、同键异输入返回 409；
实际服务重启后已完成任务仍可查且仍幂等。排队/运行中恢复标记在独立契约测试中验证。
新工具服务端五阶段 `{run['job_id']}` 完成，修复消费哈希匹配，五项复验全真，最终无 MD。
新工具自身 CI run {TOOL_CI['run_id']} success；集成 CI 按手册保留 E7/E8-E10，并新增 E11-A/B/E12 矩阵。

## 运行与交付影响

服务绑定宿主回环地址，通过 SSH 转发进行单人双机替代演练；本轮 B 方未参与。
使用显式幂等键及持久化状态恢复。网络超时按新目录重试，保留首轮失败证据。
原始源提交、失败产物、修复补丁和验证日志分别保留；最终提交 SHA 与 CI run 随交付归档。
安装器为 pipeline 保存哈希命名备份、校验已知入口并记录安装收据；重复安装保持幂等。
"""

    index = """# E11–E12 提交资料索引

- [个人报告](../个人报告.md)
- [ADR](../ADR.md)
- [公共接口契约](../接口契约.md)
- [新工具验证配置](../e11e12-build-log-stats-contract.md)
- [数据与联调记录](数据与联调记录.csv)

原始 data/ 与 work/ 独立归档，最终 PR/CI 的运行编号、链接和提交 SHA 在 CI 取证时保存。
"""
    docs = {
        "docs/个人报告.md": report,
        "docs/ADR.md": adr,
        "docs/e11e12/README.md": index,
    }
    # Preserve filled documents; only known templates or our own generated reports can be refreshed.
    expected = {"docs/个人报告.md": ROOT_REPORT_TEMPLATE, "docs/ADR.md": ADR_TEMPLATE}
    for relative in expected:
        target = path(relative)
        if target.exists():
            current = normalize(target.read_text(encoding="utf-8"))
            generated = ("<!-- generated-e11e12-docs-v1:241880331 -->" in current
                         and previous_receipt.get("generated_sha256", {}).get(relative)
                         == hashlib.sha256(target.read_bytes()).hexdigest())
            require(current in ("", normalize(expected[relative])) or generated,
                    f"Existing filled document needs a manual merge: {relative}")

    duplicate_specs = {
        "docs/e11e12/个人报告.md": (ROOT_REPORT_TEMPLATE, "# 个人报告\n\n完整报告见 [个人报告](../个人报告.md)。\n"),
        "docs/e11e12/ADR.md": (ADR_TEMPLATE, "# ADR\n\n完整决策记录见 [ADR](../ADR.md)。\n"),
    }
    preserved = []
    for relative, (template, pointer) in duplicate_specs.items():
        target = path(relative)
        if not target.exists() or normalize(target.read_text(encoding="utf-8")) in ("", normalize(template), normalize(pointer)):
            docs[relative] = pointer
        else:
            preserved.append(relative)

    contract = path("docs/接口契约.md")
    contract_text = contract.read_text(encoding="utf-8") if contract.exists() else "# e11e12-1 接口契约\n"
    heading = "## build-log-stats-v1 验证扩展"
    if heading not in contract_text:
        contract_text = contract_text.rstrip() + "\n\n" + heading + "\n\n详见 [验证配置契约](e11e12-build-log-stats-contract.md)。该字段缺省时保留原有验证逻辑。\n"
    docs["docs/接口契约.md"] = contract_text
    nested_contract = path("docs/e11e12/接口契约.md")
    nested_text = nested_contract.read_text(encoding="utf-8") if nested_contract.exists() else "# e11e12-1 接口契约\n"
    if heading not in nested_text:
        nested_text = nested_text.rstrip() + "\n\n" + heading + "\n\n扩展字段和行为见 [验证配置契约](../e11e12-build-log-stats-contract.md)，公共接口见 [接口契约](../接口契约.md)。\n"
    docs["docs/e11e12/接口契约.md"] = nested_text
    docs["docs/e11e12/PR_BODY.md"] = f"""接通 E11 的真实全量图、增量缓存及发现集合对照，并完成 E12 的报告消费、修复和复验。
新增可选 build-log-stats-v1 行为验证配置，保留原有缺省验证逻辑及 E7/E8–E10 工作流。

验证：
- 服务器固定样例与新开发 C 工具的五阶段均 SUCCEEDED；新工具漏依赖 helper.o → rules.h 修复后最终无 MD，notes 2→0。
- 修复消费本轮增量封装报告，内容哈希匹配；真实项目 job_id 为 {run['job_id']}。
- 12 项课程契约测试通过，API 幂等、409 冲突、下载哈希及实际服务重启后恢复已验证。
- 新工具 CI：{TOOL_CI['url']} （success）。本集成仓库 CI 由当前 PR 检查另行验收。

来源与边界：新工具为本轮 AI 辅助开发并实际维护的项目，漏依赖和缺少工具链均为受控实验故障。
分机环节由 A 组本人在 Windows 与服务器间通过 SSH 转发替代演练，B 方未参与。

文档：docs/个人报告.md、docs/ADR.md、docs/接口契约.md、docs/e11e12-build-log-stats-contract.md。
原始证据：work/e11-a-01、work/e11-a-02、work/e12-02、work/api-client、work/e12-real-01、work/real-history-01。
data/ 与 work/ 按手册单独归档。
"""

    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(["实验", "数据来源", "仓库", "base_commit", "target_commit", "job_id", "trace_id", "报告路径", "补丁路径", "结果"])
    for label, record, folder in (("E11-A", a, "work/e11-a-01"), ("E11-A复用", reuse, "work/e11-a-02"),
                                   ("E12固定样例", fixed, "work/e12-02"), ("E12 API", api, "work/api-client"),
                                   ("E12新工具", run, "work/e12-real-01")):
        writer.writerow([label, "本轮新开发/受控故障" if label == "E12新工具" else "课程固定样例",
                         dataset["source_repository"] if label == "E12新工具" else "course-generated integration-sample",
                         record.get("base_commit", ""), record.get("target_commit", ""), record["job_id"],
                         record.get("trace_id", ""), folder + "/result.json", folder + "/candidate.patch", record["status"]])
    docs["docs/e11e12/数据与联调记录.csv"] = csv_buffer.getvalue()

    # Validate every destination before writing or backing up anything.
    for relative, text in docs.items():
        target = path(relative)
        if target.exists() and relative not in expected and relative not in duplicate_specs and relative not in (
                "docs/接口契约.md", "docs/e11e12/接口契约.md"):
            identical = target.read_bytes() == text.encode("utf-8")
            generated = previous_receipt.get("generated_sha256", {}).get(relative) == hashlib.sha256(target.read_bytes()).hexdigest()
            require(identical or generated, f"Preserve the existing custom document before merging: {relative}")
    path("work").mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="e11e12-docs-", dir=path("work")))
    require(backup.resolve().parent == path("work").resolve(), "Unexpected backup directory")
    changed = []
    for relative, text in docs.items():
        target = path(relative)
        content = text.encode("utf-8")
        if target.exists() and target.read_bytes() == content:
            continue
        if target.exists():
            original = backup / relative
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, original)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        changed.append(relative)
    ignore = path(".gitignore")
    ignore_text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if not {"data/", "/data/"}.intersection(ignore_text.splitlines()):
        if ignore.exists():
            shutil.copy2(ignore, backup / ".gitignore")
        ignore.write_text(ignore_text.rstrip() + "\n/data/\n", encoding="utf-8", newline="\n")
        changed.append(".gitignore")
    receipt = {"generated_at": stamp, "branch": branch, "backup": str(backup), "changed": changed,
               "preserved_custom_documents": preserved, "tool_ci": TOOL_CI,
               "real_job_id": run["job_id"], "real_trace_id": run["trace_id"],
               "raw_stage_hashes_and_envelopes_verified": True,
               "generated_sha256": {relative: hashlib.sha256(text.encode("utf-8")).hexdigest() for relative, text in docs.items()}}
    path("work/e11e12-document-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print("DOCUMENTS_READY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, default=Path.cwd())
    prepare(parser.parse_args().lab_root)
