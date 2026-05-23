# 프로젝트: <프로젝트명>

## 목표
- <이 프로젝트가 해결하는 문제를 한 문장으로 작성>
- MVP는 `docs/PRD.md`의 범위만 구현한다.
- 계획이 바뀌면 구현 전에 `docs/`와 phase 문서를 먼저 갱신한다.

## 기술 스택
- Runtime/Framework: <Spring Boot | Python | Node | 기타>
- Language: <Java/Kotlin | Python | TypeScript/JavaScript | 기타>
- Data/Storage: <DB, cache, file, external API>
- Test: <JUnit/pytest/Vitest/Jest 등>
- Build/Package: <Gradle/Maven/uv/npm/pnpm/yarn 등>

## CRITICAL 규칙
- CRITICAL: Plan Mode에서 확정된 MVP 범위를 벗어난 기능을 임의로 추가하지 않는다.
- CRITICAL: 새 동작을 구현하기 전에 관련 테스트 또는 검증 방법을 먼저 정한다.
- CRITICAL: 외부 API, DB, 인증, 파일 시스템 경계는 `docs/ARCHITECTURE.md`의 데이터 흐름을 따른다.
- CRITICAL: ADR에 기록된 기술 결정을 임의로 뒤집지 않는다.
- CRITICAL: 민감정보(API key, token, password, private key)는 코드와 문서에 커밋하지 않는다.

## 디렉터리 규칙
- 제품 요구사항은 `docs/PRD.md`에 둔다.
- 아키텍처와 데이터 흐름은 `docs/ARCHITECTURE.md`에 둔다.
- 기술 결정은 `docs/adr/0001-title.md` 형식으로 둔다.
- `docs/ADR.md`는 ADR 인덱스로 유지한다.
- 실행 명령은 `docs/COMMANDS.md`를 단일 출처로 삼는다.
- phase 작업은 `phases/{phase}/README.md`, `phases/{phase}/index.json`, `phases/{phase}/stepN.md`에 둔다.
- phase 실패 기록은 `issues/{phase}/issue-N.md`에 둔다.

## 테스트와 검증
- 구현 전 `docs/COMMANDS.md`에서 해당 프로젝트의 lint/test/build 명령을 확인한다.
- 변경 후 가능한 최소 검증부터 실행하고, phase 완료 전 test/build를 실행한다.
- 테스트를 실행할 수 없으면 이유와 대체 검증을 phase summary 또는 issue에 남긴다.
- 실패한 검증은 숨기지 말고 재현 명령과 핵심 에러를 기록한다.

## Codex 작업 방식
- 먼저 관련 `docs/`, phase 파일, 주변 코드를 읽고 작업한다.
- 코드 변경은 현재 step 범위에 맞춘다.
- 사용자의 기존 변경은 되돌리지 않는다.
- 큰 작업은 Harness skill로 phase/step 단위로 나눈다.
- step PR 자동 루프는 `scripts/autopilot.py <phase> --base main --max-review-fixes 2`를 사용한다.
- step 완료 시 `phases/{phase}/index.json`의 status와 summary를 갱신한다.
- step PR 리뷰가 실패하면 같은 PR 브랜치에서 수정하고 `issues/{phase}/issue-N.md`에 기록한다.
- 자체 리뷰는 review skill 기준으로 수행한다.

## 커밋/PR 규칙
- 커밋 메시지는 Conventional Commits 형식을 사용한다.
- 하나의 커밋에는 하나의 의도만 담는다.
- phase 구현 커밋과 phase 메타데이터 커밋은 분리할 수 있다.
- step PR은 Draft로 만들고 로컬 검증과 자체 리뷰가 통과한 경우에만 ready 전환 후 squash merge한다.
- PR 본문에는 작업 내용, 변경 이유, 테스트 및 확인 결과를 적는다.

## 명령어
- 개발 서버: `<docs/COMMANDS.md의 dev 명령>`
- 린트: `<docs/COMMANDS.md의 lint 명령>`
- 테스트: `<docs/COMMANDS.md의 test 명령>`
- 빌드: `<docs/COMMANDS.md의 build 명령>`
- 수동 검증: `python3 scripts/checks.py --stage manual`
- Step PR 루프: `python3 scripts/autopilot.py <phase-name> --base main --max-review-fixes 2`
- 환경 점검: `python3 scripts/doctor.py`
