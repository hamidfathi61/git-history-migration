
#!/usr/bin/env bash

set -Eeuo pipefail

# --------------------------------------------------
# Configuration
# --------------------------------------------------

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.sh"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

fail() {
    echo
    echo "ERROR: $1"
    exit 1
}

# --------------------------------------------------
# Dependencies
# --------------------------------------------------

[[ -x "$PYTHON" ]] || fail "Python not found: $PYTHON"

echo "Python: $("$PYTHON" --version)"

# --------------------------------------------------
# Validation
# --------------------------------------------------

[[ -d "$DEST_REPO" ]] || fail "Destination repository not found: $DEST_REPO"
[[ -f "$FILES_JSON" ]] || fail "JSON file not found: $FILES_JSON"
[[ -d "$BUNDLE_DIR" ]] || fail "Bundle directory not found: $BUNDLE_DIR"

cd "$DEST_REPO"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || fail "Not a Git repository."

[[ "$(git branch --show-current)" == "$TARGET_BRANCH" ]] \
    || fail "Please switch to $TARGET_BRANCH"

[[ -z "$(git status --porcelain)" ]] \
    || fail "Working tree is not clean."

# --------------------------------------------------
# Validate JSON
# --------------------------------------------------

"$PYTHON" -c '
import json, sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

files = data.get("files")

if not isinstance(files, list) or not files:
    raise SystemExit("files must be a non-empty array")

for item in files:
    if not isinstance(item, dict):
        raise SystemExit("Each file must be an object")

    if not isinstance(item.get("source"), str) or not item["source"].strip():
        raise SystemExit("Each file needs a valid source")

    if not isinstance(item.get("target"), str) or not item["target"].strip():
        raise SystemExit("Each file needs a valid target")
' "$FILES_JSON" || fail "Invalid JSON file: $FILES_JSON"

# --------------------------------------------------
# Read file list
# --------------------------------------------------

mapfile -d '' -t ITEMS < <(
    "$PYTHON" -c '
import json, sys

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

for item in data["files"]:
    sys.stdout.write(item["source"] + "\0")
    sys.stdout.write(item["target"] + "\0")
' "$FILES_JSON"
)

COUNT=$((${#ITEMS[@]} / 2))

echo
echo "======================================"
echo " Importing $COUNT file histories"
echo "======================================"

# --------------------------------------------------
# Import each file
# --------------------------------------------------

for ((i=0; i<COUNT; i++)); do

    SOURCE="${ITEMS[i*2]}"
    TARGET="${ITEMS[i*2+1]}"

    FILE_NAME="$(basename "$SOURCE")"
    FILE_NAME="${FILE_NAME%.*}"

    HASH=$("$PYTHON" -c '
import hashlib, sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:10])
' "$SOURCE")

    BUNDLE_NAME="${FILE_NAME}-${HASH}.bundle"
    BUNDLE="$BUNDLE_DIR/$BUNDLE_NAME"

    echo
    echo "--------------------------------------"
    echo "[$((i+1))/$COUNT] $SOURCE"
    echo "Target: $TARGET"
    echo "--------------------------------------"

    [[ -f "$BUNDLE" ]] || fail "Bundle not found: $BUNDLE"

    # Check temporary branches
    git show-ref --verify --quiet refs/heads/history \
        && fail "Branch history already exists. Resolve it first."

    git show-ref --verify --quiet refs/heads/migrate \
        && fail "Branch migrate already exists. Resolve it first."

    # Fetch history
    echo
    echo "[1/4] Fetching history..."

    git fetch "$BUNDLE" file-history:refs/heads/history

    git rev-list --count history

    # Create migration branch
    echo
    echo "[2/4] Creating migration branch..."

    git switch -c migrate "$TARGET_BRANCH"

    # Merge history
    echo
    echo "[3/4] Merging history..."

    if ! git merge --allow-unrelated-histories \
        --no-commit --no-ff history; then

        echo
        echo "MERGE FAILED OR CONFLICT DETECTED."
        echo
        echo "Current branch: migrate"
        echo "Resolve conflicts manually."
        echo "Branches migrate and history are preserved."
        exit 1
    fi

    git commit -m "Import history: $FILE_NAME"

    # Update $TARGET_BRANCH
    echo
    echo "[4/4] Updating $TARGET_BRANCH..."

    git switch "$TARGET_BRANCH"
    git merge --ff-only migrate

    # Cleanup temporary branches
    git branch -d migrate
    git branch -d history

    echo
    echo "Imported successfully: $FILE_NAME"

done

# --------------------------------------------------
# Push once
# --------------------------------------------------

if [[ "$PUSH" == "1" ]]; then
    echo
    echo "Pushing $TARGET_BRANCH..."
    git push origin "$TARGET_BRANCH"
fi

# --------------------------------------------------
# Finish
# --------------------------------------------------

echo
echo "======================================"
echo " All histories imported successfully"
echo "======================================"
