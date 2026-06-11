# 범위 변경 체크리스트

## 목적

이 문서는 MVP를 새로 정의하거나 현재 범위(baseline)를 바꿀 때 갱신 누락을
줄이기 위한 운영 체크리스트입니다.

이 문서는 제품 계약의 source of truth가 아닙니다. 제품 범위는 `docs/PRD.md`,
구조와 경계는 `docs/ARCHITECTURE.md`, 기술 결정은 `docs/adr/`, 실행 명령은
`docs/COMMANDS.md`를 우선합니다. 이 문서는 "그 문서들 중 어디를 함께 고쳐야
하는가"만 답합니다.

## 사용 시점

- 새 MVP 또는 새 phase를 기획할 때
- 포함/제외 범위, 외부 연동, 저장소, 인증 방식이 바뀔 때
- 폐기된 기능이나 계약을 문서에서 제거할 때
- `docs-checks.json`, `scope-rules.json`이 현재 범위와 맞는지 확인할 때

## 기본 원칙

- 완료된 phase 문서(`phases/`, `issues/`)와 `archive/`는 과거 실행 기록입니다.
  현재 구현 기준은 루트 `README.md`와 `docs/` 아래 현재 문서입니다.
- MVP를 전환할 때는 현재 baseline 문구를 바꾸기 전에 직전 MVP의 요약을
  `archive/{직전-mvp}/`에 남깁니다. 형식은 `archive/README.md`를 따릅니다.
- 오래된 ADR을 새 결정처럼 고치지 않습니다. 새 결정은 새 ADR 파일을 만들고
  `docs/ADR.md` 인덱스에 연결합니다.
- 범위별 정규식 검증은 `scripts/checks.py`에 넣지 않습니다. 해당 phase의
  `phases/{phase}/docs-checks.json`에 둡니다.
- 범위 금지 키워드는 하네스 스크립트에 하드코딩하지 않습니다. 전역은
  `.codex/scope-rules.json`, phase별 확장/허용은
  `phases/{phase}/scope-rules.json`에 둡니다.
- `docs-checks.json`은 자동으로 잡을 수 있는 핵심 회귀 신호만 담습니다.
  에이전트가 읽고 판단해야 하는 정성 규칙은 `AGENTS.md`와 현재 문서에 둡니다.

## 항상 확인할 파일

| 파일 | 확인할 내용 |
| --- | --- |
| `README.md` | 프로젝트 소개, 기술 스택, 핵심 흐름, 현재 MVP 포인터. 세부 계약 원문은 복사하지 않는다 |
| `docs/PRD.md` | MVP 정의, 목표, 포함/제외 범위, 우선순위, 완료 기준, 현재 baseline |
| `docs/ARCHITECTURE.md` | 모듈 구조, 데이터 흐름, 외부 의존성, 경계, 테스트 전략 |
| `docs/ADR.md`, `docs/adr/{NNNN}-*.md` | 새 결정 ADR 추가, 인덱스 연결, 이전 ADR과의 관계 |
| `docs/COMMANDS.md` | 활성 명령, 새 검증 명령, 폐기된 명령 제거 |
| `AGENTS.md` | 목표/기술 스택 문구, CRITICAL 규칙, 디렉터리 규칙이 새 범위와 충돌하지 않는지 |

API 명세, DB 스키마, 화면 설계, 공유/배포 가이드 같은 프로젝트 전용 문서를
`docs/`에 추가했다면 이 표에 직접 행을 추가해 함께 관리합니다.

## 운영 설정

| 파일 | 확인할 내용 |
| --- | --- |
| `.codex/project-profile.json` | `commands` override, `sourceRoots`/`testRoots`, `guardrailDocs`가 새 구조와 맞는지 |
| `.codex/scope-rules.json` | 새로 금지할 범위 키워드 추가, 이번 범위에 포함되어 더는 금지가 아닌 규칙 제거 |
| `phases/{phase}/scope-rules.json` | phase 한정 금지(`extraForbidden`)와 step별 허용(`allowedScopeMessages`) |

## Harness phase 파일

새 범위를 phase로 실행할 때는 아래를 함께 만듭니다. 형식 예시는
`phases/0-example/`을 참고합니다.

| 파일 | 확인할 내용 |
| --- | --- |
| `phases/index.json` | 새 phase dir 추가와 상태 |
| `phases/{phase}/README.md` | phase 목표, 작업/제외 범위, step 목록, 완료 기준, 검증 명령 |
| `phases/{phase}/index.json` | step 순서, 이름, 상태 |
| `phases/{phase}/step{N}.md` | 읽어야 할 파일, 작업, 인수 기준, 검증 절차, 금지사항 |
| `phases/{phase}/docs-checks.json` | final stage에서 검증할 `required`/`finalRequired`/`forbidden` 마커 |

`docs-checks.json`의 `forbidden`에는 이번 변경으로 폐기된 계약(엔드포인트,
파라미터, 오래된 데모 흐름)이 문서에 되살아나는 회귀를 잡는 규칙을 넣습니다.

## 스크립트 확인 기준

범위가 바뀌었다는 이유만으로 `scripts/*.py`를 수정하지 않습니다.

| 파일 | 수정하는 경우 |
| --- | --- |
| `scripts/checks.py` | docs-check 엔진, stage 처리, 명령 감지 자체가 바뀔 때 |
| `scripts/execute.py` | branch/commit/final 검증 같은 phase 실행 workflow가 바뀔 때 |
| `scripts/autopilot.py` | PR 생성, 자체 리뷰, issue 기록, merge loop workflow가 바뀔 때 |
| `scripts/test_*.py` | 위 스크립트 동작을 바꾼 경우 |

범위별 문서 검증 규칙은 `phases/{phase}/docs-checks.json`, 범위 금지 키워드는
`scope-rules.json`에 둡니다.

## 검색 체크

문서 전환 후에는 오래된 범위 표현과 폐기된 계약을 검색합니다. 검색어는
이번 변경에서 폐기한 기능/용어로 바꿉니다.

```bash
rg -n "<폐기한 기능명>|<오래된 phase명>|<폐기한 API 경로>" README.md AGENTS.md docs phases
```

완료된 phase, 오래된 ADR, issue 기록처럼 과거 맥락이 명확한 파일의 과거 표현은
남길 수 있지만, 현재 baseline 문서와 에이전트 규칙 안의 충돌 표현은 제거하거나
현재 기준으로 바꿉니다.

## 최종 검증

문서만 바꿨더라도 최소한 아래를 확인합니다.

```bash
git diff --check
python scripts/checks.py --docs-check
python scripts/doctor.py --instance
```

새 phase를 막 설계한 상태라면 해당 phase rule 파일을 직접 지정해 확인합니다.

```bash
python scripts/checks.py --docs-check-config phases/{phase}/docs-checks.json --docs-check
```

코드나 실행 흐름까지 바뀌었다면 `docs/COMMANDS.md`의 test/build와
`python scripts/checks.py --stage final`을 함께 실행합니다.
