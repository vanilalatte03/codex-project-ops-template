# Codex Project Ops Template

Codex 기반 개인 프로젝트 운영 템플릿입니다. 이 레포는 앱 코드를 직접 생성하지
않습니다. 대신 새 프로젝트 폴더에 Codex 운영 레이어를 설치해서, 문서로 MVP
범위를 먼저 확정하고 phase 단위로 구현·테스트·리뷰를 반복하는 흐름을
제공합니다.

## 전체 흐름

```text
① 셋업    템플릿 복사 → Git hook 설정 → Plan Mode로 문서 채우기 → doctor 통과
② 설계    Harness skill로 MVP를 phase/step 문서로 분해
③ 실행    execute.py로 step 구현, 또는 autopilot.py로 step별 PR 루프
④ 검증    guard hook + checks + 자체 리뷰가 매 step의 범위와 품질을 지킴
```

각 단계에서 Codex에 복붙할 프롬프트는 [guides/PROMPTS.md](guides/PROMPTS.md)에
모두 모여 있습니다.

## ① 셋업 (약 30분)

새 프로젝트에 템플릿을 복사한 뒤 아래 순서대로 placeholder를 실제 값으로
바꿉니다. 앞 단계가 비어 있으면 Codex가 MVP 범위, 검증 명령, phase 경계를
잘못 판단할 수 있으므로 순서를 건너뛰지 않습니다.

### 1. Git hook 경로 설정

macOS/Linux:
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .codex/hooks/tdd-guard.sh .codex/hooks/tdd-guard.py
```

Windows PowerShell:
```powershell
git config core.hooksPath .githooks
```

Codex hook은 `.codex/hooks.json`에서 `python3` 명령으로 실행됩니다. Windows에서는
Python 설치 후 앱 실행 환경의 PATH에서 `python3`가 동작하는지 확인합니다.

Codex 앱의 tool hook은 터미널 명령이 아니라 앱 설정에서 켭니다.

1. Codex 앱 왼쪽 아래 설정을 엽니다.
2. 왼쪽 메뉴에서 **코딩 > 훅**으로 이동합니다.
3. 현재 프로젝트 이름을 선택합니다.
4. **도구 사용 전**, **권한 요청**, **중지**에 보이는 hook 토글을 켭니다.

템플릿을 통째로 복사했다면 Codex 앱은 프로젝트의 `.codex/config.toml`과
`.codex/hooks.json`을 읽어 hook 내용을 표시합니다. 화면에 hook이 보이지 않으면
먼저 Codex 앱에서 연 폴더가 템플릿을 복사한 프로젝트 루트인지 확인합니다.

### 2. Plan Mode로 문서 채우기

Codex를 Plan Mode로 전환하고 [guides/PROMPTS.md](guides/PROMPTS.md)의 셋업
프롬프트를 순서대로 사용합니다. 목적은 Codex가 임의로 구현을 시작하기 전에
MVP 범위, 기술 스택, 검증 명령, phase 경계를 먼저 문서로 확정하게 만드는
것입니다.

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

### 3. doctor로 점검

```bash
python scripts/doctor.py --instance
```

`doctor.py --instance`는 아래 상태를 발견하면 non-zero로 종료합니다.

- 필수 문서나 `AGENTS.md`에 template placeholder가 남아 있음
- `.codex/project-profile.json`의 `projectName`이 비어 있거나 placeholder임
- `.codex/project-profile.json`의 `templateVersion`이 없거나 설치된 harness의
  `TEMPLATE_VERSION`(`scripts/codex_common.py`)과 다름
- `test` 또는 `build` 명령이 `docs/COMMANDS.md`와 project profile 양쪽에서 준비되지 않음
- `git core.hooksPath`가 `.githooks`로 설정되어 있지 않음

## ② 설계 — phase/step 나누기

doctor가 통과한 뒤 Plan Mode에서 Harness skill로 phase/step 설계안을 만듭니다.
프롬프트는 [guides/PROMPTS.md](guides/PROMPTS.md)의 "운영: phase/step 설계"를
사용합니다. 설계안을 확정하면 MVP가 `phases/{phase}/README.md`, `index.json`,
`stepN.md`로 나뉩니다.

## ③ 실행

### execute.py — 로컬 step 실행

```bash
python scripts/execute.py {phase-name}                  # phase 전체
python scripts/execute.py {phase-name} --next-step-only # 다음 step만
python scripts/execute.py {phase-name} --push           # 실행 후 push
```

### autopilot.py — step별 PR 루프

실행 전 아래 사전 조건을 먼저 확인합니다.

- 문서와 phase 파일 변경이 별도 commit으로 완료되어 있음
- `git status --short`가 비어 있는 clean worktree 상태임
- `git remote get-url origin`이 성공함
- `gh auth status`가 성공함
- base branch가 `origin`과 fast-forward 동기화 가능한 상태임
- base 브랜치에서 `python scripts/checks.py --stage manual`이 통과함
  (의도적으로 생략하려면 `--skip-base-checks`)

```bash
python scripts/autopilot.py {phase-name} --max-review-fixes 2  # phase 전체 구현 시 권장
```

autopilot은 step마다 아래 루프를 반복합니다.

1. 다음 pending step을 `codex/{phase}-step{N}-{name}` 브랜치에서 실행하고 Draft PR을 만듭니다.
2. step 인수 기준 명령 또는 `python scripts/checks.py --stage manual`, `git diff --check`, scope rule scan, Codex read-only review가 통과하면 PR을 ready로 전환합니다.
3. PR ready 후 `gh pr checks --watch` 원격 체크가 통과해야 squash merge합니다. CI가 없는 저장소는 `--allow-no-checks`로 no-checks grace 대기를 생략할 수 있습니다.
4. 리뷰가 실패하면 PR 코멘트, GitHub Issue, `issues/{phase}/issue-N.md`를 남기고 같은 PR 브랜치에서 자동 수정과 재리뷰를 진행합니다.
5. 재시도 후에도 실패하면 PR과 Issue를 열어둔 채 중단합니다.

## ④ 검증 장치

- **Guard**: `rm -rf`, `git reset --hard`, `sudo` 같은 위험 명령을 항상 차단합니다.
  기본 `soft` 모드는 테스트 누락이나 검증 실패를 경고로만 남기고, 안정되면
  `hard`로 전환해 차단합니다.
- **Checks**: `docs/COMMANDS.md` → profile override → manifest 감지 순서로
  `lint`/`test`/`build` 명령을 찾아 실행합니다. `test`와 `build`는 필수입니다.
- **Scope rules**: MVP 범위 밖 기능이 step PR에 끼어드는 것을 막는 금지어
  overlay입니다.

각 장치의 상세 설정은 [guides/CONFIGURATION.md](guides/CONFIGURATION.md)를
참조합니다.

## 레포 구성

| 영역 | 경로 | 역할 |
| --- | --- | --- |
| 규칙 | `AGENTS.md` | Codex가 따르는 100줄 안팎의 프로젝트 운영 규칙 |
| 프로젝트 문서 | `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md`, `docs/adr/`, `docs/COMMANDS.md`, `docs/SCOPE_CHANGE_CHECKLIST.md` | MVP 범위, 구조, 기술 결정, 검증 명령, 범위 변경 체크리스트 |
| 가이드 | `guides/PROMPTS.md`, `guides/CONFIGURATION.md`, `guides/UPGRADE.md` | 프롬프트 모음, 설정 레퍼런스, 업그레이드 절차 |
| Codex 설정 | `.codex/` | hook 설정, project profile, scope rules |
| Hook | `.githooks/pre-commit`, `.codex/hooks/` | 커밋 전 검증, cross-platform hook wrapper |
| Skill | `.agents/skills/harness`, `.agents/skills/review` | phase/step 설계·실행, 문서 기준 자체 리뷰 워크플로우 |
| 스크립트 | `scripts/`, `scripts/tests/` | `execute.py`, `autopilot.py`, `checks.py`, `doctor.py`, `guard.py`, `codex_common.py`, Harness 스크립트 테스트 |
| 작업 공간 | `phases/`, `issues/`, `archive/` | phase 문서(예시: `phases/0-example/`), 실패 기록, 직전 MVP 요약 |
| CI | `.github/workflows/template-ci.yml` | macOS/Linux/Windows 템플릿 검증 (인스턴스에는 복사하지 않음) |

`.github/workflows/template-ci.yml`은 이 템플릿 repo 자체를 검증하는 CI입니다.
새 프로젝트에 템플릿을 복사할 때는 이 파일을 복사하지 않습니다. 이미 실제
프로젝트에 들어갔다면 삭제하고, 필요한 경우 프로젝트의 `docs/COMMANDS.md`
기준으로 `lint`, `test`, `build`를 실행하는 별도 GitHub Actions workflow를
만듭니다.

## 업그레이드

복사한 인스턴스는 `.codex/project-profile.json`의 `templateVersion` 마커로
템플릿과의 동기화 상태를 추적하고, 템플릿 소유 단위(`scripts/`,
`.agents/skills/harness/`, `.agents/skills/review/`, hook 설정)를 통째로
덮어쓰는 방식으로 업그레이드합니다. 프로젝트 전용 skill 디렉터리는 보존합니다.
파일 소유 구분과 절차는 [guides/UPGRADE.md](guides/UPGRADE.md)를 참조합니다.

## 템플릿 자체 개발

이 템플릿 레포 자체를 수정할 때만 해당합니다. 대상 프로젝트의 `dev`, `lint`,
`test`, `build` 명령은 복사한 프로젝트에서 채웁니다.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest scripts
python scripts/doctor.py --template
```

macOS/Linux에서 `python` 명령이 Python 3를 가리키지 않으면 `python3`를 사용합니다.
