import os
import shutil
import stat
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from file_organizer.cli import main
from file_organizer.organizer import (
    _is_link,
    _move_without_overwrite,
    get_category,
    organize_by_date,
    organize_by_size,
    organize_by_type,
)


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, name, content=b'hello'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def link(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as error:
            self.skipTest('Symlinks unavailable: {}'.format(error))

    def test_each_mode_is_recursive_and_idempotent(self):
        for mode in (organize_by_type, organize_by_date, organize_by_size):
            with self.subTest(mode=mode.__name__):
                root = self.root / mode.__name__
                (root / 'nested').mkdir(parents=True)
                source = root / 'nested' / 'sample.txt'
                source.write_text('important')
                preview = mode(root, recursive=True, dry_run=True)
                self.assertTrue(source.exists())
                self.assertFalse(preview[0][1].exists())
                self.assertEqual(mode(root, recursive=True), preview)
                self.assertEqual(preview[0][1].read_text(), 'important')
                self.assertEqual(mode(root, recursive=True), [])

    def test_hidden_subtrees_and_nonrecursive_files_are_untouched(self):
        hidden = self.write('.private/deep/secret.txt')
        dotfile = self.write('.secret.txt')
        nested = self.write('nested/visible.txt')
        self.assertEqual(organize_by_type(self.root), [])
        self.assertEqual(len(organize_by_type(self.root, recursive=True)), 1)
        self.assertTrue(hidden.exists())
        self.assertTrue(dotfile.exists())
        self.assertFalse(nested.exists())

    def test_collision_plan_reserves_names_and_matches_actual(self):
        for name in ('a/same.txt', 'b/same.txt', 'Documents/same.txt', 'Documents/same_1.txt'):
            self.write(name, name.encode())
        preview = organize_by_type(self.root, recursive=True, dry_run=True)
        self.assertEqual([dst.name for _, dst in preview], ['same_2.txt', 'same_3.txt'])
        self.assertEqual(organize_by_type(self.root, recursive=True), preview)
        self.assertEqual((self.root / 'Documents/same.txt').read_bytes(), b'Documents/same.txt')
        self.assertEqual(organize_by_type(self.root, recursive=True), [])

    def test_symlink_files_subtrees_and_dangling_links_skipped(self):
        actual = self.write('.private/secret.txt')
        self.link(self.root / 'linked.txt', actual)
        self.link(self.root / 'linked-dir', actual.parent, True)
        self.link(self.root / 'dangling.txt', self.root / 'absent')
        self.assertEqual(organize_by_type(self.root, recursive=True), [])
        self.assertTrue(actual.exists())

    def test_symlink_destination_and_target_are_rejected(self):
        source = self.write('important.txt')
        outside = self.root / 'outside'
        outside.mkdir()
        self.link(self.root / 'Documents', outside, True)
        for dry_run in (True, False):
            with self.assertRaises(ValueError):
                organize_by_type(self.root, dry_run=dry_run)
        with self.assertRaises(ValueError):
            organize_by_type(self.root / 'Documents')
        self.assertTrue(source.exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_date_symlink_parent_rejected(self):
        from datetime import datetime
        source = self.write('sample.txt')
        year = str(datetime.fromtimestamp(source.stat().st_mtime).year)
        outside = self.root / 'outside'
        outside.mkdir()
        self.link(self.root / year, outside, True)
        with self.assertRaises(ValueError):
            organize_by_date(self.root)
        self.assertTrue(source.exists())

    def test_dangling_destination_is_a_collision(self):
        self.write('sample.txt')
        (self.root / 'Documents').mkdir()
        self.link(self.root / 'Documents/sample.txt', self.root / 'missing')
        moves = organize_by_type(self.root)
        self.assertEqual(moves[0][1].name, 'sample_1.txt')
        self.assertTrue((self.root / 'Documents/sample.txt').is_symlink())

    def test_bad_categories_rejected_before_any_moves(self):
        source = self.write('sample.txt')
        for name in ('..', '.', '../escape', '/absolute', 'a/b', 'a\\b', '.hidden', 'C:escape', 'CON', 'trailing.', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                organize_by_type(self.root, categories={name: ['.txt']})
        for categories in ([], {'Safe': '.txt'}, {'Safe': [123]}, {'Safe': ['txt']}):
            with self.assertRaises(ValueError):
                organize_by_type(self.root, categories=categories)
        self.assertTrue(source.exists())
        self.assertEqual(get_category(Path('PHOTO.JPG'), {'Photos': ['.JPG']}), 'Photos')
        self.assertEqual(get_category(Path('unknown.xyz'), {}), 'Others')

    def test_windows_reparse_point_detection(self):
        from types import SimpleNamespace
        with patch.object(Path, 'is_symlink', return_value=False):
            with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_file_attributes=0x400)):
                self.assertTrue(_is_link(self.root))

    def test_invalid_targets(self):
        file = self.write('file.txt')
        for target in (file, self.root / 'missing'):
            with self.assertRaises(ValueError):
                organize_by_type(target)

    def test_blocked_destination_validated_before_moves(self):
        self.write('a.mp3')
        source = self.write('z.txt')
        self.write('Documents')
        with self.assertRaises(ValueError):
            organize_by_type(self.root)
        self.assertTrue(source.exists())
        self.assertTrue((self.root / 'a.mp3').exists())
        self.assertFalse((self.root / 'Audio').exists())

    def test_size_boundaries(self):
        for name, size, expected in [('small.bin', 1024**2 - 1, 'Small'),
                                     ('medium.bin', 1024**2, 'Medium'),
                                     ('large.bin', 100 * 1024**2, 'Large')]:
            path = self.root / name
            with path.open('wb') as stream:
                stream.truncate(size)
        plan = organize_by_size(self.root, dry_run=True)
        self.assertEqual({src.name: dst.parent.name for src, dst in plan},
                         {'small.bin': 'Small', 'medium.bin': 'Medium', 'large.bin': 'Large'})

    def test_size_bucket_blocked_by_file_preserves_all_sources(self):
        source = self.write('sample.bin', b'source')
        occupied = self.write('Small', b'existing bucket-name file')
        for dry_run in (True, False):
            with self.assertRaises(ValueError):
                organize_by_size(self.root, dry_run=dry_run)
        self.assertEqual(source.read_bytes(), b'source')
        self.assertEqual(occupied.read_bytes(), b'existing bucket-name file')

    def test_exclusive_move_preserves_existing_destination(self):
        source = self.write('source.txt', b'source')
        destination = self.write('destination.txt', b'destination')
        with self.assertRaises(FileExistsError):
            _move_without_overwrite(source, destination)
        self.assertEqual(source.read_bytes(), b'source')
        self.assertEqual(destination.read_bytes(), b'destination')

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission bits required')
    def test_copy_starts_private_before_copying_source_bytes(self):
        source = self.write('private.txt', b'private data')
        source.chmod(0o600)
        destination = self.root / 'copy.txt'
        original_copy = shutil.copyfileobj
        def inspect_and_copy(original, output):
            self.assertEqual(stat.S_IMODE(os.fstat(output.fileno()).st_mode), 0o600)
            original_copy(original, output)
        previous_umask = os.umask(0)
        try:
            with patch('file_organizer.organizer.shutil.copyfileobj', side_effect=inspect_and_copy):
                _move_without_overwrite(source, destination)
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(destination.read_bytes(), b'private data')
        self.assertFalse(source.exists())

    def test_fdopen_failure_closes_descriptor_and_removes_destination(self):
        source = self.write('source.txt')
        destination = self.root / 'destination.txt'
        with patch('file_organizer.organizer.os.fdopen', side_effect=OSError('fdopen failed')):
            with patch('file_organizer.organizer.os.close', wraps=os.close) as close:
                with self.assertRaises(OSError):
                    _move_without_overwrite(source, destination)
                close.assert_called_once()
        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())

    def test_case_and_unicode_equivalent_planned_names_are_reserved(self):
        self.write('a/Photo.txt')
        self.write('b/photo.txt')
        self.write('c/caf\u00e9.txt')
        self.write('d/cafe\u0301.txt')
        preview = organize_by_type(self.root, recursive=True, dry_run=True)
        self.assertEqual([unicodedata.normalize('NFC', dst.name) for _, dst in preview],
                         ['Photo.txt', 'photo_1.txt', 'caf\u00e9.txt', 'caf\u00e9_1.txt'])
        self.assertEqual(organize_by_type(self.root, recursive=True), preview)
        self.assertEqual(organize_by_type(self.root, recursive=True), [])

    def test_copy_failure_retains_source_and_removes_partial_copy(self):
        source = self.write('source.txt')
        destination = self.root / 'destination.txt'
        with patch('file_organizer.organizer.shutil.copyfileobj', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                _move_without_overwrite(source, destination)
        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())

    def test_date_preserves_mtime(self):
        source = self.write('sample.txt')
        os.utime(source, (1600000000, 1600000000))
        moves = organize_by_date(self.root)
        self.assertEqual(moves[0][1].stat().st_mtime, 1600000000)
        self.assertEqual(organize_by_date(self.root, recursive=True), [])

    def test_cli_relative_path_and_errors(self):
        runner = CliRunner()
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                Path('sample.txt').write_text('hello')
                result = runner.invoke(main, ['.', '--dry-run', '--verbose'])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn('Documents/sample.txt', result.output.replace('\\', '/'))
                self.assertTrue(Path('sample.txt').exists())
                Path('nested').mkdir()
                result = runner.invoke(main, ['nested/..', '--dry-run', '--verbose'])
                self.assertEqual(result.exit_code, 0, result.output)
                Path('Documents').write_text('blocked')
                result = runner.invoke(main, ['.'])
                self.assertEqual(result.exit_code, 1)
                self.assertIn('Error:', result.output)
            finally:
                os.chdir(previous)
        self.assertIn('--dry-run', runner.invoke(main, ['--help']).output)
        self.assertEqual(runner.invoke(main, ['--version']).exit_code, 0)


if __name__ == '__main__':
    unittest.main()
