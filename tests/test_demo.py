"""Regression checks for readable Korean PDFs and recoverable mock submissions."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfReader

from turnin_demo.pdf import render_pdf
from turnin_demo.submission import SubmissionError, collect_sources, submit


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="turnin-hangul-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "학생 과제"
        self.sources.mkdir()
        self.output_root = self.root / "모의 제출함"

    def source(self, name="한글 주석.cpp", text=None):
        path = self.sources / name
        path.write_text(
            text if text is not None else
            '// 한글 주석이 보입니다\n#include <stdio.h>\n'
            'int main(void) { printf("안녕하세요\\n"); return 0; }\n',
            encoding="utf-8",
        )
        return path

    def do_submit(self, **kwargs):
        return submit(
            self.sources, self.output_root,
            course="알고리즘 과제", submitter="demo-student", **kwargs,
        )

    @staticmethod
    def pdf_text(path):
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)

    def test_korean_headers_comments_and_filenames_are_extractable(self):
        source = self.source()
        output = self.root / "한글 결과.pdf"
        result = render_pdf(
            [source], output, course="알고리즘 과제", submitter="테스트 학생"
        )
        self.assertEqual(Path(result).resolve(), output.resolve())
        text = self.pdf_text(output)
        for expected in ("알고리즘 과제", "한글 주석이 보입니다", "안녕하세요"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertIn("한글 주석.cpp", text)

    def test_korean_font_is_embedded_with_unicode_mapping(self):
        output = self.root / "embedded.pdf"
        render_pdf([self.source()], output, "알고리즘 과제", "테스트 학생")
        reader = PdfReader(output)
        unicode_embedded = []
        for page in reader.pages:
            resources = page["/Resources"].get_object()
            for reference in resources["/Font"].get_object().values():
                font = reference.get_object()
                descriptors = []
                if "/FontDescriptor" in font:
                    descriptors.append(font["/FontDescriptor"].get_object())
                for descendant in font.get("/DescendantFonts", []):
                    descendant = descendant.get_object()
                    if "/FontDescriptor" in descendant:
                        descriptors.append(descendant["/FontDescriptor"].get_object())
                if "/ToUnicode" in font and any(
                    "/FontFile2" in descriptor or "/FontFile3" in descriptor
                    for descriptor in descriptors
                ):
                    unicode_embedded.append(font)
        self.assertTrue(unicode_embedded, "A Unicode font must be embedded in the PDF")

    def test_wrapping_and_page_overflow_keep_the_last_source_content(self):
        long_line = "// " + "한글과긴줄검사 " * 140 + "LONG_END_MARKER\n"
        body = "".join("// 줄 번호 검사 %04d\n" % index for index in range(550))
        source = self.source(text=long_line + body + "// FINAL_SOURCE_SENTINEL 끝까지\n")
        output = self.root / "many-pages.pdf"
        render_pdf([source], output, "여러 페이지 과제", "테스트 학생")
        reader = PdfReader(output)
        self.assertGreater(len(reader.pages), 1)
        compact = "".join(self.pdf_text(output).split())
        self.assertIn("LONG_END_MARKER", compact)
        self.assertIn("FINAL_SOURCE_SENTINEL끝까지", compact)

    def test_invalid_utf8_preserves_an_existing_pdf(self):
        source = self.source()
        output = self.root / "existing.pdf"
        render_pdf([source], output, "과제", "학생")
        original = output.read_bytes()
        source.write_bytes(b"// invalid UTF-8: \xff\xfe\n")
        with self.assertRaises((ValueError, UnicodeError, RuntimeError)):
            render_pdf([source], output, "과제", "학생")
        self.assertEqual(output.read_bytes(), original)

    def test_empty_source_list_preserves_an_existing_pdf(self):
        output = self.root / "existing.pdf"
        render_pdf([self.source()], output, "과제", "학생")
        original = output.read_bytes()
        with self.assertRaises(ValueError):
            render_pdf([], output, "과제", "학생")
        self.assertEqual(output.read_bytes(), original)

    def test_pdf_save_failure_preserves_an_existing_pdf(self):
        source = self.source()
        output = self.root / "existing.pdf"
        render_pdf([source], output, "과제", "학생")
        original = output.read_bytes()
        with mock.patch("turnin_demo.pdf.Canvas.save", side_effect=OSError("simulated full disk")):
            with self.assertRaises(OSError):
                render_pdf([source], output, "과제", "학생")
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(list(self.root.glob(".render-*.pdf")), [])

    def test_unsupported_glyph_preserves_an_existing_pdf(self):
        source = self.source()
        output = self.root / "existing.pdf"
        render_pdf([source], output, "과제", "학생")
        original = output.read_bytes()
        source.write_text("// unsupported glyph: 🚀\n", encoding="utf-8")
        with self.assertRaises((ValueError, RuntimeError)):
            render_pdf([source], output, "과제", "학생")
        self.assertEqual(output.read_bytes(), original)

    def test_source_collection_handles_spaces_and_korean_names(self):
        cpp = self.source("공백 있는 이름.cpp")
        c_file = self.source("예제.c", "// C 한글\n")
        header = self.source("헤더 파일.h", "// 헤더\n")
        self.source("ignored.txt", "This is not a source file.\n")
        found = collect_sources(self.sources)
        self.assertEqual(
            {Path(path).resolve() for path in found},
            {path.resolve() for path in (cpp, c_file, header)},
        )

    def test_multiple_source_files_all_appear_in_pdf(self):
        sources = [
            self.source("가 파일.c", "// 첫 번째 소스 SOURCE_C\n"),
            self.source("나 파일.cpp", "// 두 번째 소스 SOURCE_CPP\n"),
            self.source("다 파일.h", "// 세 번째 소스 SOURCE_HEADER\n"),
        ]
        output = self.root / "all-sources.pdf"
        render_pdf(sources, output, "여러 파일 과제", "학생")
        text = self.pdf_text(output)
        for source in sources:
            with self.subTest(source=source.name):
                self.assertIn(source.name, text)
                self.assertIn(source.read_text(encoding="utf-8").strip(), text)

    def test_successful_resubmission_keeps_the_old_bundle(self):
        source = self.source()
        first = self.do_submit()
        for field in ("bundle", "current", "receipt", "pdf"):
            self.assertTrue(Path(first[field]).is_absolute(), field)
            self.assertTrue(Path(first[field]).exists(), field)
        original_pdf = Path(first["pdf"]).read_bytes()
        original_receipt = Path(first["receipt"]).read_bytes()
        first_pointer = Path(first["current"]).read_bytes()
        json.loads(first_pointer)
        source.write_text("// 두 번째 제출\nint main() { return 0; }\n", encoding="utf-8")
        second = self.do_submit()
        self.assertNotEqual(first["bundle"], second["bundle"])
        self.assertEqual(first["current"], second["current"])
        self.assertNotEqual(Path(second["current"]).read_bytes(), first_pointer)
        self.assertEqual(Path(first["pdf"]).read_bytes(), original_pdf)
        self.assertEqual(Path(first["receipt"]).read_bytes(), original_receipt)
        self.assertIn("두 번째 제출", self.pdf_text(second["pdf"]))

    def test_renderer_failure_preserves_current_submission(self):
        self.source()
        first = self.do_submit()
        pointer = Path(first["current"]).read_bytes()
        pdf = Path(first["pdf"]).read_bytes()

        def fail_renderer(*args, **kwargs):
            raise RuntimeError("intentional PDF conversion failure")

        with self.assertRaises(SubmissionError):
            self.do_submit(renderer=fail_renderer)
        self.assertEqual(Path(first["current"]).read_bytes(), pointer)
        self.assertEqual(Path(first["pdf"]).read_bytes(), pdf)

    def test_copy_failure_preserves_current_submission(self):
        self.source()
        first = self.do_submit()
        previous = {
            name: Path(first[name]).read_bytes()
            for name in ("current", "pdf", "receipt")
        }
        original_write = Path.write_bytes

        def fail_staging_copy(path, data):
            if path.parent.name == "sources":
                raise OSError("simulated source copy failure")
            return original_write(path, data)

        with mock.patch("turnin_demo.submission.Path.write_bytes", new=fail_staging_copy):
            with self.assertRaises((OSError, SubmissionError)):
                self.do_submit()
        for name, contents in previous.items():
            with self.subTest(artifact=name):
                self.assertEqual(Path(first[name]).read_bytes(), contents)
        self.assertEqual(list(Path(first["bundle"]).parent.glob(".pending-*")), [])

    def test_invalid_utf8_resubmission_preserves_current_submission(self):
        source = self.source()
        first = self.do_submit()
        pointer = Path(first["current"]).read_bytes()
        source.write_bytes(b"// broken UTF-8: \xff\n")
        with self.assertRaises(SubmissionError):
            self.do_submit()
        self.assertEqual(Path(first["current"]).read_bytes(), pointer)
        self.assertIn("한글 주석이 보입니다", self.pdf_text(first["pdf"]))

    def test_empty_resubmission_preserves_current_submission(self):
        source = self.source()
        first = self.do_submit()
        pointer = Path(first["current"]).read_bytes()
        source.unlink()
        with self.assertRaises(SubmissionError):
            self.do_submit()
        self.assertEqual(Path(first["current"]).read_bytes(), pointer)
        self.assertTrue(Path(first["pdf"]).is_file())


if __name__ == "__main__":
    unittest.main()
