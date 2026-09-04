# Phases

Harness phase 파일은 프로젝트별 MVP 작업을 작은 step으로 나눠 실행하기 위한 템플릿입니다.

형식이 채워진 참고용 예시는 `0-example/`(v1)와 `0-example-v2/`(outcome v2)에
있습니다. 실행 대상이 아니라 형식 레퍼런스이며, `python scripts/doctor.py
--template`이 두 예시의 schema와 companion 문서를 검증합니다. 전체 계약은
[`docs/TASK_SCHEMA.md`](../docs/TASK_SCHEMA.md)에 있습니다. 실제 phase를 만들 때
적절한 예시를 복사해 시작해도 됩니다.

새 phase는 아래 구조로 만듭니다.

```text
phases/{phase-name}/
  README.md
  index.json
  docs-checks.json
  scope-rules.json  # 필요할 때만 추가
  step0.md
  step1.md
```

`README.md`에는 phase 목표, 작업 범위, 제외 범위, step PR 리뷰 원칙, 완료 기준,
검증 명령을 적습니다. 중간 step PR 리뷰는 해당 `stepN.md`와 phase `README.md`를
우선 계약으로 삼고, 미래 step에 배정된 기능이 아직 없다는 이유만으로 blocker 처리하지
않습니다.

`index.json`에는 v1 `steps[]` 또는 v2 `tasks[]` 목록과 상태를 기록합니다.
`scripts/task_schema.py`가 두 형식을 구분하고 path/reason validation을 먼저
수행하며, `scripts/execute.py`와 `scripts/autopilot.py`가
`pending`, `completed`, `error`, `blocked` 상태와 timestamp를 갱신합니다. v2의
`dependsOn`은 현재 list-order 직렬 실행을 바꾸지 않으며, 기존 index를 자동
migration하지 않습니다.

`docs-checks.json`에는 phase 최종 완료 전에 자동으로 확인할 문서 정합성 규칙을
적습니다. `manual` stage에서는 실행하지 않고, 모든 pending step이 끝난 뒤
`python scripts/checks.py --stage final`에서 한 번 실행합니다.

`scope-rules.json`은 선택 파일입니다. phase 안에서만 추가로 금지하거나, 전역
`.codex/scope-rules.json`의 메시지를 특정 step에서 허용해야 할 때 작성합니다.
