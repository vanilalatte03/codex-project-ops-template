# Phase task schema

이 문서는 `phases/{phase}/index.json`의 task 계약과 v1/v2 호환 규칙의
source of truth다. 현재 실행기는 모든 입력을 검증한 뒤 배열 순서대로 한 번에
하나의 task를 처리한다.

## 형식 판별

| 형식 | 판별 기준 | 저장 컨테이너 |
| --- | --- | --- |
| v1 | `steps`가 있고 `tasks`가 없음. 기존 파일에는 `schemaVersion`이 없어도 된다 | `steps[]` |
| v2 | `schemaVersion: 2`와 `tasks` | `tasks[]` |

v1을 명시적으로 구분하려면 `schemaVersion: 1`을 사용할 수 있다. `schemaVersion`이
없고 `tasks`만 있는 입력도 v2로 읽을 수 있지만, 새 파일은 `schemaVersion: 2`를
기록한다. `steps`와 `tasks`를 함께 두거나 marker와 컨테이너가 불일치하면
거부한다.

## 공통 상태

v1과 v2는 같은 상태 집합을 사용한다.

`pending` · `completed` · `error` · `blocked`

실행기가 기록하는 `summary`, `error_message`, `blocked_reason`과 상태별 timestamp
필드는 lifecycle 필드로 보존된다. `project`, `phase`, `created_at`, `completed_at`는
기존 phase 기록과 함께 유지한다.

## v1 계약

기존 v1 입력의 최소 형태는 다음과 같다.

```json
{
  "project": "<프로젝트명>",
  "phase": "0-example",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" }
  ]
}
```

`step`은 0 이상 정수, `name`은 비어 있지 않은 문자열, `status`는 공통 상태 중
하나여야 한다. 기존 v1 phase 파일에는 v2 필드를 추측해 추가하지 않으며,
`phases/0-example/index.json`은 호환 fixture로 유지한다.

## v2 계약

v2 task는 다음 필드를 사용한다.

| 필드 | 구분 | 타입과 규칙 |
| --- | --- | --- |
| `id` | 필수 | 비어 있지 않은 문자열. phase 안에서 유일해야 한다 |
| `objective` | 필수 | 비어 있지 않은 결과 목표 문자열 |
| `status` | 필수 | `pending`, `completed`, `error`, `blocked` 중 하나 |
| `dependsOn` | 선택 | task `id` 문자열의 배열. 생략하면 검증된 메모리 view에서 `[]`로 본다 |
| `issue` | 선택 | 양의 정수인 GitHub Issue 번호 |
| `risk` | 선택 | 비어 있지 않은 위험도 문자열 |

실행 기록에 필요한 lifecycle 필드(`summary`, `error_message`, `blocked_reason`,
`started_at`, `completed_at`, `failed_at`, `blocked_at`)도 선택적으로 보존할 수
있다. v2 task에 v1 전용 `step` 또는 `name`, 정의되지 않은 임의 필드를 넣으면
거부한다.

예시는 [`phases/0-example-v2/index.json`](../phases/0-example-v2/index.json)에
있다.

## 정규화와 실행 경계

`scripts/task_schema.py`의 validator가 반환하는 메모리 view는 두 형식을 공통으로
다룬다.

- v1 task는 기존 `step`/`name`을 그대로 사용한다.
- v2 task는 배열 위치를 `step`, `id`를 `name`으로 임시 노출한다.
- 이 alias는 현재 직렬 executor가 기존 companion `stepN.md`와 list-order를
  사용할 수 있게 하는 메모리 값이며 v2 JSON에 저장하지 않는다.
- `dependsOn`은 중복·self·존재하지 않는 task id를 거부하는 참조 검증만 한다.
  ready set, cycle 처리, DAG 스케줄링, 병렬 실행은 후속 #22 범위다.

읽기와 쓰기 사이에 형식을 바꾸지 않는다. 정규화 객체의 `to_payload()`는 원래
`steps[]` 또는 `tasks[]` 컨테이너와 필드 생략을 보존하며, v1 입력에 synthetic v2
필드를 추가하지 않는다.

## 오류와 실행 전 검증

다음 오류는 Codex subprocess 또는 GitHub 인증보다 먼저 발생해야 한다.

- 중복 `id`
- `dependsOn`의 누락된 task id
- 자기 자신을 가리키는 dependency
- 필수 필드 누락, 잘못된 타입, 공통 상태 밖의 `status`

`TaskSchemaError`는 파일 경로와 필드 경로를 함께 출력한다. 예를 들어
`phases/demo/index.json tasks[1].dependsOn[0]`처럼 문제 위치를 식별할 수 있어야
하며, 여러 오류가 있으면 한 번에 모두 보고한다. `execute.py`와 `autopilot.py`는
이 검증 실패를 성공이나 재시도로 바꾸지 않는다.

## migration 규칙

자동 migration은 하지 않는다. 기존 `index.json`, `stepN.md`, phase README를
읽었다는 이유만으로 v1 파일을 v2로 덮어쓰거나, v2 alias를 파일에 기록해서는 안
된다. v1을 v2로 바꾸려는 프로젝트는 별도의 명시적 opt-in 작업으로 다음을
수행한다.

1. 원본 phase와 index를 백업하고 변경 대상과 task id 매핑을 검토한다.
2. dry-run에서 `id`, `objective`, `dependsOn`, `issue`, `risk`를 사람이 확정한다.
3. 생성한 v2 index를 validator, companion step 문서, 전체 테스트로 확인한다.
4. 사용자가 승인한 뒤에만 별도 commit으로 적용하고, 실패 시 원본을 복구한다.

이번 schema 단계는 migration 명령이나 DAG scheduler를 추가하지 않는다. 원본을
보존한 채 읽기 호환성과 검증만 제공한다.
