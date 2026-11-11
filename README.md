# Smart File Organizer

## 中文简介

这是一个小型 Python 命令行工具，用来把杂乱文件夹里的文件按**类型**、**修改日期**或**大小**移动到子文件夹。请先用 `--dry-run` 预览。移动不是事务：中途失败时，已经完成的移动会保留。加上 `--manifest` 会把实际移动写成清单，之后可以用 `--undo` 移回原处。需要 Python 3.8 或更新版本。

A small Python command-line tool that moves files into folders by extension,
modification date, or size. Preview the moves before applying them.

## Install from source

Requires Python 3.8 or newer and Click. These instructions install this repository;
no PyPI release is assumed.

```bash
git clone https://github.com/Master-626/smart-file-organizer.git
cd smart-file-organizer
python -m pip install .
organize --help
```

## Start with a preview

```bash
organize ~/Downloads --by type --dry-run --verbose
# Review the destinations, then apply:
organize ~/Downloads --by type
```

Use a disposable folder or a backup for your first run. Without `--manifest`,
moves are not undoable through this tool.

```bash
organize ~/Downloads --by date --dry-run
organize ~/Downloads --by size --dry-run
organize ~/Downloads --by type --recursive --dry-run --verbose
```

Record an applied run, then move those files back. Put the manifest **outside**
the folder you are organizing:

```bash
organize ~/Downloads --by type --manifest ~/downloads-moves.jsonl
organize --undo ~/downloads-moves.jsonl --dry-run
organize --undo ~/downloads-moves.jsonl
```

## Options

```text
organize PATH [OPTIONS]
organize --undo MANIFEST [--dry-run] [--verbose]

--by [type|date|size]  Organization method (default: type)
--dry-run             Preview without creating folders or moving files
--recursive           Include files in visible subdirectories
-v, --verbose         Show full destination paths relative to PATH
--manifest FILE       Write each applied move as JSON Lines for --undo
--undo FILE           Move files back using a manifest from --manifest
--version             Show the version
--help                Show help
```

`--undo` does not take a target directory, `--manifest`, `--recursive`, or `--by`.
It accepts `--dry-run` and `--verbose`. `--config` and week-based grouping are
not implemented.

## Organization rules

- **Type:** Documents, Images, Videos, Audio, Code, Archives, Executables, Fonts,
  or Others, using the final filename extension, case-insensitively. For example,
  `notes.txt` goes into `Documents/`, `photo.JPG` into `Images/`, and `bundle.tar.gz`
  into `Archives/`. The full mapping is in `file_organizer/organizer.py`.
- **Date:** `YEAR/MM/` from the file's modification time, in your local timezone.
- **Size:** `Small/` for less than 1 MiB, `Medium/` for 1 MiB to less than 100 MiB,
  and `Large/` for 100 MiB or more. One MiB is 1,048,576 bytes.

Recursive mode flattens matching files into the target's category folders; it
leaves empty source directories in place. Files already directly in their correct
folder are left alone, so repeating the same run does not rename them. Changing
methods or custom categories can move previously organized files again.

### Safety behavior and limits

- Discovery and destination validation finish before any moves begin.
- Dot-prefixed files and directories, symbolic links, Windows reparse points, and non-regular files are
  skipped. This refers to dot-prefixed names, not Windows' hidden-file attribute.
- Targets and destination directories containing symbolic links or Windows reparse
  points are rejected.
- Existing files, directories, and dangling links are never intentionally replaced.
  Collisions get `_1`, `_2`, and so on before the final extension. Dry runs reserve
  these names too, comparing planned destinations case-insensitively and with
  Unicode normalization, so previews are consistent when the directory stays
  unchanged. This may add suffixes unnecessarily on case-sensitive filesystems.
- Files are copied to an exclusively created destination, metadata is copied where
  supported, and only then is the source removed. On POSIX, new copies start with
  restrictive `0600` permissions before the original mode is restored. This needs extra disk space and
  can be slower for large files. Filesystem metadata such as ownership, ACLs, and
  alternate data streams may not be preserved. Back up important data first.
- A run is **not transactional**. On a permission error, full disk, or interruption,
  earlier moves remain applied; interruption can leave a partial destination or
  duplicate copies. Inspect both locations before retrying. `--manifest` appends
  each move as it succeeds, so a partial manifest can be undone.
- A collision suffix that would exceed the filesystem's file-name limit raises
  `ValueError` during planning. Dry runs and real runs both stop before moving
  any file. `os.path.lexists` alone is not enough: it returns false for an
  over-long name, which used to let a preview succeed and then fail mid-run.
- If a date folder is blocked by a file or a symlink (for example a file named
  `2020` when another file belongs in `2020/01`), planning raises `ValueError`
  before any move. The message names the blocking path.
- Use only on folders you control, with no concurrent writers or other organizer
  runs. Path checks do not protect against an adversary replacing directories or
  files between validation and use. This is not a security sandbox. Do not point
  `--undo` at a manifest you do not trust.

Older code used size folders named `Small (<1MB)`, `Medium (1MB-100MB)`, and
`Large (>100MB)`. Those names are invalid on Windows. This version uses the portable
names above; `--recursive --by size` can move files from the old folders on systems
where those folders exist. Preview first.

## Custom extension categories (Python API)

There is no configuration-file loader. Python callers can supply a mapping:

```python
from pathlib import Path
from file_organizer.organizer import organize_by_type

moves = organize_by_type(
    Path("Downloads"),
    categories={"Reading": [".pdf", ".epub"], "Photos": [".jpg", ".png"]},
    dry_run=True,
)
for source, destination in moves:
    print(source, "->", destination)
```

Category names must be plain, non-hidden folder names, not paths. Unmatched files
use `Others`. Returned paths are absolute. Invalid categories or destinations raise
`ValueError`; filesystem failures raise `OSError`. The CLI reports these errors and
exits unsuccessfully.

## Undo manifest

`--manifest` cannot be combined with `--dry-run`. Each line is one JSON object,
`{"v": 1, "src": "<absolute original>", "dst": "<absolute new path>"}`.
The file is created only after planning succeeds, outside the target directory,
and is not overwritten. `--undo` reads that file, checks every record, then moves
destinations back in reverse order without replacing existing files. The manifest
is left in place. A manifest is trusted input: it can name any regular file the
user is allowed to move, but symlink destinations and occupied original paths are
rejected.

```python
from pathlib import Path
from file_organizer.organizer import organize_by_type, undo_manifest

organize_by_type(Path("Downloads"), manifest=Path("/tmp/downloads-moves.jsonl"))
undo_manifest(Path("/tmp/downloads-moves.jsonl"), dry_run=True)
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

`pytest` runs the `unittest` suite in `tests/test_organizer.py` and the cases in
`tests/test_core.py`. CI lints with Ruff, then runs pytest on Python 3.8 on Linux
and on 3.9–3.14 (3.12+ also on Windows and macOS). Symlink tests skip if the
operating system does not permit creating links. The filename-limit tests skip
when the filesystem cannot create a name of that length.

Contributions with reproducible bug reports and regression tests are welcome.

## License

[MIT](LICENSE).
