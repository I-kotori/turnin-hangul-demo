"""UTF-8 C/C++ listings with embedded Korean fonts and atomic PDF output."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from pathlib import Path
import os
import tempfile
import unicodedata

from pygments import lex
from pygments.lexers import CLexer, CppLexer
from pygments.token import Comment, Keyword, Name, String
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
REGULAR = "TurninNanumRegular"
BOLD = "TurninNanumBold"
# Measured from the school's Enscript -2rj output (points, visible landscape).
WIDTH, HEIGHT = 842.0, 595.0
LEFT, RIGHT, BOTTOM, TOP = 36.0, 806.0, 18.0, 562.0
COLUMN_WIDTH = (RIGHT - LEFT) / 2
INSET, NUMBER_WIDTH = 5.0, 30.4
FONT_SIZE, LINE_HEIGHT = 7.0, 8.0
CODE_TOP = 552.0
ROWS_PER_COLUMN = 67
HEADER_Y = TOP + 10.0 / 3


@dataclass
class Row:
    number: int | None
    segments: list[tuple[str, str, str]]


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


def _font_runs(text: str, font: str):
    # Courier retains the old ASCII metrics; embedded Nanum supplies Hangul.
    # Nanum's half/full-width cells are scaled to Courier's 0.6/1.2-em grid.
    for non_ascii, chars in groupby(text, key=lambda char: ord(char) > 127):
        fallback = BOLD if "Bold" in font else REGULAR
        yield "".join(chars), fallback if non_ascii else font, 1.2 if non_ascii else 1.0


def _width(text: str, font: str, size: float) -> float:
    return sum(pdfmetrics.stringWidth(run, face, size) * scale
               for run, face, scale in _font_runs(text, font))


def _draw(canvas: Canvas, text: str, x: float, y: float, font: str, size: float) -> None:
    obj = canvas.beginText(x, y)
    for run, face, scale in _font_runs(text, font):
        obj.setFont(face, size)
        obj.setHorizScale(scale * 100)
        obj.textOut(run)
    canvas.drawText(obj)


def _style(token, value: str) -> tuple[str, str]:
    # Enscript's familiar C/C++ palette. Pygments supplies token boundaries.
    if token in Comment.PreprocFile or token in String:
        return "bc8f8f", "Courier-Bold"
    if token in Comment.Preproc:
        return ("000000", "Courier") if value == "#" else ("5f9ea0", "Courier-Bold")
    if token in Comment:
        return "b22222", "Courier-Oblique"
    if token in Keyword.Type or value in {"const", "static", "volatile"}:
        return "228b22", "Courier-Bold"
    if token in Keyword:
        return "a020f0", "Courier-Bold"
    if token in Name.Function:
        return "0000ff", "Courier-Bold"
    if token in Name.Namespace or value == "std":
        return "5f9ea0", "Courier-Bold"
    return "000000", "Courier"


def _source_rows(path: Path) -> list[Row]:
    # Decode strictly; original source bytes are never rewritten.
    source = _text(path.read_text(encoding="utf-8-sig"), path.name).expandtabs(8)
    lexer = (CppLexer if path.suffix == ".cpp" else CLexer)(stripnl=False, ensurenl=False)
    logical: list[list[tuple[str, str, str]]] = [[]]
    for token, value in lex(source, lexer):
        color, font = _style(token, value)
        for index, part in enumerate(value.split("\n")):
            if index:
                logical.append([])
            logical[-1].extend((char, color, font) for char in part)
    if source.endswith("\n") and len(logical) > 1 and not logical[-1]:
        logical.pop()
    rows: list[Row] = []
    for number, chars in enumerate(logical, 1):
        if not chars:
            rows.append(Row(number, []))
            continue
        start = 0
        while start < len(chars):
            limit = COLUMN_WIDTH - 2 * INSET - (NUMBER_WIDTH if start == 0 else 0)
            end, last_space, used = start, start, 0.0
            while end < len(chars):
                char, _, font = chars[end]
                advance = _width(char, font, FONT_SIZE)
                if used + advance > limit + 0.001:
                    break
                used += advance
                end += 1
                if char.isspace():
                    last_space = end
            if end < len(chars) and last_space > start:
                end = last_space
            if end == start:
                raise ValueError("A source glyph is wider than the available column")
            segments = []
            for char, color, font in chars[start:end]:
                if segments and segments[-1][1:] == (color, font):
                    segments[-1] = (segments[-1][0] + char, color, font)
                else:
                    segments.append((char, color, font))
            rows.append(Row(number if start == 0 else None, segments))
            start = end
    return rows


def _header(canvas: Canvas, left_text: str, timestamp: str, page: int, total: int) -> None:
    font, size = "Courier-Bold", 10.0
    date_x = (WIDTH - _width(timestamp, font, size)) / 2
    max_width = date_x - 8 - (LEFT + INSET)
    width = _width(left_text, font, size)
    if width > max_width:
        size *= max_width / width
    if size < 5.0:
        raise ValueError("Course, submitter, or filename is too long for a readable PDF header")
    canvas.setFillColor(colors.black)
    _draw(canvas, left_text, LEFT + INSET, HEADER_Y, font, size)
    _draw(canvas, timestamp, date_x, HEADER_Y, font, 10)
    label = f"{page}/{total}"
    _draw(canvas, label, RIGHT - INSET - _width(label, font, 10), HEADER_Y, font, 10)


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
        total = (len(rows) + page_size - 1) // page_size
        for start in range(0, len(rows), page_size):
            pages.append((filename, rows[start:start + page_size], start // page_size + 1, total))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".render-", suffix=".pdf", dir=output.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        canvas = Canvas(str(temp_path), pagesize=(WIDTH, HEIGHT), pageCompression=1)
        canvas.setTitle(f"{course} - {submitter}")
        canvas.setAuthor("Local mock submission")
        canvas.setCreator("turnin-hangul-demo / ReportLab")
        timestamp = datetime.now().astimezone().strftime("%m/%d/%y %H:%M:%S")
        for filename, rows, page, total in pages:
            _header(canvas, f"[{course}] {submitter} : {filename}", timestamp, page, total)
            canvas.setStrokeColor(colors.black)
            canvas.setLineWidth(0)
            canvas.rect(LEFT, BOTTOM, RIGHT - LEFT, TOP - BOTTOM, stroke=1, fill=0)
            canvas.line(WIDTH / 2, BOTTOM, WIDTH / 2, TOP)
            for row_index, row in enumerate(rows):
                column, position = divmod(row_index, ROWS_PER_COLUMN)
                x = LEFT + column * COLUMN_WIDTH + INSET
                y = CODE_TOP - position * LINE_HEIGHT
                if row.number is not None:
                    label = f"{row.number}:"
                    canvas.setFillColor(colors.black)
                    _draw(canvas, label, x + NUMBER_WIDTH - 4.2 - _width(label, "Courier", FONT_SIZE),
                          y, "Courier", FONT_SIZE)
                    x += NUMBER_WIDTH
                for text, color, font in row.segments:
                    canvas.setFillColor(colors.HexColor("#" + color))
                    _draw(canvas, text, x, y, font, FONT_SIZE)
                    x += _width(text, font, FONT_SIZE)
            canvas.showPage()
        canvas.save()
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    return output
