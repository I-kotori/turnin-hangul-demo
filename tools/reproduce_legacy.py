#!/usr/bin/env python3
"""Reproduce the original conversion pipeline with synthetic local fixtures.

Requires separately installed enscript and ps2pdf; does not install tools or
submit files. The intermediate PostScript and tool output are kept for review.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/legacy"))
    args = parser.parse_args()
    for tool in ("enscript", "ps2pdf"):
        if not shutil.which(tool):
            parser.error(f"{tool} is not installed; this optional comparison needs both tools")
    source = args.source.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=True)
    # Keep each run separate so a failed run cannot masquerade as an older PDF.
    run = Path(tempfile.mkdtemp(prefix="run-", dir=args.output))
    commands = [
        ["enscript", "-2rj", "--header=[자료구조 모의과제] demo-student : $n|%W %C|$%/$=",
         "--word-wrap", "--line-numbers", "--highlight=cpp", "--color=1", "-o", str(run / "hw.ps"), str(source)],
        ["ps2pdf", str(run / "hw.ps"), str(run / "hw.pdf")],
    ]
    with (run / "conversion.log").open("w", encoding="utf-8") as log:
        for command in commands:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            log.write(result.stdout.decode("utf-8", errors="replace"))
            log.flush()
            if result.returncode:
                raise SystemExit(f"{command[0]} failed ({result.returncode}); see {run}")
    print(run.resolve())


if __name__ == "__main__":
    main()
