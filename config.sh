#!/usr/bin/env bash

PYTHON="/c/Python/Python314/python"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SOURCE_REPO="/c/project/res-history"
DEST_REPO="/c/project/webjars"


FILES_JSON="$SCRIPT_DIR/file.json"
BUNDLE_DIR="$SCRIPT_DIR/bundles"

TARGET_BRANCH="main"
PUSH=0
