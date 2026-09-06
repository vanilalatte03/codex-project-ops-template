# Harness 버전과 업그레이드

이 템플릿을 복사한 인스턴스는 시간이 지나면 템플릿과 갈라집니다. 어느 시점의
템플릿에서 출발했는지 추적하기 위해 버전 마커 두 개를 사용합니다.

- `scripts/codex_common.py`의 `TEMPLATE_VERSION`: 설치된 harness의 버전.
  업그레이드로 `scripts/`를 덮어쓰면 자동으로 함께 따라옵니다.
- `.codex/project-profile.json`의 `templateVersion`: 이 인스턴스가 마지막으로
  동기화한 템플릿 버전 기록.

`doctor.py --instance`는 둘이 다르면 실패합니다. harness 파일은 새로 복사했는데
기록을 안 올렸거나, 기록만 올리고 파일을 안 가져온 "절반만 끝난 업그레이드"를
잡습니다.

## 파일 소유 구분

업그레이드의 기본 원칙은 "템플릿 소유 단위는 통째로 덮어쓰고, 프로젝트 소유
단위는 건드리지 않는다"입니다.

| 단위 | 소유 | 업그레이드 시 |
| --- | --- | --- |
| `scripts/` (테스트 포함, `worktree.py` 포함) | 템플릿 | 통째로 덮어쓰기 |
| `.agents/skills/harness/`, `.agents/skills/review/` | 템플릿 공통 스킬 | 각 디렉터리만 통째로 덮어쓰기 |
| `.githooks/`, `.codex/hooks/`, `.codex/hooks.json`, `.codex/config.toml`, `.gitattributes` | 템플릿 | 통째로 덮어쓰기 |
| `guides/PROMPTS.md`, `guides/CONFIGURATION.md`, `guides/UPGRADE.md` | 템플릿 | 통째로 덮어쓰기 |
| `.github/workflows/template-ci.yml` | 템플릿 전용 | 인스턴스에는 복사하지 않음 |
| `.agents/skills/<project-skill>/` | 프로젝트 | 덮어쓰지 않음 |
| `AGENTS.md`, `docs/`, `phases/`, `issues/`, `archive/` | 프로젝트 | 덮어쓰지 않음 |
| `.codex/project-profile.json`, `.codex/scope-rules.json`, `phases/*/scope-rules.json` | 프로젝트 | 덮어쓰지 않음. 단 `templateVersion` 키만 갱신 |

`.agents/skills/`는 템플릿 공통 스킬과 프로젝트 전용 스킬이 함께 들어갈 수 있는
혼합 루트입니다. 업그레이드할 때 루트 전체를 삭제하거나 동기화하지 말고,
템플릿이 소유한 공통 스킬 디렉터리만 이름 기준으로 교체합니다. 템플릿에 새 공통
스킬이 추가되면 이 표에 해당 디렉터리를 먼저 추가한 뒤 인스턴스 업그레이드
절차에 포함합니다. 프로젝트 전용 스킬은 템플릿 공통 스킬과 같은 이름을 쓰지
않습니다. 이름이 충돌하면 업그레이드 전에 프로젝트 스킬 이름을 바꾸거나 공통
스킬 편입 여부를 결정합니다.

`docs/TASK_SCHEMA.md`는 phase index 계약을 설명하는 기준 문서지만 `docs/` 아래
프로젝트 소유 파일로 취급합니다. `scripts/upgrade.py`는 이를 포함한 프로젝트의
`docs/`, `phases/`, `issues/`, `archive/`를 자동 덮어쓰지 않습니다. 기존 인스턴스는
계약을 확인한 뒤 필요한 문서 변경을 수동으로 검토합니다.

`.github/workflows/template-ci.yml`은 템플릿 repo 전용 검증입니다. 실제 프로젝트
인스턴스에는 복사하지 않고, 이미 복사했다면 삭제합니다. 실제 프로젝트의 CI는
`docs/COMMANDS.md`에 확정한 `lint`, `test`, `build` 명령 기준으로 별도 작성합니다.

인스턴스에서 `scripts/`나 `.agents/skills/harness/` 같은 템플릿 소유 파일을 직접
고치면 다음 업그레이드 때 덮어써 사라집니다. harness나 review 공통 스킬 개선이
필요하면 템플릿 repo에 먼저 반영해 버전을 올리고, 업그레이드 절차로 인스턴스에
가져옵니다. 프로젝트별 작업 방식은 별도 프로젝트 전용 스킬 디렉터리로 둡니다.

## 업그레이드 절차

`scripts/upgrade.py`가 위 표의 템플릿 소유 단위 복사와 `templateVersion` 갱신을
대신합니다. 단, 계약 변화의 영향 검토(1번)와 검증(5번)은 사람이 합니다.

1. 인스턴스 `.codex/project-profile.json`의 `templateVersion`과 템플릿 repo의
   현재 `TEMPLATE_VERSION`을 비교하고, 그 사이의 계약 변화(hook 설정, profile 키
   추가, phase 파일 형식 변경 등)를 템플릿 `CHANGELOG.md`에서 확인합니다.
2. 템플릿 체크아웃을 받아 인스턴스 루트에서 업그레이드를 실행합니다. 먼저
   `--dry-run`으로 덮어쓸 단위를 확인한 뒤 적용합니다. 이 스크립트가 표의 템플릿
   소유 단위를 통째로 덮어쓰고, 4번의 `templateVersion` 갱신까지 처리합니다.

   ```bash
   python scripts/upgrade.py --from <template-checkout> --dry-run
   python scripts/upgrade.py --from <template-checkout>
   ```

3. 1번에서 확인한 계약 변화가 프로젝트 소유 파일에 영향을 주면 수동으로
   반영합니다.
4. (스크립트가 처리) `.codex/project-profile.json`의 `templateVersion`이 새
   버전으로 갱신됐는지 확인합니다.
5. `python -m pytest scripts`와 `python scripts/doctor.py --instance`가 통과하는지
   확인합니다.

수동으로 복사하려면 위 "파일 소유 구분" 표를 그대로 따르고, 마지막에
`templateVersion`을 직접 갱신합니다.

## phase index migration

Harness 업그레이드는 phase index를 자동으로 v1에서 v2로 변환하지 않습니다.
`phases/{phase}/index.json`, `stepN.md`, README와 실행 기록은 프로젝트 소유이며,
템플릿의 `scripts/task_schema.py`는 두 형식을 읽고 검증만 합니다. v2로 전환하려는
프로젝트는 별도 opt-in 작업에서 다음 순서를 지킵니다.

1. 원본 phase/index를 백업하고 v1 task와 새 v2 `id`의 매핑을 확정합니다.
2. `objective`, `dependsOn`, `issue`, `risk`를 dry-run으로 검토하고 누락된
   dependency와 companion 문서를 확인합니다.
3. validator, 전체 테스트와 phase 문서 검증을 통과시킨 뒤 사용자 승인을 받습니다.
4. 승인된 변경만 별도 commit으로 적용하고, 실패하면 백업한 v1 원본으로 복구합니다.

읽기 중 생성되는 v2의 `step`/`name` alias는 메모리 값이며 JSON에 저장되지
않습니다. `dependsOn`은 현재 직렬 실행 순서를 바꾸지 않고, DAG scheduler·cycle
처리·parallelism은 후속 기능으로 남겨 둡니다.

## task worktree migration

`scripts/worktree.py`와 `docs/WORKTREE_LIFECYCLE.md`는 새 Harness의 실행 계약이다.
업그레이드 시 기존 phase/index, 사용자 branch와 worktree를 자동으로 Harness
소유로 바꾸지 않는다. marker가 없는 기존 path/branch는 먼저 사람이 소유권을
확인하고, 필요한 경우 새 managed root에서 task를 시작한다.

1. 현재 작업의 `git worktree list --porcelain`, branch, dirty/ignored 파일을
   보존하고 `python scripts/worktree.py list`로 marker/stale 상태를 확인한다.
2. 템플릿 소유 `scripts/`를 dry-run으로 교체한 뒤 `doctor.py --instance`, 전체
   unit test와 `git diff --check`를 실행한다.
3. 실패·blocked·중단 marker는 삭제하지 말고 같은 `taskId`로 resume한다. base가
   바뀌었거나 marker/administrative entry가 불일치하면 수동 reconcile을 먼저
   완료한다.
4. merge되지 않은 worktree는 cleanup하지 않는다. merge된 Harness 소유 task도
   `docs/WORKTREE_LIFECYCLE.md`의 clean/head/owner gate를 다시 통과한 뒤에만
   force 없는 정리를 수행한다.

`git reset --hard`, force push, 사용자 branch 삭제, 사용자 worktree 이동과 무차별
`git worktree prune`은 migration 절차에 포함되지 않는다.

## 템플릿 repo에서 버전 올리기

템플릿 repo에서 harness 동작을 바꾸는 커밋은 `scripts/codex_common.py`의
`TEMPLATE_VERSION`과 `.codex/project-profile.json`의 `templateVersion`을 함께
올립니다. 한쪽만 올리면 `doctor.py --template`(CI)이 실패합니다.
