---
name: harness
description: "Codex가 이 Harness 프레임워크로 작업해야 할 때 사용한다. 프로젝트 문서 탐색, 구현 결정 논의, phases/ 아래 단계 파일과 docs-checks.json 설계, scripts/execute.py를 통한 페이즈 실행을 포함한다."
---

# Harness

## 개요

프로젝트 문서를 작고 자기완결적인 구현 단계로 나누고, Harness 페이즈 실행기로 순차 실행할 때 이 워크플로우를 사용한다.

## 워크플로우

### 탐색

`/docs/` 아래의 `PRD.md`, `ARCHITECTURE.md`, `ADR.md`, `COMMANDS.md` 같은 문서를 읽고 제품 의도, 아키텍처, 제약 조건, 검증 명령을 파악한다. 프로젝트 규칙은 `AGENTS.md`를 읽는다. `docs/adr/` 디렉터리가 있으면 분리된 ADR도 함께 읽는다. `AGENTS.md`가 프로젝트별 skill 문서를 지시하면 해당 skill도 읽는다.

### 논의

구현 세부사항이나 기술 선택이 불명확하면 페이즈 파일을 작성하기 전에 선택지를 사용자에게 제시하고 결정을 확정한다.

### 단계 설계

사용자가 구현 계획을 요청하면 집중된 단계들의 초안을 작성하고, 필요하면 페이즈 파일을 만들기 전에 피드백을 받는다.

단계 설계 규칙:

1. 범위를 최소화한다. 하나의 단계는 하나의 레이어 또는 모듈만 다룬다.
2. 각 단계는 자기완결적으로 작성한다. 이전 대화에 의존하지 말고 필요한 맥락을 단계 파일 안에 포함한다.
3. 사전 준비를 강제한다. 구현 전에 반드시 읽어야 할 문서와 파일을 나열한다.
4. 인터페이스와 시그니처는 명시하되, 중요한 규칙이 아닌 구현 세부사항은 에이전트 재량에 맡긴다.
5. `docs/COMMANDS.md`에 정의된 lint/test/build 명령을 인수 기준에 반영한다.
6. 주의사항은 `"X를 하지 마라. 이유: Y."` 형식으로 구체적으로 작성한다.
7. 단계 이름은 `project-setup`, `api-layer`, `auth-flow`처럼 kebab-case를 사용한다.
8. 각 단계는 Must-have / Should-have / Later 중 어느 범위에 속하는지 명시한다. 프로젝트가 P0/P1/P2 같은 용어를 쓰면 해당 프로젝트 문서의 정의를 따른다.
9. 문서 간 API, 범위, 실행 방법 충돌이 발견되면 구현 단계에 섞지 말고 별도 문서 동기화 step으로 분리한다.
10. MVP나 phase 범위가 바뀌면 `docs/SCOPE_CHANGE_CHECKLIST.md`로 함께 갱신할 파일을 먼저 확인한다.
11. phase별 문서 정합성 규칙은 `phases/{작업명}/docs-checks.json`에 함께 작성한다. MVP나 phase 범위가 바뀌면 `scripts/checks.py`가 아니라 이 파일을 갱신한다.
12. `docs-checks.json`은 정성 규칙의 SSOT가 아니다. final stage에서 기계적으로 잡을 수 있는 핵심 회귀 신호만 담는다.

## 생성할 파일

형식이 모두 채워진 실제 예시는 `phases/0-example/`을 참고한다.

### `phases/index.json`

최상위 페이즈 인덱스를 생성하거나 갱신한다:

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

`status`는 `pending`, `completed`, `error`, `blocked` 중 하나여야 한다. 생성 시 타임스탬프를 넣지 않는다. 타임스탬프는 `scripts/execute.py`가 기록한다.

### `phases/{작업명}/README.md`

작업 단위 README를 생성한다. 이 파일은 step PR 리뷰의 phase-level 계약이다:

````markdown
# Phase: {작업명}

## 목표
{이 phase가 완료해야 하는 사용자/시스템 결과}

## 작업 범위
- Must-have: {반드시 포함할 범위}

## 제외 범위
- {이번 phase에서 구현하지 않을 것}

## Steps
| Step | Name | Range |
| ---: | --- | --- |
| 0 | project-setup | Must-have |

## Step PR 리뷰 원칙
- 각 step PR의 리뷰 기준은 현재 `stepN.md`의 작업, 인수 기준, 금지사항이다.
- 미래 step에 배정된 기능이 아직 없다는 사실은 현재 step의 blocker가 아니다.
- 현재 step이 미래 step 범위를 선행 구현하면 blocker로 본다.
- 리뷰 실패는 같은 PR 브랜치에서 수정하고 `issues/{작업명}/issue-N.md`에 기록한다.

## 완료 기준
- {phase 전체가 완료됐다고 판단할 관찰 가능한 기준}

## 검증 명령
```bash
python scripts/checks.py --stage manual
```
````

### `phases/{작업명}/index.json`

작업 단위 인덱스를 생성한다:

```json
{
  "project": "<프로젝트명>",
  "phase": "<작업명>",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" },
    { "step": 1, "name": "core-types", "status": "pending" },
    { "step": 2, "name": "api-layer", "status": "pending" }
  ]
}
```

phase index의 전체 v1/v2 계약은 루트 [`docs/TASK_SCHEMA.md`](../../../docs/TASK_SCHEMA.md)에
둔다. 기존 파일을 보존해야 하므로 이 skill의 기본 예시는 v1 `steps[]` 형식이며,
`phases/0-example/index.json`은 변경하지 않는 호환 fixture다. outcome 중심 task가
필요한 새 phase는 다음 v2 모양을 사용한다:

```json
{
  "schemaVersion": 2,
  "project": "<프로젝트명>",
  "phase": "<작업명>",
  "tasks": [
    {
      "id": "api-layer",
      "objective": "사용자가 확인할 결과를 만든다.",
      "dependsOn": [],
      "issue": 123,
      "risk": "medium",
      "status": "pending"
    }
  ]
}
```

v1은 `steps[].step`, `steps[].name`, `steps[].status`를 사용하고, v2는
`id`·`objective`·`status`를 필수로 하며 `dependsOn`·`issue`·`risk`를 선택으로
둔다. 두 형식의 status는 `pending`, `completed`, `error`, `blocked`로 같다.
`scripts/task_schema.py`가 형식을 구분하고 필수 필드, 타입, 중복 id, self/unknown
dependency를 path/reason과 함께 Codex 호출 전에 검증한다. v2의 `dependsOn`은 이
단계에서 reference metadata이며 list order를 바꾸지 않는다. ready set, cycle,
DAG scheduler와 parallelism은 후속 #22 범위다.

validator가 v2 task에 노출하는 배열 위치 `step`과 id 기반 `name`은 현재
serial executor와 `stepN.md`를 연결하기 위한 메모리 alias다. 파일을 저장할 때
`tasks[]` 원형을 유지하며 v1에 v2 필드를 추가하지 않는다. v1→v2 변환은 원본
백업, dry-run, 검증과 사용자 승인을 포함한 별도 opt-in 작업으로만 수행한다.

규칙:

- 위 v1/v2 discriminator와 필드 규칙을 지킨다.
- `project`: 프로젝트 이름이며 보통 `AGENTS.md`에서 가져온다.
- `phase`: 디렉터리 이름과 일치하는 작업 이름이다.
- v1 `steps[].step`: 0부터 시작하는 순번이다.
- v1 `steps[].name`: kebab-case slug다.
- v1/v2 `status`: 초기값은 `pending`이다.

상태 필드:

| 상태 | 필드 | 작성 주체 |
| --- | --- | --- |
| `completed` | `completed_at`, `summary` | Codex가 `summary`를 쓰고, `execute.py`가 타임스탬프를 쓴다 |
| `error` | `failed_at`, `error_message` | Codex가 메시지를 쓰고, `execute.py`가 타임스탬프를 쓴다 |
| `blocked` | `blocked_at`, `blocked_reason` | Codex가 사유를 쓰고, `execute.py`가 타임스탬프를 쓴다 |

`summary`는 이후 단계에 유용한 인계 맥락을 담은 한 줄 요약이어야 한다.

### `phases/{작업명}/docs-checks.json`

phase 최종 완료 전 문서 정합성 검증 규칙을 생성한다. 이 파일은 step마다 실행되는 `manual` 검증이 아니라 모든 step이 끝난 뒤 `final` stage에서 한 번 실행되는 `docs-check`의 입력이다.

```json
{
  "paths": [
    "README.md",
    "AGENTS.md",
    "docs",
    "phases/{작업명}"
  ],
  "skipDirs": [
    ".git",
    "build",
    "node_modules",
    "__pycache__"
  ],
  "skipSuffixes": [
    ".class",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".json",
    ".png",
    ".webp"
  ],
  "required": [
    {
      "name": "<phase 핵심 문서 마커>",
      "paths": ["<이 규칙에만 적용할 선택 경로>"],
      "pattern": "<현재 phase 완료 후 반드시 문서에 남아야 하는 정규식>"
    }
  ],
  "finalRequired": [
    {
      "name": "<phase 최종 완료 후에만 필요한 마커>",
      "paths": ["<이 규칙에만 적용할 선택 경로>"],
      "pattern": "<마지막 step 이후 반드시 문서에 남아야 하는 정규식>"
    }
  ],
  "forbidden": [
    {
      "name": "<범위 밖 기능 또는 폐기된 계약>",
      "paths": ["<이 규칙에만 적용할 선택 경로>"],
      "pattern": "<현재 phase 완료 후 문서에 남으면 안 되는 정규식>"
    }
  ]
}
```

작성 규칙:

- `paths`는 현재 phase에서 문서 계약으로 검증할 경로만 넣는다.
- 각 `required`, `finalRequired`, `forbidden` rule은 선택적으로 자체 `paths`를 가질 수 있다. rule-level `paths`가 있으면 그 경로만 검사하고, 없으면 top-level `paths`를 검사한다.
- 프로젝트별 skill 파일은 기본 검사 경로에 넣지 않는다. skill의 정성 규칙 자체가 required marker를 만족시켜 문서 누락을 가릴 수 있기 때문이다.
- `required`에는 phase 진행 중에도 유지되어야 하는 API, UX, 환경변수, 공유 방식 같은 핵심 계약을 넣는다.
- `finalRequired`에는 마지막 step 이후에만 충족 가능한 QA 결과, 최종 문서 마커, 릴리스 기록 같은 계약을 넣는다.
- `forbidden`에는 폐기된 API 경로, 공개하면 안 되는 파라미터, 금지된 MVP 범위, 오래된 데모 흐름 같은 회귀 신호를 넣는다.
- regex로 안정적으로 검출할 수 있고 실패 시 바로 고칠 수 있는 항목만 둔다.
- 실행 로그, 이미지, 바이너리 파일이 정합성 검사를 오염시키지 않도록 `skipDirs`와 `skipSuffixes`를 채운다.
- 중간 step에서 아직 미래 step 문서가 없다는 이유로 실패하지 않도록 final 완료 기준에 맞는 규칙은 `finalRequired`에 둔다.
- phase에 문서 계약이 거의 없더라도 빈 파일을 생략하지 말고, `required`, `finalRequired`, `forbidden`을 빈 배열로 둔 최소 파일을 생성한다.

### `phases/{작업명}/step{N}.md`

단계마다 파일을 하나씩 생성한다:

```markdown
# 단계 {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/COMMANDS.md`
- {이전 단계에서 생성되거나 수정된 파일 경로}

이전 단계에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

{구체적인 구현 지시, 경로, 시그니처, 핵심 규칙을 작성한다.}

## 인수 기준

```bash
python scripts/checks.py --stage manual
```

`manual` stage는 step-local 검증이며 `docs-check`를 실행하지 않는다. 문서 정합성 검증은 마지막 step 이후 `python scripts/checks.py --stage final`에서 한 번 수행한다.

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md의 디렉터리 구조를 따르는가?
   - ADR의 기술 스택을 벗어나지 않았는가?
   - AGENTS.md의 CRITICAL 규칙을 위반하지 않았는가?
   - COMMANDS.md의 검증 명령을 실행했는가?
3. 결과에 따라 `phases/{작업명}/index.json`의 해당 단계를 업데이트한다:
   - 성공 -> `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 -> `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 -> `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

검증 또는 리뷰가 통과하지 못하면 `issues/{작업명}/issue-N.md`에 재현 명령, 핵심 에러, 수정 방향을 기록하고 fix step을 추가한다.

## 금지사항

- {구체적인 금지사항을 `"X를 하지 마라. 이유: Y."` 형식으로 작성한다}
- 기존 테스트를 깨뜨리지 마라
```

## 실행

페이즈 실행 명령:

```bash
python scripts/execute.py {작업명}
python scripts/execute.py {작업명} --push
python scripts/execute.py {작업명} --next-step-only
python scripts/autopilot.py {작업명} --max-review-fixes 2  # phase 전체 구현 시 권장
python scripts/autopilot.py {작업명} --dry-run --max-steps 1
```

`scripts/execute.py`는 phase index를 `scripts/task_schema.py`로 먼저 검증한 뒤
현재 선택된 task branch를 확인하고, `AGENTS.md`·phase·관련 문서의 직접 읽기 경로 검증, 현재 step의
objective/acceptance criteria/hard constraints와 완료된 단계의
`summary` context 전달, 재시도 피드백, 코드 변경과 메타데이터의 2단계 커밋,
completed 보고 후 인수 기준 재검증, 타임스탬프 기록, 선택적 push를 처리한다.
문서 본문은 prompt에 첨부하지 않고 Codex가 저장소에서 직접 읽는다.
`.codex/project-profile.json`의 비어 있지 않은 `guardrailDocs`는 문서 본문이
아닌 경로 선택 목록이며, 누락·판독 불가 경로는 Codex 호출 전에 진단한다. 기본
실행은 Codex 승인과 sandbox를 유지하며, 필요한 경우에만 `--unsafe`를 명시한다.
`scripts/execute.py`는 `--step` 또는 `--next-step-only`가 아닌 전체 phase 실행에서 모든 pending step이 완료되면 `python scripts/checks.py --stage final`을 실행한다.

`scripts/autopilot.py`는 clean primary checkout에서 base remote ref/SHA를 확인하고, 다음 pending step을 `codex/{phase}-step{N}-{name}` 브랜치의 Harness-owned task worktree에서 실행해 Draft PR을 만든다. `--base`를 생략하면 origin HEAD를 사용하고 실패 시 `main`으로 fallback한다. step 인수 기준, diff check, scope rule scan, Codex read-only review, 원격 PR checks가 통과하면 ready 전환 후 squash merge한다. 실패하면 marker·task worktree·PR 코멘트·GitHub Issue·`issues/{phase}/issue-N.md`를 남기고 같은 PR 브랜치에서 제한 횟수만큼 자동 수정과 재리뷰를 수행한다. 재시도 후에도 실패하면 PR과 Issue를 열어둔 채 중단한다.
`scripts/autopilot.py`도 모든 pending step이 사라진 뒤 `python scripts/checks.py --stage final`로 phase-local `docs-checks.json`을 한 번 검증한다.

phase별 범위 규칙이 필요하면 `phases/{작업명}/scope-rules.json`에 `extraForbidden` 또는 `allowedScopeMessages`를 추가한다. 전역 규칙은 `.codex/scope-rules.json`에 둔다. 템플릿 스크립트에 제품별 금지 키워드를 추가하지 않는다.

복구가 필요하면 `phases/{작업명}/index.json`에서 실패 또는 blocked 상태의 단계를 다시 `pending`으로 바꾸고, `error_message` 또는 `blocked_reason`을 제거한 뒤 원인을 해결하고 페이즈를 다시 실행한다. v1/v2 index의 validation 오류는 path/reason과 함께 Codex 호출 전에 중단되며, 기존 phase 파일은 자동 migration하지 않는다.

### Task worktree 실행 경계

`autopilot.py`가 구현·검증·review·PR 준비를 task별 독립 worktree에서 수행할 때는
`docs/WORKTREE_LIFECYCLE.md`와 ADR-0004를 먼저 읽는다. `scripts/worktree.py`가
Git administrative directory의 `harness-worktree.json` marker에
`owner=codex-harness`, `taskId`, phase, branch, 절대 path, `baseRef`, `baseSha`와
상태·진단을 atomic하게 기록한다. marker 없는 path/branch, owner 불일치, stale
administrative entry는 소유권을 추측하지 않고 보존한다.

primary checkout은 branch switch/commit/stage 대상이 아니다. base sync와 PR merge는
`.codex/autopilot.lock` 아래 동시성 1로 직렬화하고, v1 `steps[]`·v2 `tasks[]`는
기존 list-order를 그대로 따른다. `error`, `blocked`, `interrupted` task는 marker와
checkout을 남겨 같은 task를 resume하며, `merged`·clean·expected HEAD·active entry·
Harness owner를 모두 확인한 경우에만 force 없는 safe cleanup을 수행한다. DAG,
ready-set, parallelism과 사용자 worktree/branch 자동 삭제·prune은 이 단계에 넣지 않는다.
