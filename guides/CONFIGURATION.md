# 설정 레퍼런스

guard 모드, 명령 관리, scope rule, ADR 규칙의 상세 기준입니다. 전체 흐름은
루트 [README.md](../README.md)를 참조합니다.

## Guard 모드

기본 guard는 `soft`입니다. 위험 명령은 항상 차단하지만, 테스트 파일 누락이나
검증 실패는 경고로 남기고 흐름을 막지 않습니다. 프로젝트 구조와 검증 명령이
안정되면 `.codex/project-profile.json`의 `guardMode`를 `hard`로 바꿔 차단
모드로 전환합니다.

```json
{
  "guardMode": "soft"
}
```

항상 차단되는 위험 명령 예시는 다음과 같습니다.

- `rm -rf`, `rm -fr`: 강제 재귀 삭제
- `git reset --hard`: 작업 내용 강제 폐기
- `git clean -fd`, `git clean -fdx`: 추적되지 않는 파일 삭제
- `git push --force`, `git push --force-with-lease`: 강제 push
- `chmod -R 777`: 재귀 전체 쓰기 권한 부여
- `sudo`: 권한 상승 명령
- `DROP TABLE`: 테이블 삭제 SQL
- `curl ... | sh`, `wget ... | bash`: 다운로드한 스크립트 즉시 실행

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

## Phase task index

`phases/{phase}/index.json`의 v1 `steps[]`와 v2 `tasks[]` 필드, 공통 status,
dependency reference와 migration 경계는 [docs/TASK_SCHEMA.md](../docs/TASK_SCHEMA.md)를
기준으로 합니다. `execute.py`와 `autopilot.py`는 phase index를 먼저 검증하므로
중복 id, missing/self dependency, 잘못된 타입이나 status는 Codex 호출 전에
파일·필드 경로와 reason을 출력하고 중단합니다.

v2의 `dependsOn`은 현재 배열 순서의 직렬 실행을 바꾸지 않는 메타데이터입니다.
ready set, cycle 처리, DAG 스케줄링과 병렬 실행은 후속 범위이며, v1 phase를 v2로
자동 migration하지 않습니다. 변환이 필요하면 원본 백업과 dry-run, 사용자 승인,
별도 commit을 갖춘 명시적 opt-in 작업으로 수행합니다.

## Progressive guardrails

`scripts/execute.py`는 Codex prompt에 AGENTS, phase 문서, 관련 문서의 본문을
복사하지 않습니다. 대신 작업 목표, acceptance criteria, hard constraints, 이전
step summary와 Codex가 저장소에서 직접 읽어야 할 경로를 전달합니다. 문서 본문은
Codex가 해당 경로를 읽을 때만 context에 들어옵니다.

`guardrailDocs`는 기존과 같이 경로 선택 입력입니다.

1. 비어 있지 않은 `guardrailDocs` 목록을 명시하면 그 목록을 사용합니다.
2. 목록이 비어 있거나 키가 없으면 phase README/step 문서가 참조한 경로를
   사용합니다.
3. 참조 경로가 없으면 `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md`,
   `docs/COMMANDS.md`, `docs/SCOPE_CHANGE_CHECKLIST.md` 중 존재하는 경로를
   fallback으로 사용합니다.

모든 경로는 저장소 상대 경로여야 합니다. 선택된 경로와 현재 step의 `읽어야 할
파일`이 누락되거나 읽을 수 없으면 Codex 실행 전에 실패하므로, 잘못된 문서 참조를
조용히 건너뛰지 않습니다. `guardrailDocs: []`는 자동 선택을 의미하며 문서 본문을
prompt에 포함하라는 뜻이 아닙니다.

## Codex subprocess 환경

Harness가 `execute.py`와 `autopilot.py`에서 실행하는 Codex 명령은
`shell_environment_policy.inherit="core"`를 사용합니다. 플랫폼별 핵심 환경과
`PATH`는 유지하면서 전체 부모 환경을 그대로 넘기지 않습니다. 또한
`shell_environment_policy.ignore_default_excludes=false`를 함께 지정해 Codex의
공식 기본 제외 규칙(이름에 `KEY`, `SECRET`, `TOKEN`이 포함된 변수)을 적용합니다.

프로젝트에 꼭 필요한 non-secret runtime 변수만 다음 공식 확장 지점에 이름으로
추가합니다.

```toml
[shell_environment_policy.filters]
"PATH" = "include"
"PROJECT_RUNTIME_HOME" = "include"
```

`include`를 하나라도 추가하면 필터가 allowlist가 되므로, 필요한 경우 `PATH`와
프로젝트가 요구하는 core 변수를 함께 적습니다. credential 값이나 secret-name
변수는 이 파일과 fixture에 넣지 않습니다. `execute.py`와 autopilot의 Codex
호출은 공통 명령 생성기를 사용하므로 두 실행 경로의 정책이 달라지지 않습니다.

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
