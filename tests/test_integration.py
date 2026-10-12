"""Filesystem integration checks using synthetic submissions and failure injection."""

import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest import mock

from turnin_demo import integration


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turnin-integration-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "학생 소스 폴더"
        self.sources.mkdir()
        self.server = self.root / "가짜 제출함" / "test-student"
        self.server.parent.mkdir()
        self.course = "한글 PDF 과제"

    def source(self, name="한글 파일.cpp", data=None):
        path = self.sources / name
        path.write_bytes(data if data is not None else "// 한글 주석\r\nint main() { return 0; }\r\n".encode("utf-8"))
        return path

    def old_submission(self):
        self.server.mkdir(parents=True)
        (self.server / "obsolete.c").write_bytes(b"// previous source\n")
        (self.server / "hw.pdf").write_bytes(b"%PDF-1.4\nprevious listing\n")
        (self.server / ".teacher-note").write_bytes(b"do not change\n")
        os.chmod(self.server, 0o750)
        os.chmod(self.server / "obsolete.c", 0o640)
        os.chmod(self.server / "hw.pdf", 0o600)
        return self.visible_state()

    def visible_state(self):
        return {path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.server.iterdir() if not path.name.startswith(".")}

    def assert_old_preserved(self, previous):
        self.assertEqual(self.visible_state(), previous)
        self.assertEqual(stat.S_IMODE(self.server.stat().st_mode), 0o750)
        self.assertEqual((self.server / ".teacher-note").read_bytes(), b"do not change\n")

    @staticmethod
    def fake_renderer(sources, output, course, submitter):
        # Filesystem failure tests use an injectable renderer, not a PDF parser.
        data = b"%PDF-1.4\n" + b"\n".join(Path(path).read_bytes() for path in sources)
        Path(output).write_bytes(data + b"\n%%EOF\n" + b" " * 128)
        return Path(output)

    def submit(self, source_dir=None, server_dir=None):
        return integration.submit_listing(source_dir or self.sources,
                                          server_dir or self.server,
                                          self.course, "test-student")

    def test_real_renderer_publishes_pdf_and_original_source_bytes(self):
        source = self.source()
        original = source.read_bytes()
        result = self.submit()
        self.assertEqual(Path(result), self.server / "hw.pdf")
        self.assertTrue(result.read_bytes().startswith(b"%PDF-"))
        self.assertEqual((self.server / source.name).read_bytes(), original)
        self.assertEqual((self.sources / "hw.pdf").read_bytes(), result.read_bytes())
        self.assertEqual(stat.S_IMODE(self.server.stat().st_mode), 0o700)
        for path in self.server.iterdir():
            if not path.name.startswith("."):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(list(self.sources.glob(".turnin-prepare-*")), [])
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_resubmission_removes_obsolete_visible_files_and_keeps_hidden_files(self):
        source = self.source(data=b"\xef\xbb\xbf// UTF-8 BOM\r\nint value = 42;\r\n")
        expected = source.read_bytes()
        self.old_submission()
        with mock.patch.object(integration, "render_pdf", side_effect=self.fake_renderer):
            self.submit()
        self.assertEqual({path.name for path in self.server.iterdir() if not path.name.startswith(".")},
                         {source.name, "hw.pdf"})
        self.assertEqual((self.server / source.name).read_bytes(), expected)
        self.assertEqual((self.server / ".teacher-note").read_bytes(), b"do not change\n")
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_source_snapshot_keeps_pdf_and_published_source_consistent(self):
        source = self.source(data=b"// SNAPSHOT_ORIGINAL\n")
        original = source.read_bytes()

        def mutate_after_snapshot(paths, output, course, submitter):
            self.assertEqual(len(paths), 1)
            self.assertNotEqual(Path(paths[0]), source)
            self.assertEqual(Path(paths[0]).read_bytes(), original)
            source.write_bytes(b"// EDITED_DURING_RENDER\n")
            return self.fake_renderer(paths, output, course, submitter)

        with mock.patch.object(integration, "render_pdf", side_effect=mutate_after_snapshot):
            self.submit()
        self.assertEqual((self.server / source.name).read_bytes(), original)
        self.assertIn(b"SNAPSHOT_ORIGINAL", (self.server / "hw.pdf").read_bytes())
        self.assertNotIn(b"EDITED_DURING_RENDER", (self.server / "hw.pdf").read_bytes())
        self.assertEqual(source.read_bytes(), b"// EDITED_DURING_RENDER\n")

    def test_file_order_preserves_extension_groups_and_name_sort(self):
        for name in ("z.cpp", "공백 이름.h", "b.c", "a.cpp", "a.c", "a.h"):
            self.source(name, b"// source\n")
        seen = []

        def record_order(paths, output, course, submitter):
            seen.extend(Path(path).name for path in paths)
            return self.fake_renderer(paths, output, course, submitter)

        with mock.patch.object(integration, "render_pdf", side_effect=record_order):
            self.submit()
        self.assertEqual(seen, ["a.c", "b.c", "a.cpp", "z.cpp", "a.h", "공백 이름.h"])

    def test_renderer_failure_preserves_old_submission_and_preview(self):
        self.source()
        previous = self.old_submission()
        preview = self.sources / "hw.pdf"
        preview.write_bytes(b"old local PDF")
        with mock.patch.object(integration, "render_pdf", side_effect=OSError("PDF failure")):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assert_old_preserved(previous)
        self.assertEqual(preview.read_bytes(), b"old local PDF")
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_renderer_failure_does_not_create_destination(self):
        self.source()
        with mock.patch.object(integration, "render_pdf", side_effect=ValueError("invalid source")):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assertFalse(self.server.exists())

    def test_snapshot_copy_failure_preserves_old_submission(self):
        self.source()
        previous = self.old_submission()
        original_copy = integration.shutil.copy2

        def fail_snapshot(src, dst, *args, **kwargs):
            if Path(src).parent == self.sources and Path(src).suffix in {".c", ".cpp", ".h"}:
                raise OSError("snapshot copy failure")
            return original_copy(src, dst, *args, **kwargs)

        with mock.patch.object(integration.shutil, "copy2", side_effect=fail_snapshot):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assert_old_preserved(previous)
        self.assertEqual(list(self.sources.glob(".turnin-prepare-*")), [])

    def test_staged_copy_failure_preserves_old_submission(self):
        self.source()
        previous = self.old_submission()
        original_copy = integration.shutil.copy2
        staged = []

        def fail_second_staged_copy(src, dst, *args, **kwargs):
            if Path(dst).parent.name == "new" and ".turnin-recovery-" in str(dst):
                staged.append(Path(dst))
                if len(staged) == 2:
                    raise OSError("staged copy failure")
            return original_copy(src, dst, *args, **kwargs)

        with mock.patch.object(integration, "render_pdf", side_effect=self.fake_renderer):
            with mock.patch.object(integration.shutil, "copy2", side_effect=fail_second_staged_copy):
                with self.assertRaises(RuntimeError):
                    self.submit()
        self.assertEqual(len(staged), 2)
        self.assert_old_preserved(previous)
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_staged_chmod_failure_preserves_old_files_and_mode(self):
        self.source()
        previous = self.old_submission()
        original_chmod = integration.os.chmod
        injected = []

        def fail_file_chmod(path, mode, *args, **kwargs):
            target = Path(path)
            if target.parent.name == "new" and ".turnin-recovery-" in str(target):
                injected.append(target)
                raise OSError("staged file chmod failure")
            return original_chmod(path, mode, *args, **kwargs)

        with mock.patch.object(integration, "render_pdf", side_effect=self.fake_renderer):
            with mock.patch.object(integration.os, "chmod", side_effect=fail_file_chmod):
                with self.assertRaises(RuntimeError):
                    self.submit()
        self.assertTrue(injected)
        self.assert_old_preserved(previous)
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_mid_install_failure_restores_old_submission_and_mode(self):
        self.source()
        previous = self.old_submission()
        original_replace = integration.os.replace
        installed = []

        def fail_second_install(src, dst):
            if Path(src).parent.name == "new" and Path(dst).parent == self.server:
                installed.append(Path(dst))
                if len(installed) == 2:
                    raise OSError("mid-install failure")
            return original_replace(src, dst)

        with mock.patch.object(integration, "render_pdf", side_effect=self.fake_renderer):
            with mock.patch.object(integration.os, "replace", side_effect=fail_second_install):
                with self.assertRaises(RuntimeError):
                    self.submit()
        self.assertEqual(len(installed), 2)
        self.assert_old_preserved(previous)
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])

    def test_rollback_failure_retains_named_backup_with_old_pdf(self):
        self.source()
        previous = self.old_submission()
        original_replace = integration.os.replace
        installing = []

        def fail_install_and_pdf_restore(src, dst):
            source = Path(src)
            if source.parent.name == "new" and Path(dst).parent == self.server:
                installing.append(Path(dst))
                if len(installing) == 2:
                    raise OSError("install failure")
            if source.parent.name == "old" and source.name == "hw.pdf":
                raise OSError("rollback failure")
            return original_replace(src, dst)

        with mock.patch.object(integration, "render_pdf", side_effect=self.fake_renderer):
            with mock.patch.object(integration.os, "replace", side_effect=fail_install_and_pdf_restore):
                with self.assertRaises(RuntimeError) as error:
                    self.submit()
        recovery = list(self.server.glob(".turnin-recovery-*"))
        self.assertEqual(len(recovery), 1)
        self.assertIn(str(recovery[0]), str(error.exception))
        self.assertEqual((recovery[0] / "old" / "hw.pdf").read_bytes(), previous["hw.pdf"][0])
        self.assertEqual((self.server / ".teacher-note").read_bytes(), b"do not change\n")

    def test_destination_symlink_is_refused_without_touching_target(self):
        self.source()
        previous = self.old_submission()
        link = self.root / "linked submission"
        link.symlink_to(self.server, target_is_directory=True)
        with self.assertRaises((RuntimeError, ValueError)):
            self.submit(server_dir=link)
        self.assert_old_preserved(previous)

    def test_visible_nonregular_destination_entry_is_refused(self):
        self.source()
        previous = self.old_submission()
        nested = self.server / "unexpected folder"
        nested.mkdir()
        (nested / "preserve.txt").write_bytes(b"preserve nested content")
        with self.assertRaises((RuntimeError, ValueError)):
            self.submit()
        self.assertEqual((nested / "preserve.txt").read_bytes(), b"preserve nested content")
        nested_file = nested / "preserve.txt"
        nested_file.unlink()
        nested.rmdir()
        self.assert_old_preserved(previous)

    def test_overlapping_source_and_destination_are_refused(self):
        source = self.source()
        before = source.read_bytes()
        for destination in (self.sources, self.sources / "nested submission", self.root):
            with self.subTest(destination=destination):
                with self.assertRaises((RuntimeError, ValueError)):
                    self.submit(server_dir=destination)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.sources / "nested submission").exists())

    def test_concurrent_patched_calls_publish_one_complete_submission(self):
        first = self.sources
        (first / "first.c").write_bytes(b"// FIRST_SUBMISSION\n")
        second = self.root / "second source"
        second.mkdir()
        (second / "second.cpp").write_bytes(b"// SECOND_SUBMISSION\n")
        self.old_submission()
        first_install = threading.Event()
        release_first = threading.Event()
        second_prepared = threading.Event()
        second_install = threading.Event()
        errors = []
        original_replace = integration.os.replace

        def renderer(paths, output, course, submitter):
            result = self.fake_renderer(paths, output, course, submitter)
            if threading.current_thread().name == "second-submit":
                second_prepared.set()
            return result

        def gated_replace(src, dst):
            if Path(src).parent.name == "new" and Path(dst).parent == self.server:
                if threading.current_thread().name == "first-submit" and not first_install.is_set():
                    first_install.set()
                    if not release_first.wait(5):
                        raise OSError("timed out waiting to release first submission")
                elif threading.current_thread().name == "second-submit":
                    second_install.set()
            return original_replace(src, dst)

        def worker(directory):
            try:
                self.submit(source_dir=directory)
            except Exception as error:
                errors.append(error)

        first_thread = threading.Thread(target=worker, args=(first,), name="first-submit")
        second_thread = threading.Thread(target=worker, args=(second,), name="second-submit")
        with mock.patch.object(integration, "render_pdf", side_effect=renderer):
            with mock.patch.object(integration.os, "replace", side_effect=gated_replace):
                try:
                    first_thread.start()
                    self.assertTrue(first_install.wait(5), "first call did not reach publishing")
                    second_thread.start()
                    self.assertTrue(second_prepared.wait(5), "second call did not prepare its PDF")
                    self.assertFalse(second_install.wait(0.2), "second call bypassed destination lock")
                finally:
                    release_first.set()
                    first_thread.join(5)
                    if second_thread.ident is not None:
                        second_thread.join(5)
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(second_install.is_set())
        self.assertEqual({path.name for path in self.server.iterdir() if not path.name.startswith(".")},
                         {"second.cpp", "hw.pdf"})
        self.assertEqual((self.server / "second.cpp").read_bytes(), b"// SECOND_SUBMISSION\n")
        self.assertIn(b"SECOND_SUBMISSION", (self.server / "hw.pdf").read_bytes())
        self.assertNotIn(b"FIRST_SUBMISSION", (self.server / "hw.pdf").read_bytes())
        self.assertEqual(list(self.server.glob(".turnin-recovery-*")), [])


if __name__ == "__main__":
    unittest.main()
