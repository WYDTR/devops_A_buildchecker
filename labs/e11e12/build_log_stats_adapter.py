"""Behaviour-based MDFixer validation for build-log-stats-v1; Python stdlib only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def make_command():
    for name in ("make", "mingw32-make"):
        path = shutil.which(name)
        if path:
            return path
    raise ValueError("GNU Make is required")


def executable(project):
    return project / ("app.exe" if os.name == "nt" else "app")


def run(command, cwd, log, timeout=120):
    process = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                             errors="replace", timeout=timeout)
    log.write_text(process.stdout + process.stderr, encoding="utf-8")
    if process.returncode:
        raise ValueError(f"Command exited {process.returncode}; see {log.name}")
    return process.stdout


def validate_build_log_stats(project, patchfile, evidence):
    project, patchfile, evidence = map(lambda p: Path(p).resolve(),
                                        (project, patchfile, evidence))
    if evidence == project or project in evidence.parents:
        raise ValueError("Validation evidence must be outside the source project")
    if evidence.exists() and any(evidence.iterdir()):
        raise ValueError("Use a fresh validation directory")
    evidence.mkdir(parents=True, exist_ok=True)
    before = (project / "Makefile").read_bytes()
    checks, error = {}, None
    sandbox = evidence / "sandbox"
    try:
        if any(path.is_symlink() for path in project.rglob("*")):
            raise ValueError("Symlink fixtures are unsupported")
        shutil.copytree(project, sandbox, ignore=shutil.ignore_patterns(
            ".git", "app", "app.exe", "*.o", "work", "__pycache__", ".env", ".env.*"))
        make = make_command()
        run(["git", "init", "-b", "main"], sandbox, evidence / "git-init.log")
        run(["git", "apply", "--check", str(patchfile)], sandbox, evidence / "patch-check.log")
        run(["git", "apply", str(patchfile)], sandbox, evidence / "patch-apply.log")
        checks["patch_applies"] = True
        run([make, "clean", "app"], sandbox, evidence / "build.log")
        checks["build"] = True
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_cli.py", "-v"], sandbox, evidence / "test.log")
        app = executable(sandbox)
        command = [str(app), "--json", "tests/fixtures/compiler.log"]
        original_stats = json.loads(run(command, sandbox, evidence / "program-before.log"))
        checks["test"] = original_stats == {
            "lines": 9, "warnings": 2, "errors": 2, "notes": 2}

        header = sandbox / "rules.h"
        text = header.read_text(encoding="utf-8")
        old, new = "#define LOG_STATS_COUNT_NOTES 1", "#define LOG_STATS_COUNT_NOTES 0"
        if text.count(old) != 1:
            raise ValueError("Expected the default note-counting rule")
        helper_time = (sandbox / "helper.o").stat().st_mtime_ns
        main_time = (sandbox / "main.o").stat().st_mtime_ns
        time.sleep(1.05)
        header.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        run([make, "app"], sandbox, evidence / "incremental.log")
        changed_stats = json.loads(run(command, sandbox, evidence / "program-after.log"))
        checks["header_change"] = (
            changed_stats == dict(original_stats, notes=0)
            and (sandbox / "helper.o").stat().st_mtime_ns > helper_time
            and (sandbox / "main.o").stat().st_mtime_ns == main_time
        )
        report = json.loads(run([sys.executable, "scripts/check_dependencies.py", "--json"],
                                sandbox, evidence / "dependency-check.log"))
        checks["no_missing"] = not any(
            finding["type"] == "MISSING" for finding in report["findings"])
        (evidence / "recheck.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc)
    accepted = error is None and len(checks) == 5 and all(checks.values())
    if accepted:
        (project / "Makefile").write_bytes((sandbox / "Makefile").read_bytes())
    unchanged = (project / "Makefile").read_bytes() == before
    result = {
        "accepted": accepted, "checks": checks, "error": error,
        "source_unchanged": unchanged, "rollback": not accepted and unchanged,
        "profile": "build-log-stats-v1",
        "input_patch_sha256": hashlib.sha256(patchfile.read_bytes()).hexdigest(),
    }
    (evidence / "validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
