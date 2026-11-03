from buildchecker.fullcheck import execution_graph


def test_rename_preserves_final_target_and_dependencies(tmp_path):
    traces = {
        "t.10": (
            'execve("/usr/bin/make", ["make"], []) = 0\n'
            'clone(child_stack=NULL, flags=SIGCHLD) = 11\n'
        ),
        "t.11": (
            'execve("/usr/bin/cc", ["cc"], []) = 0\n'
            'clone(child_stack=NULL, flags=SIGCHLD) = 12\n'
            'clone(child_stack=NULL, flags=SIGCHLD) = 13\n'
        ),
        "t.12": (
            'execve("/usr/bin/cc1", ["cc1"], []) = 0\n'
            'openat(AT_FDCWD, "unit.c", O_RDONLY) = 3\n'
            'openat(AT_FDCWD, "needed.h", O_RDONLY) = 4\n'
        ),
        "t.13": (
            'execve("/usr/bin/as", ["as"], []) = 0\n'
            'openat(AT_FDCWD, "unit.tmp", '
            'O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3\n'
            'rename("unit.tmp", "unit.o") = 0\n'
        ),
    }

    for name, content in traces.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    targets, _ = execution_graph(tmp_path, "/course/project")

    assert set(targets) == {"unit.o"}
    assert set(targets["unit.o"]["dependencies"]) == {
        "unit.c", "needed.h"
    }
    assert targets["unit.o"]["output_evidence"]["operation"] == "rename"
    assert targets["unit.o"]["processes"] == [11, 12, 13]
