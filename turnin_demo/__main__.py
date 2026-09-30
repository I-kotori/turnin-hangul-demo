"""Run ``python -m turnin_demo demo`` for a completely local demonstration."""
from __future__ import annotations

import argparse
from functools import partial
import html
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import sys
import tempfile

from .submission import SubmissionError, collect_sources, submit

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_COURSE = "알고리즘 과제 · 한글 PDF"


def create_dashboard(result: dict, output_root: Path) -> Path:
    """Create a static HTML dashboard with no network assets or JavaScript."""
    dashboard_dir = Path(output_root).absolute() / "demo"
    if dashboard_dir.is_symlink():
        raise SubmissionError("데모 출력 경로는 심볼릭 링크일 수 없습니다.")
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "hw.pdf", "receipt.json", "verification.json", "REPORT.md"):
        if (dashboard_dir / name).is_symlink():
            raise SubmissionError(f"데모 출력 파일이 심볼릭 링크입니다: {name}")
    # Copies make the PDF preview portable even when opening HTML with file://.
    shutil.copyfile(result["pdf"], dashboard_dir / "hw.pdf")
    shutil.copyfile(result["receipt"], dashboard_dir / "receipt.json")
    report = PROJECT / "REPORT.md"
    if report.exists():
        shutil.copyfile(report, dashboard_dir / "REPORT.md")
    failure_check = result.get("failure_check")
    if failure_check is not None:
        (dashboard_dir / "verification.json").write_text(
            json.dumps(failure_check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = "".join(
        "<tr><td>" + html.escape(entry["name"]) + "</td><td>" + str(entry["bytes"])
        + " B</td><td><code>" + entry["sha256"][:16] + "…</code></td></tr>"
        for entry in result["data"]["sources"]
    )
    receipt = result["data"]
    page = """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Turnin 한글 PDF · 로컬 시연</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,sans-serif;color:#172522;background:#edf3f0}
*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:40px 24px}
.eyebrow{font-size:12px;font-weight:750;letter-spacing:.16em;color:#39725a}h1{font-size:34px;line-height:1.3;margin:12px 0}
.intro{color:#52645e;line-height:1.8;max-width:720px}.status{display:inline-block;background:#d8ecdf;color:#20563a;padding:8px 13px;border-radius:20px;font-size:13px;font-weight:700}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:28px 0}.card,.panel{background:white;border:1px solid #dbe5df;border-radius:12px;padding:20px}.card small{color:#63776c}.card strong{display:block;margin-top:10px;overflow-wrap:anywhere}
.panel{margin-top:18px}h2{font-size:18px;margin:0 0 17px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:13px 8px;border-bottom:1px solid #edf1ee}td:first-child{overflow-wrap:anywhere}code{font-family:ui-monospace,monospace;font-size:12px}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}a{color:#1d6447}.actions a{background:#245e46;color:#fff;text-decoration:none;padding:11px 15px;border-radius:7px;font-size:14px}.actions a.secondary{background:#e4ede8;color:#244e3c}
iframe{display:block;width:100%;height:660px;border:1px solid #dbe5df;border-radius:7px;background:#f3f5f3}.note{color:#617168;font-size:13px;line-height:1.75}footer{margin-top:24px;font-size:12px;color:#6a7970}
@media(max-width:700px){.cards{grid-template-columns:1fr}h1{font-size:27px}main{padding:25px 16px}td code{font-size:10px}iframe{height:490px}}
</style><main><div class="eyebrow">TURNIN / LOCAL DEMONSTRATION</div>
<h1>한글이 읽히는 과제 제출 PDF</h1>
<p class="intro">한글 과제명과 주석을 담은 소스를 PDF로 변환하고, 제출본과 해시 영수증을 로컬 폴더에 보관한 결과입니다. 학교 서버에 제출되는 페이지가 아닙니다. 아래 PDF는 개선안으로 새로 생성한 결과이며, 기존 시스템의 장애 증거는 리포트에서 설명합니다.</p>
<span class="status">● 로컬 모의 제출 완료</span>
<div class="cards"><div class="card"><small>과목 / 과제</small><strong>__COURSE__</strong></div>
<div class="card"><small>가상 제출자</small><strong>__SUBMITTER__</strong></div>
<div class="card"><small>제출된 소스</small><strong>__COUNT__개 · PDF 생성 완료</strong></div></div>
<div class="actions"><a href="hw.pdf" target="_blank">PDF 크게 보기 ↗</a><a class="secondary" href="receipt.json" target="_blank">해시 영수증 보기</a><a class="secondary" href="REPORT.md">진단 리포트 보기</a></div>
<section class="panel"><h2>제출 파일</h2><table><thead><tr><th>파일명</th><th>크기</th><th>SHA-256 앞 16자리</th></tr></thead><tbody>__ROWS__</tbody></table>
<p class="note">각 제출은 새 버전 폴더로 보관됩니다. PDF 생성 또는 복사에 실패하면 이전 성공 제출을 가리키는 current.json은 유지됩니다.</p></section>
__FAILURE_CHECK__
<section class="panel"><h2>생성된 PDF</h2><iframe src="hw.pdf" title="한글 PDF 미리보기"></iframe><p class="note">미리보기가 지원되지 않으면 위의 ‘PDF 크게 보기’를 사용하세요.</p></section>
<footer>로컬 시연 · __CREATED__ · revision __REVISION__</footer></main></html>"""
    replacements = {"__COURSE__": html.escape(receipt["course"]),
                    "__SUBMITTER__": html.escape(receipt["submitter"]),
                    "__COUNT__": str(len(receipt["sources"])), "__ROWS__": rows,
                    "__CREATED__": html.escape(receipt["created_at"]),
                    "__REVISION__": html.escape(receipt["revision"]),
                    "__FAILURE_CHECK__": ""}
    if failure_check is not None:
        replacements["__FAILURE_CHECK__"] = (
            '<section class="panel"><h2>실패 시 보존 확인 · 통과</h2>'
            '<p class="note">의도적으로 잘못된 UTF-8 소스를 제출했고 PDF 생성이 거부되었습니다. '
            '실패 후 current.json과 이전 성공 PDF의 바이트가 그대로 보존된 것을 확인했습니다. '
            '<a href="verification.json">검증 기록 보기</a></p></section>')
    for token, value in replacements.items():
        page = page.replace(token, value)
    index = dashboard_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


class ReadOnlyHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        translated = Path(super().translate_path(path))
        root = Path(self.directory).resolve()
        try:
            translated.resolve().relative_to(root)
        except ValueError:
            return str(root / ".not-found-outside-root")
        return str(translated)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="한글 PDF 생성 및 로컬 모의 과제 제출")
    commands = cli.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="제출 없이 PDF만 생성")
    render.add_argument("source_dir", type=Path)
    render.add_argument("--pdf", type=Path, default=Path("output/hw.pdf"))
    render.add_argument("--course", default=DEFAULT_COURSE)
    render.add_argument("--submitter", default="demo-student")
    submission = commands.add_parser("submit", help="로컬 버전 폴더에 모의 제출")
    submission.add_argument("source_dir", type=Path)
    submission.add_argument("--output", type=Path, default=Path("output"))
    submission.add_argument("--course", default=DEFAULT_COURSE)
    submission.add_argument("--submitter", default="demo-student")
    demo = commands.add_parser("demo", help="한글 예제로 PDF, 영수증, 시연 페이지 생성")
    demo.add_argument("--output", type=Path, default=Path("output"))
    serve = commands.add_parser("serve", help="생성한 시연 페이지를 localhost에서 보기")
    serve.add_argument("--output", type=Path, default=Path("output"))
    serve.add_argument("--port", type=int, default=8765)
    return cli


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "render":
            from .pdf import render_pdf
            output = render_pdf(collect_sources(args.source_dir), args.pdf, args.course, args.submitter)
            print(f"PDF 생성: {Path(output).absolute()}")
        elif args.command == "submit":
            result = submit(args.source_dir, args.output, args.course, args.submitter)
            print("로컬 모의 제출 완료 (학교 서버 제출 아님)")
            print(f"PDF: {result['pdf']}\n영수증: {result['receipt']}\n현재 제출: {result['current']}")
        elif args.command == "demo":
            result = submit(PROJECT / "examples", args.output, DEFAULT_COURSE, "demo-student")
            previous_pointer = Path(result["current"]).read_bytes()
            previous_pdf = Path(result["pdf"]).read_bytes()
            with tempfile.TemporaryDirectory(prefix=".invalid-utf8-", dir=str(args.output)) as directory:
                (Path(directory) / "invalid.cpp").write_bytes(b"// invalid UTF-8: \xff\n")
                try:
                    submit(Path(directory), args.output, DEFAULT_COURSE, "demo-student")
                except SubmissionError as error:
                    if not isinstance(error.__cause__, UnicodeDecodeError):
                        raise
                    failure_message = str(error)
                else:
                    raise RuntimeError("잘못된 UTF-8 입력을 거부하지 않았습니다.")
            if (Path(result["current"]).read_bytes() != previous_pointer
                    or Path(result["pdf"]).read_bytes() != previous_pdf):
                raise RuntimeError("실패 검증에서 기존 제출물이 변경되었습니다.")
            result["failure_check"] = {
                "scenario": "invalid-utf8-input", "rejected": True,
                "previous_current_unchanged": True, "previous_pdf_unchanged": True,
                "preserved_revision": result["revision"], "error": failure_message,
            }
            index = create_dashboard(result, args.output)
            print("로컬 시연 생성 완료 (학교 서버 제출 아님)")
            print(f"시연 페이지: {index}\nPDF: {index.parent / 'hw.pdf'}\n영수증: {result['receipt']}")
            print(f"브라우저에서 {index.as_uri()} 를 열거나 serve 명령을 사용하세요.")
        elif args.command == "serve":
            root = args.output.absolute()
            if root.is_symlink() or not (root / "demo" / "index.html").is_file():
                raise SubmissionError("먼저 demo 명령으로 시연 페이지를 생성하세요.")
            handler = partial(ReadOnlyHandler, directory=str(root))
            with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
                print(f"http://127.0.0.1:{server.server_port}/demo/ (종료: Ctrl+C)", flush=True)
                server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(f"실패: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
