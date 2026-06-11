# Codex Project Ops Template

Codex 기반 개인 프로젝트 운영 템플릿입니다. 이 레포는 Spring Boot, Python,
Node 앱 코드를 직접 생성하지 않습니다. 대신 프로젝트 시작 폴더에 Codex 운영
레이어를 설치하고, Plan Mode로 확정한 MVP 범위와 기술 스택을 문서화한 뒤,
Harness skill로 phase 단위 구현, 테스트, 리뷰를 반복하는 흐름을 제공합니다.

## 포함된 구성

- `AGENTS.md`: Codex가 따르는 100줄 안팎의 프로젝트 운영 규칙
- `docs/PRD.md`: MVP 범위와 완료 기준
- `docs/ARCHITECTURE.md`: 구조, 데이터 흐름, 경계
- `docs/ADR.md`: 기술 결정 기록과 ADR 분리 규칙
- `docs/COMMANDS.md`: dev, lint, test, build, review 명령의 기본 문서 기준
- `docs/SCOPE_CHANGE_CHECKLIST.md`: MVP/phase 범위 변경 시 함께 갱신할 파일 체크리스트
- `.codex/config.toml`: Codex hook feature 활성화 설정
- `.codex/hooks.json`: Codex tool hook 설정
- `.codex/hooks/tdd-guard.py`: Git/Codex hook cross-platform Python launcher
- `.codex/hooks/tdd-guard.sh`: macOS/Linux 호환 hook wrapper
- `.codex/project-profile.json`: guard 모드와 명령 override 설정
- `.codex/scope-rules.json`: 프로젝트 전역 scope 금지 규칙 overlay
- `.githooks/pre-commit`: 커밋 전 검증 hook
- `.gitattributes`: hook wrapper line ending 정책
- `.github/workflows/template-ci.yml`: macOS/Linux/Windows 템플릿 검증 CI
- `.agents/skills/harness`: phase/step 설계와 실행 워크플로우
- `.agents/skills/review`: 문서와 규칙 기준 자체 리뷰 워크플로우
- `scripts/execute.py`: phase step 실행기
- `scripts/autopilot.py`: step별 PR 생성, 자체 리뷰, 이슈 기록, 자동 병합 루프
- `scripts/checks.py`: 프로젝트 명령 감지 및 실행
- `scripts/codex_common.py`: Codex 호출, effort, timeout, 인수 기준 파싱 공통 유틸
- `scripts/doctor.py`: 템플릿 원본과 복사된 프로젝트 적용 상태 점검
- `scripts/guard.py`: 위험 명령, TDD, pre-commit/stop 정책
- `phases/README.md`, `phases/index.json`: Harness phase 구조와 최상위 인덱스
- `phases/0-example/`: phase 파일 형식이 채워진 참고용 예시 (`doctor.py --template`이 스키마 검증)
- `issues/README.md`: phase 실패 기록 형식
- `archive/README.md`: MVP 전환 시 직전 MVP 요약을 남기는 archive 컨벤션

## 30분 셋업 순서

새 프로젝트에 이 템플릿을 가져온 뒤 아래 순서대로 placeholder를 실제 값으로
바꿉니다. 앞 단계가 비어 있으면 Codex가 MVP 범위, 검증 명령, phase 경계를
잘못 판단할 수 있으므로 순서를 건너뛰지 않습니다.

먼저 Git hook 경로를 설정합니다. Windows에서는 Python 설치 시 `python.exe`를
PATH에 추가해야 Codex hook이 PowerShell에서 바로 실행됩니다.

macOS/Linux:
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .codex/hooks/tdd-guard.sh .codex/hooks/tdd-guard.py
```

Windows PowerShell:
```powershell
git config core.hooksPath .githooks
```

여기서는 hook 경로만 설정합니다. `doctor`는 기술 스택과 검증 명령까지 채운 뒤
8번에서 실행합니다. 그다음 파일을 아래 순서대로 채웁니다.

### Plan Mode에 복붙할 프롬프트

템플릿을 복사한 직후에는 Codex를 Plan Mode로 전환하고, 아래 프롬프트를
위에서부터 순서대로 사용합니다. 목적은 Codex가 임의로 구현을 시작하기 전에
MVP 범위, 기술 스택, 검증 명령, phase 경계를 먼저 문서로 확정하게 만드는
것입니다.

한 번에 정리하려면 아래 프롬프트를 사용합니다.

```text
이 프로젝트의 MVP를 확정하기 위해 나에게 필요한 질문을 먼저 해라.
답변을 바탕으로 docs/PRD.md, docs/ARCHITECTURE.md, docs/COMMANDS.md,
docs/ADR.md, AGENTS.md, .codex/project-profile.json의 placeholder를 실제 값으로
채울 계획을 작성해라. 아직 코드를 구현하지 마라.

질문은 MVP 목표, 사용자, must-have 범위, 제외 범위, 기술 스택, 저장소/외부 API,
인증/권한, 테스트/빌드 명령, 배포 또는 실행 방식, 리스크와 ADR 후보를 빠짐없이
확인해야 한다. 모호한 답변은 임의로 확정하지 말고 후속 질문으로 좁혀라.
```

정보가 부족한 프로젝트는 아래 프롬프트를 단계별로 던집니다.

1. 제품 범위 확정

```text
이 프로젝트의 PRD를 채우기 위해 나에게 질문해라.
질문은 목표, primary/secondary 사용자, MVP must-have, 완료 기준, 제외 범위,
구현 전 결정이 필요한 리스크를 확정하는 데 집중해라.
답변을 받은 뒤 docs/PRD.md에 들어갈 초안을 제시하고, MVP와 제외 범위를
Codex가 혼동하지 않게 명확한 문장으로 정리해라.
```

2. 아키텍처 확정

```text
확정된 PRD를 기준으로 docs/ARCHITECTURE.md를 채우기 위해 나에게 질문해라.
런타임/프레임워크, 언어, 저장소, 외부 의존성, 디렉터리 구조, 모듈 경계,
데이터 흐름, 오류 처리, 테스트 전략을 확정해야 한다.
답변을 바탕으로 구현 경계와 데이터 흐름이 드러나는 아키텍처 초안을 작성해라.
```

3. 명령과 profile 확정

```text
이 프로젝트의 docs/COMMANDS.md와 .codex/project-profile.json을 채우기 위해
필요한 질문을 해라. dev, lint, test, build 명령과 sourceRoots, testRoots,
guardMode, 필요한 stageChecks/guardrailDocs를 확정해야 한다.
확정된 기술 스택 기준으로 Windows PowerShell에서 실행 가능한 명령을 우선
작성하고, test와 build가 비어 있으면 안 되는 이유를 함께 표시해라.
```

4. ADR 후보 정리

```text
확정된 docs/PRD.md, docs/ARCHITECTURE.md, docs/COMMANDS.md를 기준으로
ADR에 기록해야 할 기술 결정을 선별해라.

나중에 바꾸면 코드, 데이터, 배포, 테스트에 큰 영향을 주는 결정만 골라라.
단순 취향, 파일명, 작은 라이브러리, 미확정 아이디어는 ADR로 만들지 마라.

각 후보마다 제목, 왜 ADR인지, 결정 내용, 검토한 대안, 되돌리기 어려운 이유,
제안 파일명(docs/adr/0001-title.md 형식)을 짧게 작성해라.
아직 파일을 쓰지 말고 먼저 승인받아라.
```

5. AGENTS.md 최종 반영

```text
확정된 PRD, ARCHITECTURE, ADR, COMMANDS 내용을 기준으로 AGENTS.md의
프로젝트명, 목표, 기술 스택, 명령어 placeholder를 채울 계획을 작성해라.
CRITICAL 규칙은 유지하되, 이 프로젝트에 맞게 외부 API, DB, 인증, 파일 시스템
경계를 더 구체화할 부분이 있으면 제안해라.
```

| 순서 | 파일 | 채울 내용 | 완료 기준 |
| ---: | --- | --- | --- |
| 1 | 프로젝트 폴더, `.githooks/*` | 템플릿 복사, Git hook 경로 설정 | `git config core.hooksPath`가 `.githooks`를 반환 |
| 2 | `.codex/project-profile.json` | `projectName`만 실제 프로젝트 이름으로 변경. `guardMode`는 초반 기본값 `soft` 유지 | 프로젝트 이름 placeholder가 사라짐 |
| 3 | `docs/PRD.md` | 목표, 사용자, MVP 범위, 완료 기준, 제외 범위 | MVP 안팎을 Codex가 구분할 수 있음 |
| 4 | `docs/ARCHITECTURE.md` | 기술 스택, 디렉터리 구조, 모듈 경계, 데이터 흐름, 테스트 전략 | 구현 경계와 검증 방식이 한 문서에 정리됨 |
| 5 | `docs/ADR.md`, `docs/adr/*` | 되돌리면 안 되는 기술 결정과 변경 규칙 | 주요 선택의 이유와 상태가 기록됨 |
| 6 | `docs/COMMANDS.md`, `.codex/project-profile.json` | 확정된 기술 스택 기준의 `dev`, `lint`, `test`, `build`, `profile`, `sourceRoots`, `testRoots`, 필요 시 `stageChecks`, `guardrailDocs` | 최소 `test`와 `build`가 비어 있지 않거나 manifest로 감지 가능 |
| 7 | `AGENTS.md` | 프로젝트명, 목표, 스택, 명령어, CRITICAL 규칙 | 템플릿 placeholder가 남아 있지 않음 |
| 8 | `scripts/doctor.py --instance` | 복사한 프로젝트의 적용 상태 점검 | doctor가 exit code 0으로 종료 |

마지막으로 복사한 프로젝트의 적용 완료 상태를 확인합니다.

```bash
python scripts/doctor.py --instance
```

`doctor.py --instance`는 아래 상태를 발견하면 non-zero로 종료합니다.

- 필수 문서나 `AGENTS.md`에 template placeholder가 남아 있음
- `.codex/project-profile.json`의 `projectName`이 비어 있거나 placeholder임
- `test` 또는 `build` 명령이 `docs/COMMANDS.md`와 project profile 양쪽에서 준비되지 않음
- `git core.hooksPath`가 `.githooks`로 설정되어 있지 않음

이 템플릿 레포 자체를 점검할 때는 template 모드를 사용합니다.

```bash
python scripts/doctor.py --template
```

## 운영 흐름

`python scripts/doctor.py --instance`가 통과한 뒤부터 아래 흐름으로 phase를
나누고 step PR을 실행합니다.

먼저 Plan Mode에서 Harness skill로 phase/step 설계안을 만듭니다.

```text
Harness skill을 사용해서 확정된 문서를 기준으로 phase를 설계해라.
MVP를 phases/{phase}/README.md, index.json, stepN.md로 나누되, 각 step은
하나의 레이어 또는 모듈만 다루게 작게 쪼개라.
각 step에는 읽어야 할 파일, 작업, 인수 기준, 검증 절차, 금지사항을 포함하고,
docs/COMMANDS.md의 test/build 명령을 완료 기준에 반영해라.
아직 phase를 실행하거나 코드를 구현하지 말고, 먼저 phase/step 설계안을 제시해라.
```

1. 설계안을 확정한 뒤 Harness skill로 MVP를 `phases/{phase}/README.md`, `index.json`, `stepN.md`로 나눕니다.
2. phase 전체 또는 다음 step만 실행합니다.

```bash
python scripts/execute.py {phase-name}
python scripts/execute.py {phase-name} --push
python scripts/execute.py {phase-name} --next-step-only
```

3. step별 PR 루프를 사용할 때는 아래 autopilot 사전 조건을 먼저 확인합니다.

- 문서와 phase 파일 변경이 별도 commit으로 완료되어 있음
- `git status --short`가 비어 있는 clean worktree 상태임
- `git remote get-url origin`이 성공함
- `gh auth status`가 성공함
- base branch가 `origin`과 fast-forward 동기화 가능한 상태임
- base 브랜치에서 `python scripts/checks.py --stage manual`이 통과함 (의도적으로 생략하려면 `--skip-base-checks`)

4. 사전 조건을 만족하면 autopilot을 실행합니다.

```bash
python scripts/autopilot.py {phase-name} --max-review-fixes 2
```

5. autopilot은 다음 pending step을 `codex/{phase}-step{N}-{name}` 브랜치에서 실행하고 Draft PR을 만듭니다.
6. step 인수 기준 명령 또는 `python scripts/checks.py --stage manual`, `git diff --check`, scope rule scan, Codex read-only review가 통과하면 PR을 ready로 전환합니다.
7. PR ready 후 `gh pr checks --watch` 원격 체크가 통과해야 squash merge합니다. CI가 없는 저장소는 `--allow-no-checks`로 no-checks grace 대기를 생략할 수 있습니다.
8. 리뷰가 실패하면 PR 코멘트, GitHub Issue, `issues/{phase}/issue-N.md`를 남기고 같은 PR 브랜치에서 자동 수정과 재리뷰를 진행합니다.
9. 재시도 후에도 실패하면 PR과 Issue를 열어둔 채 중단합니다.

## Guard 모드

기본 guard는 soft입니다. 위험 명령은 항상 차단하지만, 테스트 파일 누락이나
검증 실패는 경고로 남기고 흐름을 막지 않습니다. 프로젝트 구조와 검증 명령이
안정되면 `.codex/project-profile.json`의 `guardMode`를 `hard`로 바꿔 차단
모드로 전환합니다.

항상 차단되는 위험 명령 예시는 다음과 같습니다.

- `rm -rf`, `rm -fr`: 강제 재귀 삭제
- `git reset --hard`: 작업 내용 강제 폐기
- `git clean -fd`, `git clean -fdx`: 추적되지 않는 파일 삭제
- `git push --force`, `git push --force-with-lease`: 강제 push
- `chmod -R 777`: 재귀 전체 쓰기 권한 부여
- `sudo`: 권한 상승 명령
- `DROP TABLE`: 테이블 삭제 SQL
- `curl ... | sh`, `wget ... | bash`: 다운로드한 스크립트 즉시 실행

```json
{
  "guardMode": "soft"
}
```

## 템플릿 자체 테스트

`docs/COMMANDS.md`와 `.codex/project-profile.json`의 `dev`, `lint`, `test`,
`build` 명령은 이 템플릿을 복사한 대상 프로젝트에서 채웁니다. 템플릿 레포
자체의 Python 스크립트 테스트를 실행할 때만 dev 의존성을 설치합니다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest scripts
```

macOS/Linux에서 `python` 명령이 Python 3를 가리키지 않으면 `python3`를 사용합니다.

## 명령 관리

`docs/COMMANDS.md`가 실행 명령의 기본 문서 기준입니다. `.codex/project-profile.json`의
`commands`는 로컬 환경이나 자동화에서 필요한 check별 override이며, 있으면
`scripts/checks.py`가 같은 이름의 `docs/COMMANDS.md` 명령보다 우선 사용합니다.
profile override가 없으면 `docs/COMMANDS.md`, 그 다음 프로젝트 manifest 감지 결과를
사용합니다. `test`와 `build` 명령은 필수이며, 둘 중 하나라도 설정 또는 감지되지
않으면 manual/final check와 autopilot gate가 실패합니다. stop hook은 기본적으로
`lint`만 실행하므로, stop 시점에 `test`나 `build`까지 돌리려면
`.codex/project-profile.json`의 `stageChecks`에 명시합니다.

```json
{
  "stageChecks": {
    "stop": ["lint"],
    "manual": ["lint", "test", "build"]
  },
  "guardrailDocs": ["docs/PRD.md", "docs/ARCHITECTURE.md", "docs/COMMANDS.md"]
}
```

지원하는 감지 대상:

- Spring Boot: `gradlew`, `gradlew.bat`, `build.gradle`, `pom.xml`, `mvnw`, `mvnw.cmd`
- Python: `pyproject.toml`, `uv.lock`, `pytest`, `ruff`
- Node: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`

## Scope Rules

scope rule은 MVP 범위 밖 기능이 step PR에 끼어드는 것을 막기 위한 데이터 기반
overlay입니다. 템플릿의 `.codex/scope-rules.json`은 빈 기본값입니다. 제품별 금지어,
API, 외부 연동, 저장소 선택 같은 규칙은 각 프로젝트에서 추가합니다.

전역 규칙:

```json
{
  "forbidden": [
    {
      "message": "예시 범위가 추가되었습니다.",
      "anySubstrings": ["예시"],
      "anyLowered": ["example"],
      "requiresAnySubstrings": ["필수", "구현"],
      "excludesAnySubstrings": ["기존 계약"]
    }
  ]
}
```

phase별 `phases/<phase>/scope-rules.json`은 `extraForbidden`으로 금지 규칙을 추가하고,
`allowedScopeMessages`로 특정 `steps` 또는 `stepNames`에서만 기존 금지 메시지를
허용할 수 있습니다. 이 파일은 프로젝트/phase overlay이며, 템플릿 스크립트에 제품
고유 키워드를 하드코딩하지 않습니다.

## ADR 규칙

- ADR은 `docs/adr/0001-title.md` 형식으로 기록합니다.
- `docs/ADR.md`는 ADR 인덱스와 운영 규칙만 유지합니다.
