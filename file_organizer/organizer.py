"""
Core organization logic for Smart File Organizer.
"""
import json
import os
import shutil
import stat
import unicodedata
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Tuple

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".md", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".rtf", ".odt"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico", ".raw", ".heic"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff"],
    "Code": [".py", ".js", ".ts", ".html", ".css", ".scss", ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sql", ".json", ".xml", ".yml", ".yaml"],
    "Archives": [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz", ".iso"],
    "Executables": [".exe", ".msi", ".dmg", ".deb", ".rpm", ".apk"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2", ".eot"],
}


def _validate_categories(categories):
    if not isinstance(categories, dict):
        raise ValueError("Categories must be a dictionary of names and extension lists")
    for name, extensions in categories.items():
        if (not isinstance(name, str) or not name or name.startswith(".")
                or name.endswith((" ", "."))
                or any(c in name for c in '/\\<>:"|?*')
                or any(ord(c) < 32 for c in name)
                or PureWindowsPath(name).is_reserved()):
            raise ValueError("Category names must be safe, single folder names")
        if not isinstance(extensions, (list, tuple)) or any(
            not isinstance(ext, str) or not ext.startswith(".") or len(ext) < 2
            or any(c in ext for c in '/\\') for ext in extensions
        ):
            raise ValueError("Category extensions must be lists of dotted extensions")


def get_category(file_path: Path, categories=None) -> str:
    """Return a category for the final extension (case-insensitive)."""
    categories = DEFAULT_CATEGORIES if categories is None else categories
    _validate_categories(categories)
    ext = Path(file_path).suffix.lower()
    for category, extensions in categories.items():
        if ext in [value.lower() for value in extensions]:
            return category
    return "Others"


def _is_link(path):
    if path.is_symlink():
        return True
    # Windows junctions and other reparse points are not always symlinks.
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _check_directory(path):
    # Reject links at any level, including dangling ones. Never resolve them away.
    # Check the filesystem root first. A file or link blocking a missing child
    # (a file named "2020" when the destination is "2020/01", or a symlink to a
    # file) must raise ValueError. Probing the missing child first makes lstat()
    # raise NotADirectoryError and skips these checks.
    for component in reversed((path,) + tuple(path.parents)):
        if _is_link(component):
            raise ValueError("Symbolic-link directories are not supported: {}".format(component))
        if component.exists() and not component.is_dir():
            raise ValueError("Not a directory: {}".format(component))


def _snapshot(root, recursive):
    files = []
    def raise_walk_error(error):
        raise error
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=raise_walk_error):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".")
                         and not _is_link(Path(directory) / name))
        for name in sorted(names):
            item = Path(directory) / name
            if not name.startswith(".") and not _is_link(item) and item.is_file():
                files.append(item)
        if not recursive:
            break
    return sorted(files)


def _move_without_overwrite(source, destination):
    """Copy exclusively, preserve metadata, then remove the original.

    An occupied destination fails rather than replacing anyone else's data.
    This is not a transaction: interruption can leave both copies.
    """
    # Restrict permissions from creation, before any source bytes are written.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(destination, flags, 0o600)
    try:
        output = os.fdopen(descriptor, "wb")
    except BaseException:
        os.close(descriptor)
        destination.unlink()
        raise
    try:
        with output:
            with source.open("rb") as original:
                shutil.copyfileobj(original, output)
            output.flush()
            shutil.copystat(source, destination, follow_symlinks=False)
    except BaseException:
        destination.unlink()
        raise
    source.unlink()


def _reservation_key(path):
    # Be conservative across case-insensitive and Unicode-normalizing volumes,
    # even when planning on a case-sensitive host.
    return unicodedata.normalize("NFC", str(path)).casefold()


def _filename_limit(directory):
    """Return the filesystem's max single-component name length, if known."""
    probe = directory
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    statvfs = getattr(os, "statvfs", None)
    if statvfs is not None:
        try:
            return statvfs(probe).f_namemax
        except OSError:
            pass
    # Windows has no statvfs. The per-component limit is 255 characters.
    if os.name == "nt":
        return 255
    return None


def _name_exceeds_limit(name, limit):
    if limit is None:
        return False
    # POSIX NAME_MAX is a byte count. Windows counts Unicode characters.
    if os.name == "nt":
        return len(name) > limit
    return len(os.fsencode(name)) > limit


def _open_manifest(manifest):
    """Create a new manifest exclusively. Caller closes the stream."""
    path = Path(os.path.abspath(os.path.expanduser(str(manifest))))
    if _is_link(path) or path.exists():
        raise ValueError("Manifest path already exists: {}".format(path))
    _check_directory(path.parent)
    if not path.parent.is_dir():
        raise ValueError("Manifest directory does not exist: {}".format(path.parent))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        return path, os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
    except BaseException:
        os.close(descriptor)
        path.unlink()
        raise


def _append_manifest(stream, source, destination):
    stream.write(json.dumps(
        {"v": 1, "src": str(source), "dst": str(destination)},
        ensure_ascii=False,
    ) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _read_manifest(manifest):
    path = Path(os.path.abspath(os.path.expanduser(str(manifest))))
    if _is_link(path) or not path.is_file():
        raise ValueError("Manifest is not a regular file: {}".format(path))
    records = []
    seen_sources = set()
    seen_destinations = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError("Invalid manifest record on line {}: {}".format(line_number, error)) from error
            if not isinstance(record, dict) or record.get("v") != 1:
                raise ValueError("Unsupported manifest record on line {}".format(line_number))
            source = record.get("src")
            destination = record.get("dst")
            if (not isinstance(source, str) or not isinstance(destination, str)
                    or not os.path.isabs(source) or not os.path.isabs(destination)):
                raise ValueError("Manifest paths must be absolute on line {}".format(line_number))
            source_path = Path(source)
            destination_path = Path(destination)
            source_key = _reservation_key(source_path)
            destination_key = _reservation_key(destination_path)
            if source_key == destination_key or source_key in seen_sources or destination_key in seen_destinations:
                raise ValueError("Manifest has conflicting paths on line {}".format(line_number))
            seen_sources.add(source_key)
            seen_destinations.add(destination_key)
            records.append((source_path, destination_path))
    return records


def _organize(target_dir, folder_for, dry_run, recursive, manifest=None):
    root = Path(os.path.abspath(os.path.expanduser(str(target_dir))))
    _check_directory(root)
    if not root.is_dir():
        raise ValueError("Target directory does not exist: {}".format(root))

    if manifest is not None and dry_run:
        raise ValueError("Refusing to write a manifest during a dry run")

    # Finish discovery and validation before making any filesystem changes.
    moves = []
    reserved = set()
    limits = {}
    for source in _snapshot(root, recursive):
        directory = root / folder_for(source)
        _check_directory(directory)
        if source.parent == directory:
            continue
        if directory not in limits:
            limits[directory] = _filename_limit(directory)
        destination = directory / source.name
        counter = 1
        while os.path.lexists(destination) or _reservation_key(destination) in reserved:
            candidate = "{}_{}{}".format(source.stem, counter, source.suffix)
            # lexists() reports False for an over-long name, so without this check
            # a dry run accepts a destination that apply cannot create. Later files
            # in the same run would already have been moved.
            if _name_exceeds_limit(candidate, limits[directory]):
                raise ValueError(
                    "Cannot rename {!r} in {} without exceeding the filesystem name limit ({})".format(
                        source.name, directory, limits[directory]
                    )
                )
            destination = directory / candidate
            counter += 1
        reserved.add(_reservation_key(destination))
        moves.append((source, destination))

    manifest_stream = None
    if manifest is not None:
        manifest_path = Path(os.path.abspath(os.path.expanduser(str(manifest))))
        try:
            inside_target = os.path.commonpath([str(root), str(manifest_path)]) == str(root)
        except ValueError:
            inside_target = False
        if inside_target:
            raise ValueError("Manifest must be created outside the target directory")
        _, manifest_stream = _open_manifest(manifest_path)
    try:
        if not dry_run:
            for source, destination in moves:
                _check_directory(source.parent)
                _check_directory(destination.parent)
                if _is_link(source) or not source.is_file():
                    raise ValueError("Source changed during organization: {}".format(source))
                destination.parent.mkdir(parents=True, exist_ok=True)
                _check_directory(destination.parent)
                _move_without_overwrite(source, destination)
                if manifest_stream is not None:
                    _append_manifest(manifest_stream, source, destination)
    finally:
        if manifest_stream is not None:
            manifest_stream.close()
    return moves


def organize_by_type(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False, categories=None, manifest=None) -> List[Tuple[Path, Path]]:
    """Organize by extension; return absolute (source, destination) paths.

    If manifest is set, each applied move is appended as one JSON object.
    Dry runs refuse to create a manifest.
    """
    categories = DEFAULT_CATEGORIES if categories is None else categories
    _validate_categories(categories)
    return _organize(
        target_dir, lambda item: get_category(item, categories), dry_run, recursive, manifest
    )


def organize_by_date(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False, manifest=None) -> List[Tuple[Path, Path]]:
    """Organize by modification year/month in the local timezone."""
    def folder_for(item):
        date = datetime.fromtimestamp(item.stat().st_mtime)
        return Path(str(date.year)) / "{:02d}".format(date.month)
    return _organize(target_dir, folder_for, dry_run, recursive, manifest)


def organize_by_size(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False, manifest=None) -> List[Tuple[Path, Path]]:
    """Organize by size: <1 MiB, 1–<100 MiB, and >=100 MiB."""
    def folder_for(item):
        size = item.stat().st_size
        if size < 1024 * 1024:
            return "Small"
        if size < 100 * 1024 * 1024:
            return "Medium"
        return "Large"
    return _organize(target_dir, folder_for, dry_run, recursive, manifest)


def undo_manifest(manifest, dry_run: bool = False) -> List[Tuple[Path, Path]]:
    """Move manifest destinations back to their original paths.

    Returns (current, original) pairs. Validates every record before moving.
    Existing files are never overwritten. The manifest file itself is left in place.
    """
    records = _read_manifest(manifest)
    reverse = []
    reserved = set()
    for source, destination in reversed(records):
        if _is_link(destination) or not destination.is_file():
            raise ValueError("Manifest destination is missing or not a regular file: {}".format(destination))
        _check_directory(destination.parent)
        _check_directory(source.parent)
        if not source.parent.is_dir():
            raise ValueError("Original directory does not exist: {}".format(source.parent))
        if os.path.lexists(source) or _reservation_key(source) in reserved:
            raise ValueError("Original path is not free, refusing to overwrite: {}".format(source))
        reserved.add(_reservation_key(source))
        reverse.append((destination, source))

    if not dry_run:
        for current, original in reverse:
            _check_directory(current.parent)
            _check_directory(original.parent)
            if _is_link(current) or not current.is_file():
                raise ValueError("File changed during undo: {}".format(current))
            if os.path.lexists(original):
                raise ValueError("Original path is not free, refusing to overwrite: {}".format(original))
            _move_without_overwrite(current, original)
    return reverse
