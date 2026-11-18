"""
Command-line interface for Smart File Organizer.
"""
import os
from pathlib import Path

import click
from click.core import ParameterSource

from . import __version__
from .organizer import organize_by_date, organize_by_size, organize_by_type, undo_manifest


@click.command()
@click.argument(
    "path", required=False, default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
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
@click.option(
    "--manifest",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write each applied move as JSON Lines for --undo. Must be outside PATH.",
)
@click.option(
    "--undo", "undo_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Move files back using a manifest written by --manifest.",
)
@click.version_option(version=__version__, prog_name="smart-file-organizer")
@click.pass_context
def main(ctx, path, organization_method, dry_run, recursive, verbose, manifest, undo_path):
    """
    Smart File Organizer - Automatically organize your messy folders.

    Target PATH is the directory you want to organize.
    """
    click.echo(f"📁 Smart File Organizer v{__version__}")
    if undo_path is not None:
        if path is not None or manifest is not None or recursive:
            raise click.UsageError("--undo only accepts --dry-run and --verbose.")
        source = ctx.get_parameter_source("organization_method")
        if source is ParameterSource.COMMANDLINE:
            raise click.UsageError("--undo does not accept --by.")
        _undo(undo_path, dry_run, verbose)
        return

    if path is None:
        raise click.UsageError("Missing argument 'PATH'.")

    target = Path(os.path.abspath(os.path.expanduser(str(path))))
    click.echo(f"📂 Target: {target}")
    click.echo(f"🔧 Method: by {organization_method}")

    if dry_run:
        click.echo("👀 Dry run mode - no files will be moved")

    click.echo("")

    methods = {"type": organize_by_type, "date": organize_by_date, "size": organize_by_size}
    try:
        moves = methods[organization_method](
            path, dry_run=dry_run, recursive=recursive, manifest=manifest,
        )
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    if not moves:
        click.echo("✅ No files to organize.")
        if manifest is not None:
            click.echo(f"📝 Manifest: {Path(os.path.abspath(manifest))}")
        return

    click.echo(f"Found {len(moves)} files to organize:\n")

    for src, dst in moves:
        rel_dst = dst.relative_to(target)
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
        if manifest is not None:
            click.echo(f"📝 Manifest: {Path(os.path.abspath(manifest))}")


def _undo(undo_path, dry_run, verbose):
    click.echo(f"↩️  Undo manifest: {Path(os.path.abspath(undo_path))}")
    if dry_run:
        click.echo("👀 Dry run mode - no files will be moved")
    click.echo("")
    try:
        moves = undo_manifest(undo_path, dry_run=dry_run)
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from error

    if not moves:
        click.echo("✅ No files to move back.")
        return

    click.echo(f"Found {len(moves)} files to move back:\n")
    for current, original in moves:
        if verbose:
            click.echo(f"  {current.name}  →  {original}")
        else:
            click.echo(f"  {current.name}  →  {original.parent}/")
    click.echo("")
    if dry_run:
        click.echo(f"👀 Dry run complete. {len(moves)} files would be moved back.")
    else:
        click.echo(f"✅ Done! {len(moves)} files restored.")


if __name__ == "__main__":
    main()
