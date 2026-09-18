"""
Command-line interface for Smart File Organizer.
"""
import sys
from pathlib import Path

import click

from .organizer import organize_by_type, organize_by_date, organize_by_size
from . import __version__


@click.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--by", "organization_method",
    type=click.Choice(["type", "date", "size"]),
    default="type",
    help="Organize by file type, date, or file size.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Preview changes without actually moving files.",
)
@click.option(
    "--recursive", is_flag=True, default=False,
    help="Also process files in subdirectories.",
)
@click.option(
    "-v", "--verbose", is_flag=True, default=False,
    help="Show detailed output.",
)
@click.version_option(version=__version__, prog_name="smart-file-organizer")
def main(path: Path, organization_method: str, dry_run: bool, recursive: bool, verbose: bool):
    """
    Smart File Organizer - Automatically organize your messy folders.

    Target PATH is the directory you want to organize.
    """
    click.echo(f"📁 Smart File Organizer v{__version__}")
    click.echo(f"📂 Target: {path.resolve()}")
    click.echo(f"🔧 Method: by {organization_method}")

    if dry_run:
        click.echo("👀 Dry run mode - no files will be moved")

    click.echo("")

    if organization_method == "type":
        moves = organize_by_type(path, dry_run=dry_run, recursive=recursive)
    elif organization_method == "date":
        moves = organize_by_date(path, dry_run=dry_run, recursive=recursive)
    else:
        moves = organize_by_size(path, dry_run=dry_run, recursive=recursive)

    if not moves:
        click.echo("✅ No files to organize.")
        return

    click.echo(f"Found {len(moves)} files to organize:\n")

    for src, dst in moves:
        rel_dst = dst.relative_to(path)
        if verbose:
            click.echo(f"  {src.name}  →  {rel_dst}")
        else:
            click.echo(f"  {src.name}  →  {rel_dst.parent}/")

    click.echo("")

    if dry_run:
        click.echo(f"👀 Dry run complete. {len(moves)} files would be organized.")
        click.echo("   Run without --dry-run to apply changes.")
    else:
        click.echo(f"✅ Done! {len(moves)} files organized successfully.")


if __name__ == "__main__":
    main()
