"""Check the page geometry measured from the school's Enscript output.

Coordinates below are points in the visible landscape page. They deliberately
come from the reference output, rather than importing renderer constants.
"""

import re
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from turnin_demo.pdf import render_pdf


class LegacyLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="turnin-layout-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def render(self, text, course="Course", filename="example.cpp"):
        source = self.root / filename
        source.write_text(text, encoding="utf-8")
        output = self.root / "listing.pdf"
        render_pdf([source], output, course, "student")
        return output

    @staticmethod
    def spans(page):
        result = []

        def visit(text, cm, tm, font, size):
            if text.strip():
                # Compose the text origin with the current transformation.
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                result.append({
                    "text": text.rstrip("\n"), "x": x, "y": y,
                    "size": size, "font": str(font.get("/BaseFont", "")),
                })

        page.extract_text(visitor_text=visit)
        return result

    def marker(self, page, text):
        found = [span for span in self.spans(page) if text in span["text"]]
        self.assertEqual(len(found), 1, "Expected one text span containing " + text)
        return found[0]

    def test_school_frame_header_and_ascii_font(self):
        output = self.render("// FIRST_LINE\n// SECOND_LINE\n")
        page = PdfReader(output).pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 842, delta=0.2)
        self.assertAlmostEqual(float(page.mediabox.height), 595, delta=0.3)
        operations = page.get_contents().operations
        rectangles = [tuple(float(value) for value in args)
                      for args, operator in operations if operator == b"re"]
        self.assertTrue(any(
            all(abs(actual - expected) < 0.2 for actual, expected in zip(rect, (36, 18, 770, 544)))
            for rect in rectangles
        ), "The original outer frame must remain at (36, 18, 770, 544)")
        paths = []
        start = None
        for args, operator in operations:
            if operator == b"m":
                start = tuple(float(value) for value in args)
            elif operator == b"l" and start is not None:
                paths.append((start, tuple(float(value) for value in args)))
        self.assertTrue(any(
            abs(start[0] - 421) < 0.2 and abs(end[0] - 421) < 0.2
            and sorted((round(start[1], 1), round(end[1], 1))) == [18.0, 562.0]
            for start, end in paths
        ), "The full-height center divider must remain at x=421")

        left = self.marker(page, "[Course] student : example.cpp")
        self.assertAlmostEqual(left["x"], 41, delta=0.1)
        self.assertAlmostEqual(left["y"], 565.3332, delta=0.1)
        header = [span for span in self.spans(page) if span["y"] > 562]
        dates = [span for span in header
                 if re.fullmatch(r"\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", span["text"])]
        self.assertEqual(len(dates), 1)
        date = dates[0]
        # The original header uses fixed-width Courier at ten points.
        self.assertAlmostEqual(date["x"] + len(date["text"]) * date["size"] * 0.6 / 2,
                               421, delta=0.2)
        page_label = self.marker(page, "1/1")
        self.assertAlmostEqual(page_label["x"] + 3 * page_label["size"] * 0.6,
                               801, delta=0.2)
        first = self.marker(page, "FIRST_LINE")
        second = self.marker(page, "SECOND_LINE")
        self.assertTrue(first["font"].startswith("/Courier"))
        self.assertAlmostEqual(first["size"], 7, delta=0.01)
        self.assertAlmostEqual(first["x"], 71.4, delta=0.1)
        self.assertAlmostEqual(first["y"], 552, delta=0.1)
        self.assertAlmostEqual(first["y"] - second["y"], 8, delta=0.1)
        first_number = [span for span in self.spans(page)
                        if span["text"].strip() == "1:" and abs(span["y"] - 552) < 0.1]
        self.assertEqual(len(first_number), 1)
        self.assertAlmostEqual(first_number[0]["x"] + 2 * 7 * 0.6, 67.2, delta=0.1)
        self.assertNotIn("LOCAL DEMO", page.extract_text())

    def test_column_and_page_boundaries_preserve_line_order(self):
        output = self.render("".join("// ROW_%03d\n" % number for number in range(1, 136)))
        pages = PdfReader(output).pages
        self.assertEqual(len(pages), 2)
        for page_index, number, x, y in (
            (0, 1, 71.4, 552), (0, 67, 71.4, 24),
            (0, 68, 456.4, 552), (0, 134, 456.4, 24),
            (1, 135, 71.4, 552),
        ):
            with self.subTest(line=number):
                span = self.marker(pages[page_index], "ROW_%03d" % number)
                self.assertAlmostEqual(span["x"], x, delta=0.1)
                self.assertAlmostEqual(span["y"], y, delta=0.1)
        markers = re.findall(r"ROW_\d{3}", "\n".join(page.extract_text() for page in pages))
        self.assertEqual(markers, ["ROW_%03d" % number for number in range(1, 136)])

    def test_mixed_korean_wrapping_keeps_every_character(self):
        source = "// " + " ".join("한글%03dABC" % index for index in range(100)) + " END_SENTINEL\n"
        output = self.render(source)
        body = []
        for page in PdfReader(output).pages:
            body.extend(span for span in self.spans(page)
                        if 18 < span["y"] < 562 and not re.fullmatch(r"\s*\d+:\s*", span["text"]))
        reconstructed = "".join("".join(span["text"].split()) for span in body)
        self.assertEqual(reconstructed, "".join(source.split()))
        self.assertTrue(any(abs(span["x"] - 41) < 0.1 and span["y"] < 552 for span in body),
                        "Wrapped rows must use the original unnumbered continuation position")

    def test_long_header_fits_without_overlapping_date_or_replacing_on_error(self):
        output = self.render("// source\n", course="LongName" * 9)
        page = PdfReader(output).pages[0]
        left = self.marker(page, "[LongName")
        date = next(span for span in self.spans(page)
                    if re.fullmatch(r"\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}", span["text"]))
        self.assertGreaterEqual(left["size"], 5)
        self.assertLess(left["size"], 10)
        self.assertLess(left["x"] + len(left["text"]) * left["size"] * 0.6, date["x"])
        previous = output.read_bytes()
        with self.assertRaises(ValueError):
            render_pdf([self.root / "example.cpp"], output, "LongName" * 100, "student")
        self.assertEqual(output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
