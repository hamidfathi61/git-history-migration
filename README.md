# Git History Migration

A lightweight tool for exporting selected file histories from a source Git repository and importing them into a target Git repository.

## Requirements

- Git
- Python 3
- Bash (Windows users should use Git Bash)

Make sure Python is installed and its executable path is correctly configured in `config.sh`.

These settings are global and only need to be configured once per machine.

## Limitations

This tool reconstructs and migrates file-related Git history. However, it does not guarantee that every historical commit will be identified or migrated.

Depending on the repository's history structure, file renames, moves, or other historical changes, some commits may not be included. In most cases, a substantial portion of the relevant file history can be recovered.

The migration approach was developed with reference to file history displayed by IntelliJ IDEA, but the resulting history is not guaranteed to match IntelliJ IDEA exactly.

## How to Run

### 1. Set execution permissions

Run the following command in Git Bash:

```bash
chmod +x export-history.sh import-history.sh
```

### 2. Configure paths and settings

Edit `config.sh` and configure the following values:

- `SOURCE_REPO`: Path to the source Git repository.
- `DEST_REPO`: Path to the target Git repository.
- `TARGET_BRANCH`: Target branch where histories will be imported.
- `PYTHON`: Path to the Python executable.
- `PUSH`: Set to `1` to push automatically, or `0` to skip pushing.

### 3. Define files to migrate

Edit `file.json` and specify the source and target paths for each file.

Example:

```json
{
  "files": [
    {
      "source": "src/main/java/Example.java",
      "target": "src/main/java/Example.java"
    }
  ]
}
```

### 4. Export file histories

Run:

```bash
./export-history.sh
```

This extracts the selected file histories and creates the corresponding JSON history files and Git bundles inside the `bundles` directory.

### 5. Import file histories

Run:

```bash
./import-history.sh
```

This imports the exported histories into the configured target branch.

**Important:** Make sure the target repository is clean and you are on the configured target branch before importing.

---

## Path Configuration Examples

Configure `SOURCE_REPO`, `DEST_REPO`, and `PYTHON` in `config.sh` according to your operating system.

**Windows (Git Bash)**

Run the scripts using Git Bash. Git for Windows must be installed.

```bash
SOURCE_REPO="/c/Users/xxx/projects/source-repo"
DEST_REPO="/c/Users/xxx/projects/target-repo"
PYTHON="/c/Python/Python314/python"
```

**Linux**

```bash
SOURCE_REPO="/home/xxx/projects/source-repo"
DEST_REPO="/home/xxx/projects/target-repo"
PYTHON="/usr/bin/python3"
```

**macOS**

```bash
SOURCE_REPO="/Users/xxx/projects/source-repo"
DEST_REPO="/Users/xxx/projects/target-repo"
PYTHON="/usr/bin/python3"
```

**Notes:**
- On Windows, use Git Bash and Unix-style paths (`/c/...`) instead of Windows-style paths (`C:\...`).
- On Linux and macOS, use absolute Unix-style paths.
- Make sure the configured Python executable exists and is accessible.
- Replace the example paths with your actual repository and Python installation paths.

## Credits

- **Author:** Hamid Fathi
- **Development assistance:** ChatGPT (OpenAI)

Built with a focus on simplicity, preserving Git history, and keeping the migration process reproducible.