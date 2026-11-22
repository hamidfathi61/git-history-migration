
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


if len(sys.argv) < 2:
    print("Usage: python trace.py <file-path>")
    sys.exit(1)


input_path = Path(sys.argv[1]).resolve()

repo_root = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True
    ).strip()
).resolve()

try:
    FILE_PATH = input_path.relative_to(repo_root).as_posix()
except ValueError:
    FILE_PATH = Path(sys.argv[1]).replace("\\", "/")

USE_FULL_HISTORY_SIMPLIFY_MERGES = True

def git(*args):
    result = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(error)

    return result.stdout


def decode(value):
    return value.decode("utf-8", errors="replace")


def get_history(commit, path):
    args = ["log", "--format=%H"]

    if USE_FULL_HISTORY_SIMPLIFY_MERGES:
        args += ["--full-history", "--simplify-merges"]

    args += [commit, "--", path]

    output = git(*args)

    return [
        line.strip()
        for line in decode(output).splitlines()
        if line.strip()
    ]


def get_follow_history(commit, path):
    """
    Use Git's native --follow to collect the complete
    file history across renames.
    """

    output = git(
        "log",
        "--full-history",
        "--follow",
        "--format=%H",
        commit,
        "--",
        path
    )

    return [
        line.strip()
        for line in decode(output).splitlines()
        if line.strip()
    ]


def get_parents(commit):
    output = decode(
        git("rev-list", "--parents", "-n", "1", commit)
    )

    parts = output.strip().split()
    return parts[1:]


def find_rename(commit, current_path):
    output = git(
        "show",
        "-M",
        "--name-status",
        "--format=",
        "-z",
        commit
    )

    parts = output.split(b"\0")
    i = 0

    while i < len(parts):
        status = decode(parts[i])

        if not status:
            i += 1
            continue

        i += 1

        if status.startswith(("R", "C")):
            old_path = decode(parts[i])
            new_path = decode(parts[i + 1])
            i += 2

            if status.startswith("R") and new_path == current_path:
                return old_path

        else:
            i += 1

    return None


def get_commit_info(commit):
    output = git(
        "show",
        "-s",
        "--format=%H%x00%ct%x00%an%x00%s",
        commit
    )

    parts = decode(output).rstrip("\n").split("\0", 3)

    return {
        "hash": parts[0],
        "timestamp": int(parts[1]),
        "date": datetime.fromtimestamp(
            int(parts[1])
        ).strftime("%Y-%m-%d %H:%M"),
        "author": parts[2],
        "subject": parts[3],
        "parents": get_parents(commit)
    }


def main():
    head = decode(git("rev-parse", "HEAD")).strip()

    current_path = FILE_PATH
    last_commit = head

    all_commits = {}
    rename_history = []

    # Collect complete history using Git's native --follow.
    follow_commits = get_follow_history(
        head,
        FILE_PATH
    )

    for commit in follow_commits:
        all_commits[commit] = None

    print(f"Git follow commits: {len(follow_commits)}")

    # Preserve the previous rename/path discovery logic.
    iteration = 0

    while current_path and last_commit:

        iteration += 1

        commits = get_history(last_commit, current_path)

        if not commits:
            break

        for commit in commits:
            all_commits[commit] = None

        first_commit = commits[-1]

        parents = get_parents(first_commit)

        if not parents:
            break

        first_parent = parents[0]

        previous_path = find_rename(
            first_commit,
            current_path
        )

        if previous_path is None:
            break

        rename_history.append({
            "commit": first_commit,
            "old_path": previous_path,
            "new_path": current_path
        })

        current_path = previous_path
        last_commit = first_parent

    result = []

    for commit in all_commits:
        result.append(get_commit_info(commit))

    result.sort(
        key=lambda item: item["timestamp"],
        reverse=True
    )

    data = {
        "head": head,
        "initial_path": FILE_PATH,
        "use_full_history_simplify_merges": USE_FULL_HISTORY_SIMPLIFY_MERGES,
        "total_commits": len(result),
        "rename_count": len(rename_history),
        "paths_visited": iteration,
        "rename_history": rename_history,
        "commits": result
    }

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent
    output_name = sys.argv[3] if len(sys.argv) > 3 else input_file.stem + ".json"

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / output_name

    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print()
    print("========== TRACE COMPLETED ==========")
    print(f"Git follow commits : {len(follow_commits)}")
    print(f"Total commits      : {len(result)}")
    print(f"Rename count       : {len(rename_history)}")
    print(f"Historical paths   : {iteration}")
    print(f"Output             : {output_file}")


if __name__ == "__main__":
    main()
