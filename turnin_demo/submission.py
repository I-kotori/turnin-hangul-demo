"""Local submission simulation with immutable successful revisions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timezone
from uuid import uuid4


class SubmissionError(ValueError):
    """A source or destination is unsuitable for a local submission."""


def collect_sources(source_dir: Path) -> list[Path]:
    """Read only top-level .c, .cpp and .h files; never follow source symlinks."""
    source_dir = Path(source_dir).expanduser().absolute()
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise SubmissionError("소스 경로는 심볼릭 링크가 아닌 디렉터리여야 합니다.")
    result = []
    for path in sorted(source_dir.iterdir(), key=lambda item: item.name):
        if path.suffix not in {".c", ".cpp", ".h"}:
            continue
        if path.is_symlink():
            raise SubmissionError(f"심볼릭 링크 소스는 제출할 수 없습니다: {path.name}")
        if not path.is_file():
            raise SubmissionError(f"일반 소스 파일이 아닙니다: {path.name}")
        result.append(path)
    if not result:
        raise SubmissionError("제출할 .c, .cpp, .h 파일이 없습니다.")
    return result


def course_slug(course: str) -> str:
    if not course.strip() or len(course) > 160 or any(ord(c) < 32 for c in course):
        raise SubmissionError("과목명은 1~160자의 한 줄 문자열이어야 합니다.")
    slug = re.sub(r"[^\w-]+", "-", course.strip()).strip("-_")[:48] or "course"
    return slug + "-" + hashlib.sha256(course.encode("utf-8")).hexdigest()[:8]


def _directory(path: Path) -> Path:
    if path.is_symlink():
        raise SubmissionError(f"출력 디렉터리는 심볼릭 링크일 수 없습니다: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise SubmissionError(f"출력 경로가 디렉터리가 아닙니다: {path}")
    return path


def submit(source_dir: Path, output_root: Path, course: str,
           submitter: str, renderer=None) -> dict:
    """Create a complete bundle, then atomically update current.json.

    ``renderer`` has the render_pdf(sources, output, course, submitter) signature.
    It is injectable for failure-path tests. A failed attempt never changes an
    existing current.json. Return absolute bundle/current/receipt/pdf paths.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", submitter):
        raise SubmissionError("제출자 ID는 영문·숫자로 시작하는 영문·숫자·_- 1~64자여야 합니다.")
    slug = course_slug(course)
    sources = collect_sources(source_dir)
    root = _directory(Path(output_root).expanduser().absolute())
    submissions = _directory(root / "submissions")
    course_dir = _directory(submissions / slug)
    student_dir = _directory(course_dir / submitter)
    bundles = _directory(student_dir / "bundles")
    current_path = student_dir / "current.json"
    if current_path.is_symlink():
        raise SubmissionError("current.json 심볼릭 링크는 사용할 수 없습니다.")
    if renderer is None:
        from .pdf import render_pdf
        renderer = render_pdf
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=str(bundles)))
    pointer_temp = None
    committed = False
    try:
        staged_sources = _directory(staging / "sources")
        entries = []
        for source in sources:
            # O_NOFOLLOW also rejects a symlink swapped in after enumeration.
            fd = os.open(str(source), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                data = handle.read()
            target = staged_sources / source.name
            target.write_bytes(data)
            entries.append({"name": source.name, "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()})
        pdf = staging / "hw.pdf"
        try:
            renderer([staged_sources / entry["name"] for entry in entries], pdf, course, submitter)
        except Exception as error:
            raise SubmissionError(f"PDF 생성 실패: {error}") from error
        if not pdf.is_file() or pdf.is_symlink():
            raise SubmissionError("PDF 생성기가 PDF 파일을 만들지 않았습니다.")
        pdf_data = pdf.read_bytes()
        if not pdf_data.startswith(b"%PDF-") or len(pdf_data) < 100:
            raise SubmissionError("PDF 생성 결과가 유효한 PDF 형식이 아닙니다.")
        receipt = {
            "schema_version": 1, "mode": "local-simulation",
            "revision": revision, "course": course, "submitter": submitter,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sources": entries,
            "pdf": {"name": "hw.pdf", "bytes": len(pdf_data),
                    "sha256": hashlib.sha256(pdf_data).hexdigest()},
        }
        (staging / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        bundle = bundles / revision
        os.rename(staging, bundle)
        committed = True
        pointer = {"schema_version": 1, "revision": revision,
                   "bundle": f"bundles/{revision}", "receipt": f"bundles/{revision}/receipt.json"}
        fd, temporary_name = tempfile.mkstemp(prefix=".current-", suffix=".json", dir=str(student_dir))
        pointer_temp = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(pointer, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pointer_temp, current_path)
        return {"revision": revision, "bundle": str(bundle),
                "current": str(current_path), "receipt": str(bundle / "receipt.json"),
                "pdf": str(bundle / "hw.pdf"), "data": receipt}
    finally:
        if not committed:
            shutil.rmtree(staging, ignore_errors=True)
        if pointer_temp is not None and pointer_temp.exists():
            pointer_temp.unlink()
