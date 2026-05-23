# Phases

Harness phase 파일은 프로젝트별 MVP 작업을 작은 step으로 나눠 실행하기 위한 템플릿입니다.

새 phase는 아래 구조로 만듭니다.

```text
phases/{phase-name}/
  README.md
  index.json
  step0.md
  step1.md
```

`README.md`에는 phase 목표, 작업 범위, 제외 범위, step PR 리뷰 원칙, 완료 기준,
검증 명령을 적습니다. 중간 step PR 리뷰는 해당 `stepN.md`와 phase `README.md`를
우선 계약으로 삼고, 미래 step에 배정된 기능이 아직 없다는 이유만으로 blocker 처리하지
않습니다.

`index.json`에는 step 목록과 상태를 기록합니다. `scripts/execute.py`와
`scripts/autopilot.py`가 `pending`, `completed`, `error`, `blocked` 상태와
타임스탬프를 갱신합니다.
