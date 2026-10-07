#!/usr/bin/env python3
"""Small local font experiment; this does not submit files or replace turnin."""
import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

# The same text and layout are used for both output formats.
LINES = [
    "[한글 PDF 검증] test-student : 한글 예제.cpp",
    "1: // 한글 주석: 배열에서 가장 작은 값을 찾습니다.",
    "2: #include <stdio.h>",
    '3: printf("안녕하세요, 동국대학교!\\n");',
    "4: // 혼합 문자: 가나다 ABC 123 [] () {}",
    "5: // 마지막 줄: 테스트 끝",
]
FONT = "Noto Sans Mono CJK KR"


def run(command, env):
    result = subprocess.run(command, env=env, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/noto-probe"))
    parser.add_argument("--font-dir", type=Path, help="Local copies; omit to use system fonts")
    parser.add_argument("--ps2pdf", default="ps2pdf")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    ps2pdf = shutil.which(args.ps2pdf)
    if not ps2pdf:
        parser.error("ps2pdf was not found: " + args.ps2pdf)
    env = dict(os.environ, PANGOCAIRO_BACKEND="fc")
    env["PATH"] = str(Path(ps2pdf).parent) + os.pathsep + env.get("PATH", os.defpath)
    gs_version = run(["gs", "--version"], env)
    if args.font_dir:
        cache = output / "font-cache"
        cache.mkdir(exist_ok=True)
        config = output / "fonts.conf"
        config.write_text('<fontconfig><dir>' + escape(str(args.font_dir.resolve()))
                          + '</dir><cachedir>' + escape(str(cache))
                          + '</cachedir></fontconfig>', encoding="utf-8")
        env["FONTCONFIG_FILE"] = str(config)
    matches = {}
    for family in (FONT, "Noto Sans CJK KR"):
        match = run(["fc-match", "-f", "%{file}|%{index}|%{family}", family], env)
        if family not in match.split("|")[-1].split(","):
            raise RuntimeError("Requested Noto font was not found: " + match)
        matches[family] = match
    source = output / "input.markup"
    header = '<span font_desc="Noto Sans CJK KR 14">' + escape(LINES[0]) + '</span>'
    source.write_text(header + "\n\n" + "\n".join(escape(line) for line in LINES[1:]),
                      encoding="utf-8")
    common = ["pango-view", "--no-display", "--backend=cairo", "--markup",
              "--font=" + FONT + " 12", "--language=ko", "--dpi=72",
              "--margin=24", "--width=794", "--height=547", "--wrap=word-char"]
    for filename in ("noto-direct.pdf", "noto.ps"):
        run(common + ["--output=" + str(output / filename), str(source)], env)
    run([ps2pdf, str(output / "noto.ps"), str(output / "noto-via-ps.pdf")], env)
    metadata = {"font_matches": matches, "ghostscript": gs_version, "pango": run(["pango-view", "--version"], env),
                "expected_lines": LINES, "ps2pdf": ps2pdf}
    (output / "probe.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)
                                      + "\n", encoding="utf-8")
    print("Local experiment complete:", output)


if __name__ == "__main__":
    main()
