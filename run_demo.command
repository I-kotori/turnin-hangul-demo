#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m turnin_demo demo
printf '\n브라우저에서 http://127.0.0.1:8765/demo/ 를 열어주세요. 종료: Ctrl+C\n'
.venv/bin/python -m turnin_demo serve
