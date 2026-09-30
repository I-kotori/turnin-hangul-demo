"""UTF-8 C/C++ listings with embedded Korean fonts and atomic PDF output."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import tempfile
import unicodedata

from pygments import lex
from pygments.lexers import CLexer, CppLexer
from pygments.styles import get_style_by_name
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
REGULAR = "TurninNanumRegular"
BOLD = "TurninNanumBold"
WIDTH, HEIGHT = landscape(A4)
MARGIN = 30.0
GAP = 18.0
NUMBER_WIDTH = 29.0
COLUMN_WIDTH = (WIDTH - 2 * MARGIN - GAP) / 2
TEXT_WIDTH = COLUMN_WIDTH - NUMBER_WIDTH - 9
FONT_SIZE = 8.3
LINE_HEIGHT = 11.3
CODE_TOP = HEIGHT - 77
CODE_BOTTOM = 44.0
ROWS_PER_COLUMN = int((CODE_TOP - CODE_BOTTOM) / LINE_HEIGHT) + 1


@dataclass
class Row:
    number: int | None
    segments: list[tuple[str, str, bool]]


def _fonts() -> None:
    for name, filename in ((REGULAR, "NanumGothicCoding-Regular.ttf"), (BOLD, "NanumGothicCoding-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))


def _text(value: str, label: str) -> str:
    value = unicodedata.normalize("NFC", value)
    glyphs = pdfmetrics.getFont(REGULAR).face.charWidths
    missing = sorted({ch for ch in value if ch not in "\n\r\t" and (ord(ch) < 32 or ord(ch) not in glyphs)})
    if missing:
        codes = ", ".join(f"U+{ord(ch):04X}" for ch in missing[:8])
        raise ValueError(f"{label}: bundled font cannot display {codes}")
    return value


def _source_rows(path: Path) -> list[Row]:
    # Decode strictly; never replace invalid bytes with an invisible loss.
    source = _text(path.read_text(encoding="utf-8-sig"), path.name).expandtabs(4)
    lexer = (CppLexer if path.suffix == ".cpp" else CLexer)(stripnl=False, ensurenl=False)
    style = get_style_by_name("default")
    logical: list[list[tuple[str, str, bool]]] = [[]]
    for token, value in lex(source, lexer):
        spec = style.style_for_token(token)
        for index, part in enumerate(value.split("\n")):
            if index:
                logical.append([])
            if part:
                logical[-1].append((part, spec.get("color") or "242b36", bool(spec.get("bold"))))
    if source.endswith("\n") and len(logical) > 1 and not logical[-1]:
        logical.pop()
    rows: list[Row] = []
    for number, segments in enumerate(logical, 1):
        current = Row(number, [])
        used = 0.0
        for text, color, bold in segments:
            font = BOLD if bold else REGULAR
            for char in text:
                advance = pdfmetrics.stringWidth(char, font, FONT_SIZE)
                if used + advance > TEXT_WIDTH and current.segments:
                    rows.append(current)
                    current = Row(None, [])
                    used = 0.0
                if current.segments and current.segments[-1][1:] == (color, bold):
                    old = current.segments[-1]
                    current.segments[-1] = (old[0] + char, color, bold)
                else:
                    current.segments.append((char, color, bold))
                used += advance
        rows.append(current)
    return rows


def _fit(canvas: Canvas, text: str, x: float, y: float, max_width: float, size: float, font: str = REGULAR) -> None:
    width = pdfmetrics.stringWidth(text, font, size)
    if width > max_width:
        size *= max_width / width
    if size < 5.0:
        raise ValueError("Course, submitter, or filename is too long for a readable PDF header")
    canvas.setFont(font, size)
    canvas.drawString(x, y, text)


def render_pdf(sources: list[Path], output: Path, course: str, submitter: str) -> Path:
    """Create a PDF, replacing output only after successful complete rendering.

    Original files are only read. School configuration and submission paths are
    never accessed. Each source starts on a fresh landscape page.
    """
    _fonts()
    if not sources:
        raise ValueError("No .c, .cpp, or .h source files were provided")
    course = _text(course, "course").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    submitter = _text(submitter, "submitter").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    output = Path(output)
    pages = []
    for raw in sources:
        source = Path(raw)
        if source.is_symlink() or not source.is_file() or source.suffix not in {".c", ".cpp", ".h"}:
            raise ValueError(f"Not a regular C/C++ source file: {source}")
        if source.resolve() == output.resolve():
            raise ValueError("Output must not overwrite a source file")
        filename = _text(source.name, "filename").replace("\n", " ").replace("\r", " ").replace("\t", " ")
        rows = _source_rows(source)
        page_size = 2 * ROWS_PER_COLUMN
        for start in range(0, len(rows), page_size):
            pages.append((filename, rows[start:start + page_size]))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".render-", suffix=".pdf", dir=output.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        canvas = Canvas(str(temp_path), pagesize=(WIDTH, HEIGHT), pageCompression=1)
        canvas.setTitle(f"{course} - {submitter}")
        canvas.setAuthor("Local mock submission")
        canvas.setCreator("turnin-hangul-demo / ReportLab")
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
        for index, (filename, rows) in enumerate(pages, 1):
            canvas.setFillColor(colors.HexColor("#172b46"))
            _fit(canvas, course, MARGIN, HEIGHT - 29, WIDTH - 2 * MARGIN, 13, BOLD)
            _fit(canvas, f"{submitter}  /  {filename}", MARGIN, HEIGHT - 48, WIDTH - 2 * MARGIN - 155, 9)
            canvas.setFont(REGULAR, 8)
            canvas.drawRightString(WIDTH - MARGIN, HEIGHT - 48, f"{index} / {len(pages)}")
            canvas.setStrokeColor(colors.HexColor("#c9d3df"))
            canvas.setLineWidth(0.5)
            canvas.line(MARGIN, HEIGHT - 59, WIDTH - MARGIN, HEIGHT - 59)
            canvas.line(WIDTH / 2, CODE_BOTTOM - 7, WIDTH / 2, HEIGHT - 66)
            for row_index, row in enumerate(rows):
                column, position = divmod(row_index, ROWS_PER_COLUMN)
                x = MARGIN + column * (COLUMN_WIDTH + GAP)
                y = CODE_TOP - position * LINE_HEIGHT
                canvas.setFont(REGULAR, 7.4)
                canvas.setFillColor(colors.HexColor("#7c899a"))
                canvas.drawRightString(x + NUMBER_WIDTH - 7, y, str(row.number) if row.number is not None else ">")
                x += NUMBER_WIDTH
                for text, color, bold in row.segments:
                    font = BOLD if bold else REGULAR
                    canvas.setFont(font, FONT_SIZE)
                    canvas.setFillColor(colors.HexColor("#" + color))
                    canvas.drawString(x, y, text)
                    x += pdfmetrics.stringWidth(text, font, FONT_SIZE)
            canvas.setFillColor(colors.HexColor("#6c7888"))
            canvas.setFont(REGULAR, 7)
            canvas.drawString(MARGIN, 23, "LOCAL DEMO  |  UTF-8 / embedded Korean font")
            canvas.drawRightString(WIDTH - MARGIN, 23, timestamp)
            canvas.showPage()
        canvas.save()
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    return output
