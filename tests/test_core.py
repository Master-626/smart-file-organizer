"""Pytest coverage for planning, the bug fixes, and undo manifests."""
import json
import os
import stat
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from file_organizer.cli import main
from file_organizer.organizer import (
    get_category,
    organize_by_date,
    organize_by_size,
    organize_by_type,
    undo_manifest,
)


def write(root, name, content="data"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_categories_and_size_boundaries(tmp_path):
    assert get_category(Path("PHOTO.JPG")) == "Images"
    assert get_category(Path("bundle.tar.gz")) == "Archives"
    assert get_category(Path("notes.txt")) == "Documents"
    assert get_category(Path("mystery.xyz")) == "Others"

    small = tmp_path / "small.bin"
    medium = tmp_path / "medium.bin"
    large = tmp_path / "large.bin"
    with small.open("wb") as stream:
        stream.truncate(1024 ** 2 - 1)
    with medium.open("wb") as stream:
        stream.truncate(1024 ** 2)
    with large.open("wb") as stream:
        stream.truncate(100 * 1024 ** 2)

    preview = organize_by_size(tmp_path, dry_run=True)
    assert {src.name: dst.parent.name for src, dst in preview} == {
        "small.bin": "Small",
        "medium.bin": "Medium",
        "large.bin": "Large",
    }
    assert not (tmp_path / "Small").exists()
    assert organize_by_size(tmp_path) == preview
    assert small.exists() is False
    assert (tmp_path / "Small" / "small.bin").stat().st_size == 1024 ** 2 - 1
    assert organize_by_size(tmp_path, recursive=True) == []


def test_date_folders_use_local_mtime_and_dry_run_is_stable(tmp_path):
    source = write(tmp_path, "nested/sample.txt", "important")
    os.utime(source, (1600000000, 1600000000))
    moment = datetime.fromtimestamp(1600000000)
    expected = Path(str(moment.year)) / "{:02d}".format(moment.month) / "sample.txt"

    preview = organize_by_date(tmp_path, recursive=True, dry_run=True)
    assert source.exists()
    assert preview[0][1].relative_to(tmp_path) == expected
    assert not preview[0][1].exists()
    assert organize_by_date(tmp_path, recursive=True) == preview
    assert preview[0][1].read_text() == "important"
    assert preview[0][1].stat().st_mtime == 1600000000
    assert organize_by_date(tmp_path, recursive=True) == []


def test_hidden_files_and_nonrecursive_children_stay_put(tmp_path):
    hidden = write(tmp_path, ".secret.txt")
    nested = write(tmp_path, "nested/visible.txt", "visible")
    assert organize_by_type(tmp_path) == []
    moves = organize_by_type(tmp_path, recursive=True)
    assert [src.name for src, _ in moves] == ["visible.txt"]
    assert hidden.exists()
    assert not nested.exists()
    assert (tmp_path / "Documents" / "visible.txt").read_text() == "visible"


def test_collisions_are_planned_before_any_file_is_replaced(tmp_path):
    write(tmp_path, "a/same.txt", "a")
    write(tmp_path, "b/same.txt", "b")
    write(tmp_path, "Documents/same.txt", "kept")
    preview = organize_by_type(tmp_path, recursive=True, dry_run=True)
    assert [dst.name for _, dst in preview] == ["same_1.txt", "same_2.txt"]
    assert organize_by_type(tmp_path, recursive=True) == preview
    assert (tmp_path / "Documents" / "same.txt").read_text() == "kept"
    assert (tmp_path / "Documents" / "same_1.txt").read_text() == "a"


def test_file_blocking_a_date_folder_raises_before_moves(tmp_path):
    moment = datetime.fromtimestamp(1577836800)
    blocker = write(tmp_path, str(moment.year), "not-a-directory")
    note = write(tmp_path, "note.txt", "note")
    os.utime(note, (1577836800, 1577836800))
    with pytest.raises(ValueError, match="Not a directory"):
        organize_by_date(tmp_path, dry_run=True)
    with pytest.raises(ValueError, match="Not a directory"):
        organize_by_date(tmp_path)
    assert blocker.read_text() == "not-a-directory"
    assert note.read_text() == "note"
    assert {item.name for item in tmp_path.iterdir()} == {blocker.name, "note.txt"}


def test_symlink_to_file_blocking_a_date_folder_is_rejected(tmp_path):
    target = write(tmp_path, "plain.txt", "plain")
    year = str(datetime.fromtimestamp(1577836800).year)
    link = tmp_path / year
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip("Symlinks unavailable: {}".format(error))
    note = write(tmp_path, "note.txt", "note")
    os.utime(note, (1577836800, 1577836800))
    with pytest.raises(ValueError, match="Symbolic-link"):
        organize_by_date(tmp_path, dry_run=True)
    assert note.read_text() == "note"
    assert link.is_symlink()
    assert {item.name for item in tmp_path.iterdir()} == {"plain.txt", year, "note.txt"}


def _limit_name(root):
    limit = os.statvfs(root).f_namemax
    suffix = ".txt"
    if limit <= len(suffix):
        pytest.skip("filename limit is too small to build a fixture")
    return ("n" * (limit - len(suffix))) + suffix


def test_overlong_collision_name_is_rejected_before_any_move(tmp_path):
    if not hasattr(os, "statvfs"):
        pytest.skip("statvfs is required to know the filename limit")
    root = tmp_path / "short"
    root.mkdir()
    name = _limit_name(root)
    try:
        (root / name).write_text("keep")
        (root / "Documents").mkdir()
        (root / "Documents" / name).write_text("occupied")
        (root / "aaa.txt").write_text("first")
    except OSError as error:
        pytest.skip("filesystem rejected the long name: {}".format(error))

    manifest = tmp_path / "moves.jsonl"
    with pytest.raises(ValueError, match="filesystem name limit"):
        organize_by_type(root, dry_run=True)
    with pytest.raises(ValueError, match="filesystem name limit"):
        organize_by_type(root, manifest=manifest)
    assert (root / "aaa.txt").read_text() == "first"
    assert (root / name).read_text() == "keep"
    assert (root / "Documents" / name).read_text() == "occupied"
    assert not (root / "Documents" / "aaa.txt").exists()
    assert not manifest.exists()


def test_collision_suffix_that_fits_the_filename_limit_is_used(tmp_path):
    if not hasattr(os, "statvfs"):
        pytest.skip("statvfs is required to know the filename limit")
    root = tmp_path / "short"
    root.mkdir()
    limit = os.statvfs(root).f_namemax
    suffix = ".txt"
    # "_1" is two bytes, so a name two bytes under the limit still has room.
    length = limit - 2
    if length <= len(suffix):
        pytest.skip("filename limit is too small to build a fixture")
    name = ("n" * (length - len(suffix))) + suffix
    try:
        (root / name).write_text("keep")
        (root / "Documents").mkdir()
        (root / "Documents" / name).write_text("occupied")
    except OSError as error:
        pytest.skip("filesystem rejected the long name: {}".format(error))

    moves = organize_by_type(root)
    destination = moves[0][1]
    assert destination.name.endswith("_1.txt")
    assert len(os.fsencode(destination.name)) == limit
    assert destination.read_text() == "keep"
    assert (root / "Documents" / name).read_text() == "occupied"


def test_max_length_name_without_a_collision_still_moves(tmp_path):
    if not hasattr(os, "statvfs"):
        pytest.skip("statvfs is required to know the filename limit")
    name = _limit_name(tmp_path)
    try:
        source = write(tmp_path, name, "ok")
    except OSError as error:
        pytest.skip("filesystem rejected the long name: {}".format(error))
    moves = organize_by_type(tmp_path)
    assert moves[0][1].name == name
    assert moves[0][1].read_text() == "ok"
    assert not source.exists()


def test_manifest_round_trip_restores_content_and_mtime(tmp_path):
    source = write(tmp_path / "inbox", "café.txt", "hello")
    os.utime(source, (1600000000, 1600000000))
    manifest = tmp_path / "moves.jsonl"
    moves = organize_by_type(tmp_path / "inbox", manifest=manifest)
    assert not source.exists()
    assert moves[0][1].read_text() == "hello"
    if os.name == "posix":
        assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    record = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
    assert record["v"] == 1
    assert record["src"].endswith("café.txt")
    assert Path(record["dst"]).read_text(encoding="utf-8") == "hello"

    preview = undo_manifest(manifest, dry_run=True)
    assert preview == [(moves[0][1], moves[0][0])]
    assert not source.exists()
    restored = undo_manifest(manifest)
    assert restored == preview
    assert source.read_text(encoding="utf-8") == "hello"
    assert source.stat().st_mtime == 1600000000
    assert not moves[0][1].exists()
    with pytest.raises(ValueError, match="missing"):
        undo_manifest(manifest)


def test_undo_validates_every_record_before_moving(tmp_path):
    first = write(tmp_path / "inbox", "a.txt", "a")
    second = write(tmp_path / "inbox", "b.txt", "b")
    manifest = tmp_path / "moves.jsonl"
    moves = organize_by_type(tmp_path / "inbox", manifest=manifest)
    moves[1][1].unlink()
    with pytest.raises(ValueError, match="missing"):
        undo_manifest(manifest)
    assert moves[0][1].is_file()
    assert first.exists() is False
    assert second.exists() is False


def test_undo_rejects_a_symlink_destination_before_moving_anything(tmp_path):
    write(tmp_path / "inbox", "a.txt", "a")
    write(tmp_path / "inbox", "b.txt", "b")
    manifest = tmp_path / "moves.jsonl"
    moves = organize_by_type(tmp_path / "inbox", manifest=manifest)
    moved_a, moved_b = moves[0][1], moves[1][1]
    moved_a.unlink()
    try:
        moved_a.symlink_to(moved_b)
    except OSError as error:
        pytest.skip("Symlinks unavailable: {}".format(error))
    with pytest.raises(ValueError, match="regular file"):
        undo_manifest(manifest)
    assert moved_b.read_text() == "b"
    assert not (tmp_path / "inbox" / "a.txt").exists()
    assert not (tmp_path / "inbox" / "b.txt").exists()


def test_undo_refuses_to_overwrite_an_occupied_original_path(tmp_path):
    write(tmp_path / "inbox", "note.txt", "moved")
    manifest = tmp_path / "moves.jsonl"
    moves = organize_by_type(tmp_path / "inbox", manifest=manifest)
    write(tmp_path / "inbox", "note.txt", "new occupant")
    with pytest.raises(ValueError, match="not free"):
        undo_manifest(manifest)
    assert (tmp_path / "inbox" / "note.txt").read_text() == "new occupant"
    assert moves[0][1].read_text() == "moved"


def test_manifest_must_live_outside_the_target_and_not_during_dry_run(tmp_path):
    write(tmp_path, "note.txt")
    with pytest.raises(ValueError, match="dry run"):
        organize_by_type(tmp_path, dry_run=True, manifest=tmp_path / "out.jsonl")
    with pytest.raises(ValueError, match="outside"):
        organize_by_type(tmp_path, manifest=tmp_path / "inside.jsonl")
    assert (tmp_path / "note.txt").exists()
    assert not (tmp_path / "Documents").exists()


def test_partial_manifest_can_undo_the_moves_that_succeeded(tmp_path, monkeypatch):
    write(tmp_path / "inbox", "a.txt", "a")
    write(tmp_path / "inbox", "b.txt", "b")
    manifest = tmp_path / "moves.jsonl"
    import file_organizer.organizer as organizer

    original = organizer._move_without_overwrite

    def flaky(source, destination):
        if source.name == "b.txt":
            raise OSError("disk full")
        original(source, destination)

    monkeypatch.setattr("file_organizer.organizer._move_without_overwrite", flaky)
    with pytest.raises(OSError, match="disk full"):
        organize_by_type(tmp_path / "inbox", manifest=manifest)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert (tmp_path / "inbox" / "b.txt").read_text() == "b"
    undo_manifest(manifest)
    assert (tmp_path / "inbox" / "a.txt").read_text() == "a"
    assert (tmp_path / "inbox" / "b.txt").read_text() == "b"


def test_cli_manifest_undo_and_date_blocker(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "note.txt").write_text("hello")
    manifest = tmp_path / "moves.jsonl"
    runner = CliRunner()
    preview = runner.invoke(main, [str(inbox), "--dry-run", "--verbose"])
    assert preview.exit_code == 0, preview.output
    assert "Documents/note.txt" in preview.output.replace("\\", "/")
    assert (inbox / "note.txt").exists()

    applied = runner.invoke(main, [str(inbox), "--manifest", str(manifest)])
    assert applied.exit_code == 0, applied.output
    assert "files organized successfully" in applied.output
    assert not (inbox / "note.txt").exists()

    undo_preview = runner.invoke(main, ["--undo", str(manifest), "--dry-run", "--verbose"])
    assert undo_preview.exit_code == 0, undo_preview.output
    assert "would be moved back" in undo_preview.output
    assert not (inbox / "note.txt").exists()

    restored = runner.invoke(main, ["--undo", str(manifest)])
    assert restored.exit_code == 0, restored.output
    assert (inbox / "note.txt").read_text() == "hello"

    rejected = runner.invoke(main, ["--undo", str(manifest), "--by", "date"])
    assert rejected.exit_code != 0
    assert "does not accept --by" in rejected.output

    missing = runner.invoke(main, [])
    assert missing.exit_code != 0
    assert "PATH" in missing.output

    year = str(datetime.fromtimestamp(1577836800).year)
    (inbox / year).write_text("blocked")
    dated = inbox / "old.txt"
    dated.write_text("old")
    os.utime(dated, (1577836800, 1577836800))
    blocked = runner.invoke(main, [str(inbox), "--by", "date", "--dry-run"])
    assert blocked.exit_code == 1
    assert "Not a directory" in blocked.output
    assert "Errno" not in blocked.output
    assert dated.exists()

    help_text = runner.invoke(main, ["--help"]).output
    assert "--manifest" in help_text
    assert "--undo" in help_text
    assert "--dry-run" in help_text
