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
- `docs/COMMANDS.md`: dev, lint, test, build, review 명령의 단일 출처
- `.codex/hooks.json`: Codex tool hook 설정
- `.codex/hooks/tdd-guard.sh`: Git/Codex hook wrapper
- `.codex/project-profile.json`: guard 모드와 명령 설정
- `.githooks/pre-commit`: 커밋 전 검증 hook
- `.agents/skills/harness`: phase/step 설계와 실행 워크플로우
- `.agents/skills/review`: 문서와 규칙 기준 자체 리뷰 워크플로우
- `scripts/execute.py`: phase step 실행기
- `scripts/autopilot.py`: step별 PR 생성, 자체 리뷰, 이슈 기록, 자동 병합 루프
- `scripts/checks.py`: 프로젝트 명령 감지 및 실행
- `scripts/doctor.py`: 템플릿 원본과 복사된 프로젝트 적용 상태 점검
- `scripts/guard.py`: 위험 명령, TDD, pre-commit/stop 정책
- `phases/README.md`, `phases/index.json`: Harness phase 구조와 최상위 인덱스
- `issues/README.md`: phase 실패 기록 형식

## 30분 셋업 순서

새 프로젝트에 이 템플릿을 가져온 뒤 아래 순서대로 placeholder를 실제 값으로
바꿉니다. 앞 단계가 비어 있으면 Codex가 MVP 범위, 검증 명령, phase 경계를
잘못 판단할 수 있으므로 순서를 건너뛰지 않습니다.

먼저 Git hook 경로와 실행 권한을 설정합니다.

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .codex/hooks/tdd-guard.sh
```

그다음 파일을 아래 순서대로 채웁니다.

| 순서 | 파일 | 채울 내용 | 완료 기준 |
| ---: | --- | --- | --- |
| 1 | 프로젝트 폴더, `.githooks/*` | 템플릿 복사, Git hook 경로, hook 실행 권한 | `git config core.hooksPath`가 `.githooks`를 반환 |
| 2 | `.codex/project-profile.json` | `projectName`, `profile`, `sourceRoots`, `testRoots`, `guardMode` | `projectName`이 실제 이름이고 초기 `guardMode`는 `soft` |
| 3 | `docs/COMMANDS.md`, `.codex/project-profile.json` | `dev`, `lint`, `test`, `build` 명령 | 최소 `test`와 `build`가 비어 있지 않음 |
| 4 | `docs/PRD.md` | 목표, 사용자, MVP 범위, 완료 기준, 제외 범위 | MVP 안팎을 Codex가 구분할 수 있음 |
| 5 | `docs/ARCHITECTURE.md` | 기술 스택, 디렉터리 구조, 모듈 경계, 데이터 흐름, 테스트 전략 | 구현 경계와 검증 방식이 한 문서에 정리됨 |
| 6 | `docs/ADR.md`, `docs/adr/*` | 되돌리면 안 되는 기술 결정과 변경 규칙 | 주요 선택의 이유와 상태가 기록됨 |
| 7 | `AGENTS.md` | 프로젝트명, 목표, 스택, 명령어, CRITICAL 규칙 | 템플릿 placeholder가 남아 있지 않음 |
| 8 | `scripts/doctor.py --instance` | 복사한 프로젝트의 적용 상태 점검 | doctor가 exit code 0으로 종료 |

마지막으로 복사한 프로젝트의 적용 완료 상태를 확인합니다.

```bash
python3 scripts/doctor.py --instance
```

`doctor.py --instance`는 아래 상태를 발견하면 non-zero로 종료합니다.

- 필수 문서나 `AGENTS.md`에 template placeholder가 남아 있음
- `.codex/project-profile.json`의 `projectName`이 비어 있거나 placeholder임
- `test` 또는 `build` 명령이 `docs/COMMANDS.md`와 project profile 양쪽에서 준비되지 않음
- `git core.hooksPath`가 `.githooks`로 설정되어 있지 않음

이 템플릿 레포 자체를 점검할 때는 template 모드를 사용합니다.

```bash
python3 scripts/doctor.py --template
```

## 운영 흐름

`python3 scripts/doctor.py --instance`가 통과한 뒤부터 아래 흐름으로 phase를
나누고 step PR을 실행합니다.

1. Harness skill로 MVP를 `phases/{phase}/README.md`, `index.json`, `stepN.md`로 나눕니다.
2. phase 전체 또는 다음 step만 실행합니다.

```bash
python3 scripts/execute.py {phase-name}
python3 scripts/execute.py {phase-name} --push
python3 scripts/execute.py {phase-name} --next-step-only
```

3. step별 PR 루프를 사용할 때는 autopilot을 실행합니다.

```bash
python3 scripts/autopilot.py {phase-name} --base main --max-review-fixes 2
```

4. autopilot은 다음 pending step을 `codex/{phase}-step{N}-{name}` 브랜치에서 실행하고 Draft PR을 만듭니다.
5. `python3 scripts/checks.py --stage manual`, `git diff --check`, Codex read-only review가 통과하면 PR을 ready로 전환하고 squash merge합니다.
6. 리뷰가 실패하면 PR 코멘트, GitHub Issue, `issues/{phase}/issue-N.md`를 남기고 같은 PR 브랜치에서 자동 수정과 재리뷰를 진행합니다.
7. 재시도 후에도 실패하면 PR과 Issue를 열어둔 채 중단합니다.

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
python3 -m pip install -r requirements-dev.txt
python3 -m pytest scripts
```

## 명령 관리

`docs/COMMANDS.md`가 실행 명령의 단일 출처입니다. `scripts/checks.py`는 먼저
`.codex/project-profile.json`의 명령을 보고, 없으면 `docs/COMMANDS.md`, 그 다음
프로젝트 manifest를 감지합니다. `test`와 `build` 명령은 필수이며, 둘 중 하나라도
설정 또는 감지되지 않으면 manual check와 autopilot gate가 실패합니다.

지원하는 감지 대상:

- Spring Boot: `gradlew`, `build.gradle`, `pom.xml`, `mvnw`
- Python: `pyproject.toml`, `uv.lock`, `pytest`, `ruff`
- Node: `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`

## ADR 규칙

- ADR은 `docs/adr/0001-title.md` 형식으로 기록합니다.
- `docs/ADR.md`는 ADR 인덱스와 운영 규칙만 유지합니다.
