"""Update E11-E12 documents using verified CI and Windows client evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


IMPLEMENTATION = "936ebe62f77ef0fa372d8cb0988988f7623751be"
PR_URL = "https://github.com/WYDTR/devops_A_buildchecker/pull/4"
CLIENT_JOB = "job-edb62b56b71c48ce9e91bc5eb4fdcaa4"
CLIENT_TRACE = "trace-0fe9b48533b74fe7a063c8b208b63d90"
PATCH_SHA = "88074f66c291dcad1344c48f6a2b9ddd42d235d9d0415c85fb33310c5b7cb2af"
RUNS = {
    44126139529: ("E7 A quality gate", "pull_request"),
    44126139582: ("E8-E10 teaching validation", "pull_request"),
    44126139598: ("E11-E12 integration", "pull_request"),
    44126128009: ("E7 A quality gate", "push"),
    44126127675: ("E8-E10 teaching validation", "push"),
    44126128070: ("E11-E12 integration", "push"),
}
JOBS = {
    "e11-a": "job-a323e313b4c14f9090f4d4702b85190d",
    "e11-b": "job-04ac00244f7644d39ad972b3f501ad23",
    "e12": "job-37e2fd556d8d4e05bd1a5a306e58fc72",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_text(text, old, new, path):
    if new in text:
        require(text.count(new) == 1 and text.count(old) == new.count(old),
                f"Ambiguous completed replacement in {path}")
        return text
    require(text.count(old) == 1,
            f"Preserve and manually merge changed wording in {path}: {old}")
    return text.replace(old, new, 1)


def finalize(root, dry_run=False):
    root = root.resolve()
    top = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=root, text=True
    ).strip()).resolve()
    require(top == root, "Run at the A-buildchecker Git root")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    require(branch == "e11-e12-integration", "Use the e11-e12-integration branch")
    subprocess.run(["git", "merge-base", "--is-ancestor", IMPLEMENTATION, "HEAD"],
                   cwd=root, check=True)

    ci = read_json(root / "work/ci-e11e12/evidence.json")
    require(ci["head_sha"] == IMPLEMENTATION, "CI belongs to another implementation")
    runs = {r["databaseId"]: r for r in ci["runs"]}
    require(len(ci["runs"]) == len(RUNS) and set(runs) == set(RUNS), "Expected six CI runs")
    for run_id, (workflow, event) in RUNS.items():
        run = runs[run_id]
        require((run["workflowName"], run["event"]) == (workflow, event), "Unexpected CI run")
        require(run["headSha"] == IMPLEMENTATION and run["status"] == "completed"
                and run["conclusion"] == "success", "CI did not succeed at the implementation")
        require(run["url"] == f"https://github.com/WYDTR/devops_A_buildchecker/actions/runs/{run_id}",
                "Unexpected CI URL")
    require(ci["e7_cases"] == 8 and ci["e8e10_rows"] == {"A": 30, "B": 3}, "Gate result differs")
    require(ci["e11e12_jobs"] == JOBS, "Integration jobs differ")
    downloads = Path(ci["download_root"]).resolve()
    require(downloads.is_relative_to((root / "work/ci-e11e12").resolve()), "CI path leaves the checkout")
    hashes = ci["verified_stage_artifact_sha256"]
    require(len(hashes) >= 11, "Stage artifact evidence is incomplete")
    for relative, digest in hashes.items():
        path = (downloads / relative).resolve()
        require(path.is_relative_to(downloads) and sha(path) == digest,
                f"CI artifact changed: {relative}")

    client_dir = root / "work/e12-crosshost-client"
    client = read_json(client_dir / "verification.json")
    require(client["peer_b_participated"] is False, "Keep the single-student exercise attribution")
    require((client["job_id"], client["trace_id"]) == (CLIENT_JOB, CLIENT_TRACE), "Client job differs")
    client_hashes = client["verified_files_sha256"]
    require(set(client_hashes) == {"api-request.json", "candidate.headers", "candidate.patch",
                                   "health.json", "status.json", "submit.json"}, "Expected six client files")
    for name, digest in client_hashes.items():
        require(sha(client_dir / name) == digest, f"Client file changed: {name}")
    require(client_hashes["candidate.patch"] == PATCH_SHA
            and sha(root / "work/api-client/candidate.patch") == PATCH_SHA, "Patch hash differs")
    for name in ("status.json", "submit.json"):
        record = read_json(client_dir / name)
        require((record["job_id"], record["trace_id"], record["status"])
                == (CLIENT_JOB, CLIENT_TRACE, "SUCCEEDED"), "Client response differs")

    replacements = {
        "docs/个人报告.md": [
            ("最终集成实现提交、PR 和 CI run 以交付归档的 CI 记录为准；本报告随实现分支提交，避免自引用提交 SHA。",
             f"集成实现提交：`{IMPLEMENTATION}`；PR：[第 4 号]({PR_URL})。\n"
             "实现提交的六项 CI 与原始产物见 [集成核验记录](e11e12/CI_RECORD.md)。最终交付提交及后续 CI 随归档另存。"),
            ("Windows 原始客户端文件在本机 `work/e12-crosshost-client/`，最终归档时一并回传。",
             "Windows 原始客户端文件已回传服务器 `work/e12-crosshost-client/`，六个文件逐一通过 SHA256 校验；记录为 `verification.json`。"),
            ("原集成仓库的 PR CI 结果在后续交付记录单独保存。",
             "原集成仓库实现提交的六项 CI 均通过，运行编号与原始产物见 [集成核验记录](e11e12/CI_RECORD.md)。"),
            ("|单人双机替代演练|Windows 本机 work/e12-crosshost-client/|待最终归档回传原始客户端文件|",
             "|单人双机替代演练|work/e12-crosshost-client/verification.json|六份原始文件回传并校验通过，B 方未参与|"),
            ("|最终提交与集成 CI|后续 work/ci-e11e12/ 记录、PR 检查与归档|提交后核验|",
             "|实现提交与集成 CI|docs/e11e12/CI_RECORD.md、work/ci-e11e12/evidence.json|936ebe6 的六项检查通过；最终交付版本随归档另存|"),
        ],
        "docs/ADR.md": [
            ("状态：实现与服务器技术验证完成；原集成仓库 PR/CI 待提交后记录。",
             f"状态：实现提交 `{IMPLEMENTATION}` 的六项 CI 通过；客户端原件已回传并核验。最终交付版本以归档记录为准。"),
            ("新工具自身 CI run 44103198658 success；集成 CI 按手册保留 E7/E8-E10，并新增 E11-A/B/E12 矩阵。",
             "新工具自身 CI run 44103198658 success；集成 CI 按手册保留 E7/E8-E10，并新增 E11-A/B/E12 矩阵。\n"
             "实现提交的 push/PR 共六项检查通过；阶段封装与显式产物哈希已核验，详见 [集成核验记录](e11e12/CI_RECORD.md)。"),
        ],
        "docs/e11e12/README.md": [
            ("原始 data/ 与 work/ 独立归档，最终 PR/CI 的运行编号、链接和提交 SHA 在 CI 取证时保存。",
             "- [集成 CI 与客户端原件核验](CI_RECORD.md)\n\n"
             "原始 data/ 与 work/ 独立归档。实现提交及 CI 已取证，最终交付提交与后续 CI 运行记录随归档保存。"),
        ],
        "docs/e11e12/PR_BODY.md": [
            ("本集成仓库 CI 由当前 PR 检查另行验收。",
             "原集成仓库 PR #4 的实现提交 `936ebe6` 已通过 E7、E8–E10、E11–E12 的 push/PR 共六项检查。"),
            ("分机环节由 A 组本人在 Windows 与服务器间通过 SSH 转发替代演练，B 方未参与。",
             "分机演练由 A 组本人在 Windows 与服务器间通过 SSH 转发完成，B 方未参与。\n"
             "六份客户端原始文件已回传并通过 SHA256 校验，记录：work/e12-crosshost-client/verification.json。"),
            ("文档：docs/个人报告.md、docs/ADR.md、docs/接口契约.md、docs/e11e12-build-log-stats-contract.md。",
             "文档：docs/个人报告.md、docs/ADR.md、docs/接口契约.md、docs/e11e12-build-log-stats-contract.md、docs/e11e12/CI_RECORD.md。"),
        ],
    }
    documents = {}
    for relative, pairs in replacements.items():
        text = (root / relative).read_text(encoding="utf-8")
        for old, new in pairs:
            text = update_text(text, old, new, relative)
        documents[relative] = text

    lines = ["# E11–E12 集成 CI 与客户端原件核验", "",
             f"集成 PR：[第 4 号]({PR_URL})。", f"已核验的实现提交：`{IMPLEMENTATION}`。", "",
             "## CI 运行", "", "|工作流|事件|运行|结果|", "|---|---|---|---|"]
    for run in sorted(runs.values(), key=lambda r: (r["workflowName"], r["event"])):
        lines.append(f"|{run['workflowName']}|{run['event']}|[{run['databaseId']}]({run['url']})|completed / success|")
    lines += ["", "三类工作流的 push 与 pull_request 共六项检查全部通过，headSha 均与上述实现提交一致。",
              "原始运行清单：`work/ci-e11e12/runs.json`；PR 快照：`work/ci-e11e12/pr-4.json`。",
              "PR 的三份运行产物和日志已下载，核验收据为 `work/ci-e11e12/evidence.json`；收据保存下载位置和阶段显式产物 SHA256。", "",
              "## 门禁与阶段结果", "", "- E7：8 个用例通过。", "- E8–E10：A 轨道 30 行、B 轨道 3 行通过。",
              "- E11–E12：阶段顺序、封装版本、job_id/trace_id、基线/目标提交与显式产物哈希核验通过；B/E12 复验的五项检查均为 true，最终无 MISSING。", "",
              "|CI 模式|job_id|结果|", "|---|---|---|"]
    lines += [f"|{mode}|`{job}`|SUCCEEDED|" for mode, job in JOBS.items()]
    lines += ["", "这里的 E11-B 是 CI 执行的独立模式，不代表 B 方同学参与了分机演练。", "",
              "## Windows 原始客户端文件", "",
              "A 组本人使用 Windows 客户端，经 SSH 转发访问 Linux 服务器；B 方未参与。",
              "原件已回传 `work/e12-crosshost-client/`，六个文件与 Windows 原件的 SHA256 逐一匹配。",
              f"job_id：`{CLIENT_JOB}`；trace_id：`{CLIENT_TRACE}`。",
              f"补丁 SHA256：`{PATCH_SHA}`。",
              "核验收据：`work/e12-crosshost-client/verification.json`。", "",
              "## 交付版本", "",
              "上述六项 CI 对应已存在的实现提交。本次补齐文档后的最终提交 SHA、后续 CI 运行记录及合并 SHA 在归档阶段另存，避免报告自引用提交 SHA。",
              "data/ 与 work/ 按手册独立归档；本记录不把尚未发生的文档补全提交 CI 或合并写作已完成。", ""]
    record_path = "docs/e11e12/CI_RECORD.md"
    record_text = "\n".join(lines)
    target = root / record_path
    require(not target.exists() or target.read_text(encoding="utf-8") == record_text,
            "Preserve the existing custom CI_RECORD.md before merging")
    documents[record_path] = record_text

    changed = {relative: text.encode("utf-8") for relative, text in documents.items()
               if not (root / relative).exists() or (root / relative).read_bytes() != text.encode("utf-8")}
    for relative, content in changed.items():
        require(not any(line.rstrip(b" \t\r") != line for line in content.split(b"\n")),
                f"Trailing whitespace in generated document: {relative}")
    if dry_run:
        print(json.dumps({"implementation": IMPLEMENTATION, "changed": list(changed)}, ensure_ascii=False, indent=2))
        print("FINAL_DOCUMENTS_DRY_RUN_PASS")
        return
    backup = None
    if changed:
        backup = Path(tempfile.mkdtemp(prefix="e11e12-final-docs-", dir=root / "work"))
        for relative, content in changed.items():
            target = root / relative
            if target.exists():
                original = backup / relative
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, original)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    receipt = {"implementation": IMPLEMENTATION, "pr_url": PR_URL,
               "backup": str(backup) if backup else None, "changed": list(changed),
               "verified_ci_stage_artifacts": len(hashes), "verified_client_files": len(client_hashes),
               "generated_sha256": {relative: sha(root / relative) for relative in documents}}
    receipt_path = root / "work/e11e12-final-docs-receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print("FINAL_DOCUMENTS_READY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    finalize(args.lab_root, args.dry_run)
