# Commands

이 파일은 프로젝트 실행 명령의 기본 문서 기준입니다. Plan Mode에서 기술 스택을
확정한 뒤 실제 명령으로 채웁니다. 비어 있는 명령은 실행하지 않습니다.
`.codex/project-profile.json`의 `commands`가 있으면 check별 override로 먼저 적용하고,
없으면 이 파일, 그 다음 프로젝트 manifest 감지 결과를 사용합니다. manual/final
stage에서 `test`와 `build`는 필수 gate입니다. 둘 중 하나라도 비어 있거나
감지되지 않으면 `scripts/checks.py --stage manual`과 autopilot review gate가
실패합니다. stop hook은 기본적으로 `lint`만 실행하며, 더 무거운 검증은
`.codex/project-profile.json`의 `stageChecks`로 명시적으로 확장합니다.

## 활성 명령

| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| dev |  | no | 개발 서버 또는 watch 실행 |
| lint |  | no | 정적 분석과 포맷 검사 |
| test |  | yes | 자동 테스트 |
| build |  | yes | 배포 가능한 빌드 또는 패키징 |
| frontend-build |  | no | 별도 프론트엔드 빌드가 있을 때 사용 |
| harness-test |  | no | 템플릿/Harness 스크립트 자체 테스트 |
| docs-check |  | no | `--stage final`이 phase별 `docs-checks.json` 검사를 내장 실행하므로 보통 비워 둔다. 별도 문서 검사 도구를 추가할 때만 채운다 |
| review | `python scripts/doctor.py --template` | no | 템플릿 원본 구조 점검 |
| phase | `python scripts/execute.py <phase-name>` | no | Harness phase 실행 |
| phase-step | `python scripts/execute.py <phase-name> --next-step-only` | no | 다음 pending step만 실행 |
| autopilot | `python scripts/autopilot.py <phase-name> --max-review-fixes 2` | no | phase 전체 구현 시 권장. step별 PR 생성, 자체 리뷰, 이슈 기록, 자동 병합 루프 |

## Harness 운영 옵션

Codex 호출은 프롬프트를 stdin으로 전달해 긴 phase 문서에서 argv 길이 제한을 피합니다.
`execute.py`의 기본 reasoning effort는 `medium`입니다. `autopilot.py`의 기본값은
step 구현 `medium`, PR self-review `high`, 자동 fix `medium`입니다. `xhigh`는
`--allow-xhigh`와 함께 명시한 경우에만 허용합니다.

```bash
python scripts/execute.py <phase-name> --codex-effort medium
python scripts/execute.py <phase-name> --reasoning-effort medium  # 호환 alias
python scripts/autopilot.py <phase-name> --dry-run --max-steps 1
python scripts/autopilot.py <phase-name> --step-effort medium --review-effort high --fix-effort medium
```

autopilot 운영 안전장치:

- `--base`를 생략하면 origin HEAD 브랜치를 자동 감지한다(실패 시 `main`).
- `--dry-run`은 실행 없이 pending step과 브랜치 계획만 출력한다.
- `--max-steps N`은 한 번의 실행에서 최대 N개의 step PR만 병합하고 멈춘다.
- 동시 실행은 `.codex/autopilot.lock`으로 차단한다(stale lock은 자동 회수).
- 루프 시작 전에 base 브랜치에서 `checks.py --stage manual`을 실행해 base가 이미 깨진 상태면 fail-fast 한다. 의도된 상태라면 `--skip-base-checks`로 생략한다.
- step 문서의 인수 기준 명령은 실행 전에 `guard.py` 위험 명령 정책을 통과해야 한다.
- `execute.py`는 Codex의 completed 보고 후에도 인수 기준을 직접 재실행한다.
- `checks.py --stage final`은 test/build 통과 후 phase `docs-checks.json`의 `required`/`finalRequired`/`forbidden` 규칙을 내장 실행한다. docs-check 명령 등록 여부와 무관하다.
- PR은 `gh pr checks --watch`로 원격 체크 통과를 확인한 뒤에만 squash merge한다.
- `no checks reported`는 ready 직후 체크 생성 전 레이스일 수 있어 grace 동안 재확인한다. CI가 없는 저장소는 `--allow-no-checks`로 대기를 생략할 수 있다.
- 금지 범위 규칙은 `.codex/scope-rules.json`의 `forbidden`, phase별 확장/허용은 `phases/<phase>/scope-rules.json`의 `extraForbidden`, `allowedScopeMessages`로 관리한다.
- `execute.py`는 phase README/step 문서가 참조하는 `docs/*.md`만 기본 첨부한다. `.codex/project-profile.json`의 `guardrailDocs`가 있으면 그 목록이 우선한다.

`scope-rules.json` rule schema:

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

phase별 파일은 `extraForbidden`으로 금지 규칙을 추가하고, `allowedScopeMessages`로 특정
`steps` 또는 `stepNames`에서만 허용할 수 있습니다. 템플릿 기본 파일은 의도적으로 빈
규칙만 제공하며, 제품별 MVP 금지어는 각 프로젝트에서 추가합니다.

## 기술별 예시

```bash
# Spring Boot - Gradle
./gradlew test
./gradlew build
.\gradlew.bat test
.\gradlew.bat build

# Spring Boot - Maven
./mvnw test
./mvnw package
.\mvnw.cmd test
.\mvnw.cmd package

# Python
uv run pytest
uv run ruff check .
python -m pytest

# Node
npm run lint
npm test
npm run build
pnpm test
yarn test
```

macOS/Linux에서 `python` 명령이 Python 3를 가리키지 않으면 `python3`를 사용합니다.
Windows PowerShell에서는 `python`, `.\gradlew.bat`, `.\mvnw.cmd` 형태를 우선 사용합니다.
