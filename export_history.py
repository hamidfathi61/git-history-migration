
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path



if len(sys.argv) < 3:
    print("Usage: python export_history.py <history.json> <target_path>")
    sys.exit(1)


INPUT_FILE = Path(sys.argv[1]).resolve()

if not INPUT_FILE.is_file():
    print(f"Input file not found: {INPUT_FILE}")
    sys.exit(1)


FILE_NAME = INPUT_FILE.stem

input_path = Path(sys.argv[2]).resolve()

repo_root = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True
    ).strip()
).resolve()

try:
    TARGET_PATH = input_path.relative_to(repo_root).as_posix()
except ValueError:
    TARGET_PATH = Path(sys.argv[2]).as_posix()

OUTPUT_BUNDLE = FILE_NAME + ".bundle"
BRANCH_NAME = "file-history"


def git(repo, *args, input_data=None):
    result = subprocess.run(
        ["git", "-C", repo, *args],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Git command failed:\n"
            + " ".join(args)
            + "\n"
            + result.stderr.decode("utf-8", errors="replace")
        )

    return result.stdout



class CatFileBatch:

    def __init__(self, repo):
        self.proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=-1
        )

    def read_exact(self, size):
        chunks = []
        remaining = size

        while remaining > 0:
            chunk = self.proc.stdout.read(remaining)

            if not chunk:
                raise RuntimeError(
                    "Unexpected EOF while reading Git object. "
                    "Expected {} more bytes.".format(remaining)
                )

            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks)

    def read(self, sha):
        self.proc.stdin.write(sha.encode("ascii") + b"\n")
        self.proc.stdin.flush()

        header = self.proc.stdout.readline()

        if not header:
            raise RuntimeError(
                "cat-file process terminated unexpectedly."
            )

        parts = header.decode("ascii").strip().split()

        if len(parts) == 2 and parts[1] == "missing":
            return None

        if len(parts) != 3:
            raise RuntimeError(
                "Invalid cat-file response: " + repr(header)
            )

        size = int(parts[2])

        data = self.read_exact(size)

        separator = self.read_exact(1)

        if separator != b"\n":
            raise RuntimeError(
                "Invalid cat-file object separator."
            )

        return data

    def close(self):
        if self.proc is None:
            return

        self.proc.stdin.close()
        return_code = self.proc.wait()

        self.proc.stdout.close()
        self.proc = None

        if return_code != 0:
            raise RuntimeError("cat-file process failed.")

    def __init__(self, repo):
        self.proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def read(self, sha):
        self.proc.stdin.write(sha.encode("ascii") + b"\n")
        self.proc.stdin.flush()

        header = self.proc.stdout.readline()

        if not header:
            raise RuntimeError("cat-file process terminated unexpectedly.")

        parts = header.decode("ascii").strip().split()

        if len(parts) == 2 and parts[1] == "missing":
            return None

        if len(parts) != 3:
            raise RuntimeError(
                "Invalid cat-file response: " + repr(header)
            )

        size = int(parts[2])
        data = self.proc.stdout.read(size)

        if len(data) != size:
            raise RuntimeError("Incomplete object received from cat-file.")

        separator = self.proc.stdout.read(1)

        if separator != b"\n":
            raise RuntimeError("Invalid cat-file object separator.")

        return data

    def close(self):
        if self.proc is None:
            return

        self.proc.stdin.close()
        return_code = self.proc.wait()

        self.proc.stdout.close()
        self.proc = None

        if return_code != 0:
            raise RuntimeError("cat-file process failed.")


def get_parents(all_parents, commit_hash):
    return all_parents.get(commit_hash, [])


def nearest_selected_ancestors(
    commit_hash,
    selected,
    all_parents,
    cache
):
    if commit_hash in selected:
        return [commit_hash]

    if commit_hash in cache:
        return cache[commit_hash]

    result = []
    result_set = set()
    visited = set()
    stack = [commit_hash]

    while stack:
        current = stack.pop()

        if current in visited:
            continue

        visited.add(current)

        if current in selected:
            if current not in result_set:
                result_set.add(current)
                result.append(current)

            continue

        if current in cache:
            for ancestor in cache[current]:
                if ancestor not in result_set:
                    result_set.add(ancestor)
                    result.append(ancestor)

            continue

        parents = get_parents(all_parents, current)

        stack.extend(reversed(parents))

    cache[commit_hash] = result

    return result


def find_file(repo, commit_hash, paths):
    output = git(
        repo,
        "ls-tree",
        "-z",
        commit_hash,
        "--",
        *paths
    )

    found = {}

    for entry in output.decode(
        "utf-8",
        errors="replace"
    ).split("\0"):

        if not entry:
            continue

        meta, path = entry.split("\t", 1)
        parts = meta.split()

        if len(parts) == 3 and parts[1] == "blob":
            found[path] = (parts[0], parts[2])

    # اولویت مسیرها مطابق ترتیب paths حفظ می‌شود.
    for path in paths:
        if path in found:
            return found[path]

    return None


def build_file_tree(repo, blob_info):
    if blob_info is None:
        current_tree = git(
            repo,
            "mktree",
            input_data=b""
        ).decode().strip()

        return current_tree

    mode, blob_hash = blob_info

    file_name = TARGET_PATH.split("/")[-1]
    directories = TARGET_PATH.split("/")[:-1]

    current_tree = git(
        repo,
        "mktree",
        input_data=(
            mode.encode("ascii")
            + b" blob "
            + blob_hash.encode("ascii")
            + b"\t"
            + file_name.encode("utf-8")
            + b"\n"
        )
    ).decode().strip()

    for directory in reversed(directories):
        current_tree = git(
            repo,
            "mktree",
            input_data=(
                b"040000 tree "
                + current_tree.encode("ascii")
                + b"\t"
                + directory.encode("utf-8")
                + b"\n"
            )
        ).decode().strip()

    return current_tree


def parse_signature(line):
    match = re.match(
        r"^(.*) <(.*)> ([0-9]+) ([+-][0-9]{4})$",
        line
    )

    if not match:
        raise RuntimeError(
            "Cannot parse commit signature: " + line
        )

    return match.groups()


def parse_commit_metadata(content):
    if b"\n\n" not in content:
        raise RuntimeError("Invalid commit object.")

    headers, message = content.split(b"\n\n", 1)

    author = None
    committer = None

    for line in headers.decode(
        "utf-8",
        errors="replace"
    ).splitlines():

        if line.startswith("author "):
            author = line[7:]

        elif line.startswith("committer "):
            committer = line[10:]

    if author is None or committer is None:
        raise RuntimeError("Commit metadata is incomplete.")

    return author, committer, message


def make_commit(
    source_repo,
    temp_repo,
    batch,
    original_hash,
    parent_hashes,
    paths
):
    content = batch.read(original_hash)

    if content is None:
        raise RuntimeError(
            "Commit not found: " + original_hash
        )

    author, committer, message = parse_commit_metadata(content)

    blob_info = find_file(
        source_repo,
        original_hash,
        paths
    )

    if blob_info is not None:
        mode, blob_hash = blob_info

        blob_data = batch.read(blob_hash)

        if blob_data is None:
            raise RuntimeError(
                "Blob not found: " + blob_hash
            )

        new_blob_hash = git(
            temp_repo,
            "hash-object",
            "-w",
            "--stdin",
            input_data=blob_data
        ).decode().strip()

        blob_info = (mode, new_blob_hash)

    tree_hash = build_file_tree(
        temp_repo,
        blob_info
    )

    author_values = parse_signature(author)
    committer_values = parse_signature(committer)

    environment = os.environ.copy()

    environment["GIT_AUTHOR_NAME"] = author_values[0]
    environment["GIT_AUTHOR_EMAIL"] = author_values[1]
    environment["GIT_AUTHOR_DATE"] = (
        author_values[2] + " " + author_values[3]
    )

    environment["GIT_COMMITTER_NAME"] = committer_values[0]
    environment["GIT_COMMITTER_EMAIL"] = committer_values[1]
    environment["GIT_COMMITTER_DATE"] = (
        committer_values[2] + " " + committer_values[3]
    )

    command = [
        "git",
        "-C",
        temp_repo,
        "commit-tree",
        tree_hash
    ]

    for parent in parent_hashes:
        command.extend(["-p", parent])

    result = subprocess.run(
        command,
        input=message,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="replace")
        )

    return result.stdout.decode().strip()


def main():
    if len(sys.argv) != 3:
        print("Usage: python export_history.py history.json")
        sys.exit(1)

    history_file = os.path.abspath(sys.argv[1])
    source_repo = str(repo_root)

    with open(
        history_file,
        "r",
        encoding="utf-8"
    ) as file:
        history = json.load(file)

    selected_commits = history["commits"]

    selected_hashes = {
        item["hash"] if isinstance(item, dict) else item
        for item in selected_commits
    }

    source_head = history["head"]

    paths = [TARGET_PATH]

    for rename in history.get("rename_history", []):
        old_path = rename.get("old_path")
        new_path = rename.get("new_path")

        if old_path and old_path not in paths:
            paths.append(old_path)

        if new_path and new_path not in paths:
            paths.append(new_path)

    initial_path = history.get("initial_path")

    if initial_path and initial_path not in paths:
        paths.append(initial_path)

    print("Selected commits:", len(selected_hashes))
    print("Historical paths:", len(paths))
    print("Collecting commit graph...", flush=True)

    # تمام گراف والدها فقط با یک دستور خوانده می‌شود.
    output = git(
        source_repo,
        "rev-list",
        "--parents",
        "--reverse",
        "--topo-order",
        source_head
    ).decode()

    all_parents = {}
    all_commits = []

    for line in output.splitlines():
        parts = line.split()

        if not parts:
            continue

        commit_hash = parts[0]

        all_commits.append(commit_hash)
        all_parents[commit_hash] = parts[1:]

    print("Graph commits:", len(all_commits), flush=True)

    ordered_commits = [
        commit
        for commit in all_commits
        if commit in selected_hashes
    ]

    if len(ordered_commits) != len(selected_hashes):
        missing = selected_hashes - set(ordered_commits)

        raise RuntimeError(
            "Some selected commits are not reachable from HEAD:\n"
            + "\n".join(sorted(missing))
        )

    print("Selected commits in graph:", len(ordered_commits))
    print("Analyzing parent relationships...", flush=True)

    selected = set(ordered_commits)
    ancestor_cache = {}
    parent_map = {}

    for index, commit_hash in enumerate(ordered_commits, 1):
        selected_parents = []
        seen = set()

        for parent in get_parents(all_parents, commit_hash):
            ancestors = nearest_selected_ancestors(
                parent,
                selected,
                all_parents,
                ancestor_cache
            )

            for ancestor in ancestors:
                if ancestor not in seen:
                    seen.add(ancestor)
                    selected_parents.append(ancestor)

        parent_map[commit_hash] = selected_parents

        if index % 25 == 0 or index == len(ordered_commits):
            print(
                "Analyzed: {}/{}".format(
                    index,
                    len(ordered_commits)
                ),
                flush=True
            )

    referenced_parents = set()

    for parents in parent_map.values():
        referenced_parents.update(parents)

    tips = [
        commit
        for commit in ordered_commits
        if commit not in referenced_parents
    ]

    if len(tips) != 1:
        raise RuntimeError(
            "Expected exactly one history tip, found: "
            + str(len(tips))
            + "\nTips:\n"
            + "\n".join(tips)
        )

    print("History graph analyzed successfully.")
    print("Building filtered history...", flush=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_repo = os.path.join(temp_dir, "repo")

        os.makedirs(temp_repo)

        git(temp_repo, "init", "--quiet")

        batch = CatFileBatch(source_repo)

        try:
            rebuilt = {}

            for index, original_hash in enumerate(
                ordered_commits,
                1
            ):
                new_parents = [
                    rebuilt[parent]
                    for parent in parent_map[original_hash]
                ]

                new_hash = make_commit(
                    source_repo,
                    temp_repo,
                    batch,
                    original_hash,
                    new_parents,
                    paths
                )

                rebuilt[original_hash] = new_hash

                if index % 10 == 0 or index == len(ordered_commits):
                    print(
                        "Rebuilt: {}/{}".format(
                            index,
                            len(ordered_commits)
                        ),
                        flush=True
                    )

        finally:
            batch.close()

        new_head = rebuilt[tips[0]]

        git(
            temp_repo,
            "update-ref",
            "refs/heads/" + BRANCH_NAME,
            new_head
        )

        actual_count = int(
            git(
                temp_repo,
                "rev-list",
                "--count",
                new_head
            ).decode().strip()
        )

        if actual_count != len(selected_hashes):
            raise RuntimeError(
                "History count mismatch. Expected "
                + str(len(selected_hashes))
                + ", got "
                + str(actual_count)
            )

        bundle_path = os.path.join(
            os.path.dirname(history_file),
            OUTPUT_BUNDLE
        )

        git(
            temp_repo,
            "bundle",
            "create",
            bundle_path,
            "refs/heads/" + BRANCH_NAME
        )

        git(
            temp_repo,
            "bundle",
            "verify",
            bundle_path
        )

    print()
    print("========== EXPORT COMPLETED ==========")
    print("Original commits :", len(selected_hashes))
    print("Exported commits :", actual_count)
    print("New HEAD         :", new_head)
    print("Target path      :", TARGET_PATH)
    print("Bundle           :", bundle_path)
    print(
        "Bundle size      :",
        os.path.getsize(bundle_path),
        "bytes"
    )


if __name__ == "__main__":
    main()
