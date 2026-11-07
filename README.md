# Smart File Organizer

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

Use a disposable folder or a backup for your first run. Moves are **not undoable**
through this tool, and no persistent move log is saved.

```bash
organize ~/Downloads --by date --dry-run
organize ~/Downloads --by size --dry-run
organize ~/Downloads --by type --recursive --dry-run --verbose
```

## Options

```text
organize PATH [OPTIONS]

--by [type|date|size]  Organization method (default: type)
--dry-run             Preview without creating folders or moving files
--recursive           Include files in visible subdirectories
-v, --verbose         Show full destination paths relative to PATH
--version             Show the version
--help                Show help
```

`--config`, `--undo`, and week-based grouping are not implemented.

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
  duplicate copies. Inspect both locations before retrying.
- Use only on folders you control, with no concurrent writers or other organizer
  runs. Path checks do not protect against an adversary replacing directories or
  files between validation and use. This is not a security sandbox.

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

## Development

```bash
python -m pip install .
python -m unittest discover -s tests -v
```

Tests use temporary folders and Python's standard library `unittest`. CI is
configured for Python 3.8 on Linux and 3.12, 3.13, and 3.14 on Linux, Windows,
and macOS; symlink
tests skip if the operating system does not permit creating links.

Contributions with reproducible bug reports and regression tests are welcome.

## License

[MIT](LICENSE).
