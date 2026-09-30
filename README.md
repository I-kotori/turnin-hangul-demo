# Turnin 한글 PDF 로컬 시연

학교 과제 제출 스크립트에서 확인한 `소스 → enscript → PostScript → ps2pdf` 흐름의 한글 깨짐을 개선하기 위한 독립적인 검증 프로젝트입니다. UTF-8 소스로부터 한글 글꼴이 포함된 PDF를 만들고, 가상 제출 디렉터리에 원본 소스와 검증 영수증을 보관합니다.

이 프로젝트의 `submit`은 로컬 파일 시뮬레이션입니다. 학교 계정·설정·제출 경로를 사용하지 않습니다. 공개 라이선스가 확인되지 않은 학교 스크립트 원문도 포함하지 않습니다.

## 시작하기

Python 3.8 이상을 대상으로 작성했습니다. 터미널에서 이 프로젝트 디렉터리로 이동한 뒤 실행합니다.

macOS에서는 `run_demo.command`를 실행해도 됩니다. 첫 실행에는 가상환경과 의존성을 준비하고, 이후에는 데모 생성과 localhost 서버 실행을 수행합니다. 이미 8765 포트에서 시연 중이면 기존 페이지를 이용하세요.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m turnin_demo demo
python -m turnin_demo serve
```

브라우저에서 <http://127.0.0.1:8765/demo/>를 엽니다. 종료는 `Ctrl+C`입니다. 서버를 실행하지 않고 `output/demo/index.html`을 브라우저로 열어도 됩니다. 브라우저의 로컬 PDF 미리보기 정책에 따라 “PDF 크게 보기”를 사용하세요.

`demo`는 공개된 학번이나 실제 제출물이 없는 예제 2개로 다음 결과를 생성합니다.

- `output/demo/index.html`: 제출 결과와 PDF 미리보기
- `output/demo/hw.pdf`: 한글 과제명·주석·파일명, 줄 번호, 문법 강조, 2단 배치
- `output/demo/receipt.json`: 원본 파일과 PDF의 SHA-256 해시
- `output/demo/verification.json`: 잘못된 UTF-8 입력 거부와 이전 성공 제출 보존 검증
- `output/demo/REPORT.md`: 진단 리포트 사본
- `output/submissions/...`: 제출 버전과 현재 제출을 가리키는 `current.json`

프로젝트에 포함된 NanumGothicCoding 글꼴을 PDF에 포함하므로, 이 시연은 서버에 설치된 Noto 글꼴이나 별도 브라우저 엔진에 의존하지 않습니다. 글꼴의 라이선스와 출처는 글꼴 디렉터리를 참고하세요.

## 내 테스트 소스로 실행하기

지정한 디렉터리 바로 아래의 `.c`, `.cpp`, `.h` 파일을 읽습니다. 기본 입력 인코딩은 UTF-8입니다. UTF-8로 해석할 수 없는 입력은 오류로 처리하며, 임의로 글자를 치환하지 않습니다.

PDF만 만들기:

```bash
python -m turnin_demo render ./examples --pdf output/my-preview.pdf --course "자료구조 과제" --submitter demo-student
```

로컬 모의 제출하기:

```bash
python -m turnin_demo submit ./examples --output output --course "자료구조 과제" --submitter demo-student
```

제출자 ID는 영문·숫자로 시작하고 영문·숫자·`_`·`-`만 포함해야 합니다. 한글 과목명, 한글·공백이 포함된 소스 파일명은 지원합니다. 소스 심볼릭 링크는 거부합니다.

각 제출은 원본 소스 바이트를 새 임시 폴더로 복사한 뒤 그 사본에서 PDF를 생성합니다. 생성과 영수증 저장이 모두 끝나면 새 버전 폴더를 확정하고 `current.json`을 원자적으로 교체합니다. 실패한 시도는 이전 성공 제출을 지우지 않습니다. 성공한 과거 버전도 자동 삭제하지 않습니다. 동시 제출 시 마지막 포인터 교체가 현재 버전이 되며, 각각의 성공한 버전은 남습니다.

`demo`는 정상 제출 직후 잘못된 UTF-8 예제를 한 번 제출해 오류를 발생시킵니다. 그 뒤 `current.json`과 기존 PDF의 바이트가 같음을 확인하고 이 실제 검증 결과를 페이지에 표시합니다. 과목 설정 파일, 제출 마감 시각, 학교 계정 인증 및 운영 디렉터리 권한은 이 로컬 시연의 구현 범위에 포함하지 않습니다.

## 교수님 또는 관리자에게 전달하기

먼저 [REPORT.md](REPORT.md)의 근거와 한계를 읽고, 예제 소스 및 생성한 `hw.pdf`를 함께 검토하면 됩니다. 이 프로젝트는 기존 시스템과 별개인 시연용 구현이며, 운영 적용에는 실제 서버 환경에서 글꼴·Python 패키지·출력 레이아웃과 실패 동작을 확인하는 작업이 필요합니다.

기여 자료에는 진단 리포트, 재현용 예제, PDF 생성 모듈, 실패 시 이전 제출을 보존하는 모의 구현, 실행 방법 및 테스트 결과를 포함할 수 있습니다. 원본 저장소와 라이선스가 확인되면 관리자의 방식에 맞춰 패치 또는 PR로 전달합니다. 실제 학생 제출물·학번·학교 설정 파일은 Git에 넣지 않습니다.

## 검증

프로젝트에 포함된 테스트는 다음 명령으로 실행합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

PDF 화면에서는 과제명·파일명·주석이 정상적으로 보이는지, 두 열과 줄바꿈이 겹치지 않는지 확인합니다. PDF 뷰어에서 한글을 검색·복사해 보는 것도 확인 항목입니다. 해시 영수증은 제출 원본의 바이트 보존을 확인하는 용도이며, 디지털 서명은 아닙니다.

검증 환경: macOS, Python 3.12, ReportLab 4.4.9, Pygments 2.19.2. 자동 검사 14개 통과 및 Poppler로 렌더링한 2쪽의 한글·배치 확인을 완료했습니다. 학교 서버의 Python 버전과 권한에서는 아직 실행하지 않았습니다.

## 기존 변환 경로 재현 (선택)

`enscript`와 `ps2pdf`가 설치된 별도 환경에서는 가짜 샘플로 기존 변환 단계만 실행할 수 있습니다.

```bash
python tools/reproduce_legacy.py "examples/한글 예제.cpp"
```

`output/legacy/run-.../` 아래에 `hw.ps`, `hw.pdf`, 변환 로그를 보존합니다. 이 도구는 제출 디렉터리를 사용하지 않습니다. 이 로컬 Mac에는 두 프로그램이 없어 해당 비교 실행은 미검증이며, 이미 관찰한 오류 증거는 `REPORT.md`에 따로 기록했습니다.
