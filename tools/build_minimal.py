#!/usr/bin/env python3
"""Package the PDF renderer and small connection; no school code or mock CLI."""
import argparse
from pathlib import Path
import zipfile

FILES = (
    "turnin_demo/__init__.py", "turnin_demo/pdf.py", "turnin_demo/integration.py",
    "assets/fonts/NanumGothicCoding-Regular.ttf", "assets/fonts/NanumGothicCoding-Bold.ttf",
    "assets/fonts/OFL.txt", "assets/fonts/SOURCE.md", "requirements.txt",
    "MINIMAL_PATCH.md", "tools/patch_turnin.py",
)


def build(output):
    root = Path(__file__).resolve().parent.parent
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(root / name, name)
    return output.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/minimal/turnin-pdf.zip"))
    args = parser.parse_args()
    try:
        result = build(args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + chr(10))
    print("최소 배포 묶음:", result)


if __name__ == "__main__":
    main()
