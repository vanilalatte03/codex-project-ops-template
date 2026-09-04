# ADR-0003: Outcome task schema v2와 v1 호환

## Status

Accepted

## Context

기존 Harness는 phase index의 `steps[]`를 배열 순서대로 직렬 실행한다. 이후
issue-driven outcome task에는 결과 목표, dependency reference, GitHub Issue와
위험도 메타데이터가 필요하지만, 이미 존재하는 v1 phase와 실행 기록을 자동으로
변환하거나 깨뜨릴 수는 없다.

## Decision

- v1 `steps[]`와 v2 `schemaVersion: 2` + `tasks[]`를 함께 지원한다.
- v2 task의 필수 필드는 `id`, `objective`, `status`이고 `dependsOn`, `issue`,
  `risk`는 선택 필드다. v1과 v2의 status 집합은
  `pending`, `completed`, `error`, `blocked`로 공유한다.
- `scripts/task_schema.py`를 두 실행 경로와 doctor가 공유한다. 중복 id,
  self/unknown dependency, 필수 필드·타입·status 오류는 Codex 호출 전에
  path/reason을 포함해 거부한다.
- v2 입력은 메모리에서만 기존 serial executor가 이해하는 `step`/`name` alias를
  제공한다. 저장 시 원래 컨테이너와 필드 형태를 보존한다.
- `dependsOn`은 이번 결정에서 reference validation만 한다. ready set, cycle
  처리, DAG scheduling과 parallelism은 후속 #22에서 별도 결정한다.
- v1→v2 migration은 자동으로 하지 않는다. 변환은 backup, dry-run, validator,
  사용자 승인과 별도 commit을 포함한 명시적 opt-in 작업이어야 한다.

## Consequences

- 기존 v1 phase는 `phases/0-example/index.json`과 같은 형태로 계속 실행된다.
- 새 v2 phase는 outcome metadata를 기록하면서도 현재 `stepN.md`와 직렬 실행을
  재사용할 수 있다.
- v2 dependency graph의 실행 가능 집합이나 cycle은 아직 계산하지 않으므로,
  이를 요구하는 구현은 #22 범위까지 기다려야 한다.
- schema 변경 시 `docs/TASK_SCHEMA.md`, 예제, doctor와 두 실행 경로의 테스트를
  함께 갱신해야 한다.
