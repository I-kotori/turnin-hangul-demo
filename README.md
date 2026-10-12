# Turnin Hangul PDF

UTF-8 C/C++ 소스 파일을 한글이 포함된 PDF로 변환하는 Python 프로젝트입니다. 과목·과제 제목, 제출자, 파일명, 한글 주석과 문자열을 표시하며, 기존 코드 인쇄용 가로 2단 양식을 기준으로 출력합니다.

PDF 생성기, 기존 제출 스크립트에 연결하는 함수, 선택적인 로컬 모의 제출 도구를 제공합니다.

## 주요 기능

- 디렉터리 바로 아래의 `.c`, `.cpp`, `.h` 파일 처리
- 한글 글꼴 포함, 줄 번호, C/C++ 문법 강조, 긴 줄 자동 줄바꿈
- 가로 2단 테두리, 날짜·시각, 파일별 쪽 번호
- PDF 생성 실패 시 기존 출력 파일 보존
- 제출용 사본으로 PDF와 소스를 준비하고, 파일 교체 오류 시 이전 제출 복구

## 요구 환경

- Python 3.8 이상
- ReportLab `>=3.5.34,<5`
- Pygments `>=2.3.1,<3`
- 제출 연결 함수 `integration.py`: Linux/macOS (`fcntl.flock` 사용)

생성기는 ReportLab으로 PDF를 직접 만듭니다. 포함된 Nanum Gothic Coding TTF 글꼴을 사용하며, 실행 패키지 버전 범위는 [requirements.txt](requirements.txt)에 있습니다.

## 설치와 PDF 생성

저장소 루트에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m turnin_demo render ./examples \
  --pdf output/preview.pdf \
  --course "자료구조 과제" \
  --submitter student01
```

결과는 `output/preview.pdf`에 저장됩니다. `./examples`를 소스 디렉터리로 바꾸면 다른 파일을 처리할 수 있습니다.

입력은 UTF-8이며 UTF-8 BOM도 처리합니다. 잘못된 인코딩이나 포함 글꼴로 표시할 수 없는 문자는 오류로 알립니다. 원본 소스 파일은 수정하지 않습니다. PDF 표시에는 NFC 정규화와 탭 너비 8을 적용합니다.

머리글은 `[과목·과제 제목] 제출자 : 파일명` 형식입니다. 제목과 제출자는 명령 인자로 전달하며, 계정 조회나 과목 선택은 연결하는 프로그램에서 담당합니다.

## 로컬 시연과 모의 제출 (선택)

예제로 PDF·검증 기록·미리보기 페이지를 생성합니다.

```bash
python -m turnin_demo demo
python -m turnin_demo serve
```

브라우저에서 <http://127.0.0.1:8765/demo/>를 엽니다. 종료는 `Ctrl+C`입니다. 생성된 `output/demo/index.html`을 직접 열 수도 있습니다.

다른 소스를 로컬 버전 폴더에 보관하려면 다음을 실행합니다.

```bash
python -m turnin_demo submit ./examples \
  --output output \
  --course "자료구조 과제" \
  --submitter student01
```

`submit`은 원본 소스·PDF·SHA-256 영수증을 새 버전으로 보관하고 `current.json`을 갱신합니다. 모의 제출자 ID는 영문·숫자로 시작하고 영문·숫자·`_`·`-`를 사용합니다. `demo`와 `submit`은 지정한 로컬 폴더에 결과를 저장합니다.

## 기존 제출 프로그램에 연결

PDF 생성기와 연결 함수에 필요한 파일만 묶습니다.

```bash
python3 tools/build_minimal.py
```

`output/minimal/turnin-pdf.zip`에는 실행 모듈, 공용 글꼴, 의존성 목록, 연결 안내와 수정 사본 도구가 포함됩니다. 출력 ZIP이 이미 있으면 `--output`으로 새 경로를 지정합니다.

압축을 푼 뒤 `turnin_demo/`와 `assets/`를 형제 디렉터리로 유지합니다. 글꼴은 프로그램 공용 경로에 한 번 배치합니다. 기존 프로그램이 계산한 제목·로그인 계정·제출 경로를 연결 함수에 전달합니다.

아래 예제는 전체 개발 저장소 루트에서 실행합니다. 최소 ZIP만 사용한다면 `examples` 대신 별도로 준비한 소스 디렉터리를 지정합니다.

```python
from pathlib import Path
from turnin_demo.integration import submit_listing

source = Path("examples")
destination = Path("output/test-submissions/student01")
destination.parent.mkdir(parents=True, exist_ok=True)
pdf = submit_listing(source, destination, "자료구조 과제", "student01")
```

함수는 대상 디렉터리에 원본 소스와 `hw.pdf`를 저장하고 PDF 경로를 반환합니다. 입력 폴더의 `hw.pdf`도 미리보기로 갱신하므로 입력 폴더에 쓰기 권한이 필요합니다. 소스와 대상 디렉터리는 서로 포함하지 않는 별도 경로여야 합니다. 대상 제출함의 상위 디렉터리는 미리 준비합니다.

파일 수집은 `.c → .cpp → .h` 그룹 순서이며 그룹 안에서는 이름순입니다. 소스를 먼저 복사하고 그 사본에서 PDF를 생성합니다. 제출 교체 실패 시 이전 파일을 복구하고, 복구 오류가 나면 백업 경로를 알립니다. 기존의 보이는 일반 파일은 교체하며 숨김 파일은 유지합니다.

원본을 보존한 수정 사본·diff 생성 방법, 실제 연결 위치와 권한 확인 사항은 [MINIMAL_PATCH.md](MINIMAL_PATCH.md)에 있습니다. 최소 ZIP에는 모의 제출 CLI와 검사 파일이 포함되지 않습니다.

## 검증

전체 개발 저장소에서 실행합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

| 환경 | 확인한 결과 |
| --- | --- |
| macOS arm64 / Python 3.12.14 / ReportLab 4.4.9 / Pygments 2.20.0 | 전체 37개 검사 통과, 배포 ZIP의 별도 실행 및 PDF 화면 확인 |
| Ubuntu 20.04.6 x86_64 / Python 3.8.10 / ReportLab 3.5.34 / Pygments 2.3.1 | 전체 37개 검사 통과, 분리된 테스트 경로의 설정·계정 연결 및 PDF 화면 확인 |
| macOS arm64 / Python 3.14.7 / ReportLab 4.5.1 / Pygments 2.21.0 | 새 가상환경에서 README 절차·전체 37개 검사·HTTP 5개 경로·최소 ZIP의 별도 실행 통과 |

검사는 한글 추출·글꼴 포함·양식·여러 파일과 페이지·실패 보존·복구·수정 호출 간 잠금·패치·배포를 포함합니다. Ubuntu의 연결 검증에는 취소·마감·정상 재제출·잘못된 UTF-8 입력 거부가 포함됩니다. 운영 제출 경로의 권한과 읽기 흐름은 별도 확인이 필요합니다.

최근 로컬 실행 결과는 [TEST_REPORT.md](TEST_REPORT.md)에 정리했습니다.

## 적용 범위와 한계

- 입력 소스의 심볼릭 링크와 일반 파일이 아닌 항목은 거부합니다.
- 제목이 길면 머리글을 축소하며, 읽을 수 있는 최소 크기를 넘으면 오류로 처리합니다.
- 글꼴과 문법 강조 방식 차이로 기존 출력과 줄바꿈·색상·쪽 수가 달라질 수 있습니다.
- 잠금은 같은 연결 함수를 사용하는 제출끼리 적용됩니다. 다른 프로그램의 읽기는 교체 중 일부 파일을 볼 수 있습니다.
- 파일 교체는 강제 종료·전원 장애까지 복구하는 트랜잭션이 아닙니다.
- 작업 폴더의 미리보기 PDF 생성과 대상 폴더의 제출 성공은 별개입니다.

설계 근거와 변환 방식 비교는 [REPORT.md](REPORT.md)에서 확인하실 수 있습니다. 선택적인 비교 도구는 `tools/reproduce_legacy.py`와 `tools/probe_noto_ps.py`입니다. 각 도구는 별도의 외부 프로그램과 시험 환경을 요구합니다.

## 글꼴과 라이선스

포함된 Nanum Gothic Coding Regular·Bold는 Google Fonts 배포본입니다. 글꼴에는 SIL Open Font License가 적용됩니다. 출처는 [SOURCE.md](assets/fonts/SOURCE.md), 이용 조건은 [OFL.txt](assets/fonts/OFL.txt)에 있습니다.

코드 라이선스는 아직 명시되지 않았습니다.
