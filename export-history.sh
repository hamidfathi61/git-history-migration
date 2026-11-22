
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

[[ -d "$SOURCE_REPO" ]] || fail "Source repository not found: $SOURCE_REPO"
[[ -f "$FILES_JSON" ]] || fail "JSON file not found: $FILES_JSON"

cd "$SOURCE_REPO"

[[ -f "$SCRIPT_DIR/trace.py" ]] || fail "trace.py not found."
[[ -f "$SCRIPT_DIR/export_history.py" ]] || fail "export_history.py not found."

mkdir -p "$BUNDLE_DIR"

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
echo " Exporting $COUNT file histories"
echo "======================================"

# --------------------------------------------------
# Export each file
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
    HISTORY_NAME="${FILE_NAME}-${HASH}.json"

    BUNDLE_PATH="$BUNDLE_DIR/$BUNDLE_NAME"
    HISTORY_JSON="$BUNDLE_DIR/$HISTORY_NAME"

    echo
    echo "--------------------------------------"
    echo "[$((i+1))/$COUNT] $SOURCE"
    echo "Target: $TARGET"
    echo "--------------------------------------"

    [[ -f "$SOURCE" ]] || fail "Source file not found: $SOURCE"

    # Extract history
    echo
    echo "[1/4] Extracting history..."

    "$PYTHON" "$SCRIPT_DIR/trace.py" "$SOURCE" "$BUNDLE_DIR" "$HISTORY_NAME"

    [[ -f "$HISTORY_JSON" ]] \
        || fail "History JSON not created: $HISTORY_JSON"

    # Remove previous bundle
    rm -f "$BUNDLE_PATH"

    # Build bundle
    echo
    echo "[2/4] Building bundle..."

	"$PYTHON" "$SCRIPT_DIR/export_history.py" "$HISTORY_JSON" "$TARGET"


    [[ -f "$BUNDLE_PATH" ]] \
        || fail "Bundle not created: $BUNDLE_PATH"

    # Verify bundle
    echo
    echo "[3/4] Verifying bundle..."

    VERIFY_DIR="$BUNDLE_DIR/.verify-$HASH"

    rm -rf "$VERIFY_DIR"

    git clone --quiet --branch file-history \
        "$BUNDLE_PATH" \
        "$VERIFY_DIR"

    git -C "$VERIFY_DIR" fsck --full

    COMMIT_COUNT="$(git -C "$VERIFY_DIR" rev-list --count HEAD)"

    rm -rf "$VERIFY_DIR"

    # Result
    echo
    echo "[4/4] Completed."

    echo "Bundle       : $BUNDLE_NAME"
    echo "History JSON : $HISTORY_NAME"
    echo "Target       : $TARGET"
    echo "Commit count : $COMMIT_COUNT"

done

# --------------------------------------------------
# Finish
# --------------------------------------------------

echo
echo "======================================"
echo " All bundles exported successfully"
echo "======================================"

echo
echo "Bundle directory: $BUNDLE_DIR"
