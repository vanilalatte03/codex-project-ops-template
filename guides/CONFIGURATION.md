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
