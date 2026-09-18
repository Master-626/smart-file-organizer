"""
Core organization logic for Smart File Organizer.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
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


def get_category(file_path: Path, categories: Dict[str, List[str]] = None) -> str:
    """Determine which category a file belongs to based on its extension."""
    if categories is None:
        categories = DEFAULT_CATEGORIES

    ext = file_path.suffix.lower()

    for category, extensions in categories.items():
        if ext in extensions:
            return category

    return "Others"


def organize_by_type(
    target_dir: Path,
    dry_run: bool = False,
    recursive: bool = False,
    categories: Dict[str, List[str]] = None,
) -> List[Tuple[Path, Path]]:
    """
    Organize files in target directory by file type.

    Returns a list of (source, destination) tuples representing moves.
    """
    if categories is None:
        categories = DEFAULT_CATEGORIES

    moves = []
    pattern = "**/*" if recursive else "*"

    for item in target_dir.glob(pattern):
        if item.is_dir():
            continue

        # Skip hidden files and the organizer's own folders
        if item.name.startswith("."):
            continue

        category = get_category(item, categories)
        dest_dir = target_dir / category
        dest_path = dest_dir / item.name

        # Handle name collisions
        counter = 1
        while dest_path.exists():
            stem = item.stem
            suffix = item.suffix
            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        moves.append((item, dest_path))

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dest_path))

    return moves


def organize_by_date(
    target_dir: Path,
    dry_run: bool = False,
    recursive: bool = False,
) -> List[Tuple[Path, Path]]:
    """
    Organize files in target directory by modification date (year/month).

    Returns a list of (source, destination) tuples representing moves.
    """
    moves = []
    pattern = "**/*" if recursive else "*"

    for item in target_dir.glob(pattern):
        if item.is_dir():
            continue

        if item.name.startswith("."):
            continue

        mtime = datetime.fromtimestamp(item.stat().st_mtime)
        year_dir = target_dir / str(mtime.year)
        month_dir = year_dir / f"{mtime.month:02d}"
        dest_path = month_dir / item.name

        # Handle name collisions
        counter = 1
        while dest_path.exists():
            stem = item.stem
            suffix = item.suffix
            dest_path = month_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        moves.append((item, dest_path))

        if not dry_run:
            month_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dest_path))

    return moves


def organize_by_size(
    target_dir: Path,
    dry_run: bool = False,
    recursive: bool = False,
) -> List[Tuple[Path, Path]]:
    """
    Organize files in target directory by size buckets.

    Returns a list of (source, destination) tuples representing moves.
    """
    moves = []
    pattern = "**/*" if recursive else "*"

    for item in target_dir.glob(pattern):
        if item.is_dir():
            continue

        if item.name.startswith("."):
            continue

        size_bytes = item.stat().st_size

        if size_bytes < 1024 * 1024:  # < 1MB
            bucket = "Small (<1MB)"
        elif size_bytes < 1024 * 1024 * 100:  # < 100MB
            bucket = "Medium (1MB-100MB)"
        else:  # > 100MB
            bucket = "Large (>100MB)"

        dest_dir = target_dir / bucket
        dest_path = dest_dir / item.name

        # Handle name collisions
        counter = 1
        while dest_path.exists():
            stem = item.stem
            suffix = item.suffix
            dest_path = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        moves.append((item, dest_path))

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dest_path))

    return moves
