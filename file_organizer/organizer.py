"""
Core organization logic for Smart File Organizer.
"""
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
    for component in (path,) + tuple(path.parents):
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


def _organize(target_dir, folder_for, dry_run, recursive):
    root = Path(os.path.abspath(os.path.expanduser(str(target_dir))))
    _check_directory(root)
    if not root.is_dir():
        raise ValueError("Target directory does not exist: {}".format(root))

    # Finish discovery and validation before making any filesystem changes.
    moves = []
    reserved = set()
    for source in _snapshot(root, recursive):
        directory = root / folder_for(source)
        _check_directory(directory)
        if source.parent == directory:
            continue
        destination = directory / source.name
        counter = 1
        while os.path.lexists(destination) or _reservation_key(destination) in reserved:
            destination = directory / "{}_{}{}".format(source.stem, counter, source.suffix)
            counter += 1
        reserved.add(_reservation_key(destination))
        moves.append((source, destination))

    if not dry_run:
        for source, destination in moves:
            _check_directory(source.parent)
            _check_directory(destination.parent)
            if _is_link(source) or not source.is_file():
                raise ValueError("Source changed during organization: {}".format(source))
            destination.parent.mkdir(parents=True, exist_ok=True)
            _check_directory(destination.parent)
            _move_without_overwrite(source, destination)
    return moves


def organize_by_type(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False, categories=None) -> List[Tuple[Path, Path]]:
    """Organize by extension; return absolute (source, destination) paths."""
    categories = DEFAULT_CATEGORIES if categories is None else categories
    _validate_categories(categories)
    return _organize(target_dir, lambda item: get_category(item, categories), dry_run, recursive)


def organize_by_date(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False) -> List[Tuple[Path, Path]]:
    """Organize by modification year/month in the local timezone."""
    def folder_for(item):
        date = datetime.fromtimestamp(item.stat().st_mtime)
        return Path(str(date.year)) / "{:02d}".format(date.month)
    return _organize(target_dir, folder_for, dry_run, recursive)


def organize_by_size(target_dir: Path, dry_run: bool = False,
                     recursive: bool = False) -> List[Tuple[Path, Path]]:
    """Organize by size: <1 MiB, 1–<100 MiB, and >=100 MiB."""
    def folder_for(item):
        size = item.stat().st_size
        if size < 1024 * 1024:
            return "Small"
        if size < 100 * 1024 * 1024:
            return "Medium"
        return "Large"
    return _organize(target_dir, folder_for, dry_run, recursive)
