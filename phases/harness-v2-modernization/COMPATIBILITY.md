# v1 호환성과 rollback 계약

계약 섹션: v1 보존 기준, fallback 원칙, rollback trigger, rollback 절차

## v1 보존 기준

- 기존 phase `index.json`의 `project`, `phase`, `steps[]` 구조와 각 step의 `step`,
  `name`, `status` 필드를 schema v1로 간주한다.
- v1의 유효 status인 `pending`, `completed`, `error`, `blocked`와 현재 timestamp,
  `summary`, `error_message`, `blocked_reason` 의미를 유지한다.
- `phases/0-example/`을 변경 전 v1 호환 fixture로 유지한다. v2 필드를 강제로
  추가하거나 자동 덮어쓰기하지 않는다.
- v1 phase는 기존과 같은 순서로 실행되고 `execute.py`, `autopilot.py`, doctor,
  docs-check를 통과해야 한다.
- 새 v2 필드는 additive여야 한다. v1 입력에 없는 값을 추측해 파일에 쓰지 않으며,
  migration은 명시적 opt-in과 dry-run을 제공하기 전까지 수행하지 않는다.
- v2 reader가 기록한 상태를 v1 fallback이 읽지 못할 가능성이 있으면 원본을
  보존하고 변환 전 backup·검증·복구 절차를 제공한다.

## task schema v2 (#16)

- v1은 기존 `steps[]`와 `step`, `name`, `status`를 그대로 읽는다. 현재 fixture인
  `phases/0-example/index.json`은 v1 보존 검증의 기준이며 v2 필드를 자동으로
  추가하지 않는다.
- v2는 `schemaVersion: 2`, `tasks[]`와 각 task의 필수 `id`, `objective`, `status`,
  선택 `dependsOn`, `issue`, `risk`를 사용한다. 공통 status는 v1과 동일하게
  `pending`, `completed`, `error`, `blocked`다.
- `scripts/task_schema.py`가 두 형식을 구분·검증한다. 중복 id, self/unknown
  dependency, 필수 필드·타입·status 오류는 파일 및 필드 경로와 reason을 포함해
  Codex와 GitHub 인증 전에 거부한다.
- v2 task의 배열 위치와 id에서 파생한 `step`/`name`은 현재 serial executor를
  위한 메모리 alias일 뿐이다. 저장할 때는 원래 `tasks[]` 형식과 필드 생략을
  보존한다.
- `dependsOn`은 이 단계에서 reference validation만 수행한다. ready set, cycle
  처리, DAG scheduling과 parallelism은 #22의 범위이며 #16에서 선행 구현하지
  않는다.
- v1→v2 변환은 자동으로 실행하지 않는다. 변환이 필요한 프로젝트는 원본 백업,
  dry-run 매핑 검토, validator와 companion 문서 검증, 사용자 승인, 별도 commit을
  포함한 명시적 opt-in 절차를 사용한다.

## fallback 원칙

- SDK 또는 native review가 설치되지 않았거나 capability 검증, 인증, sandbox,
  timeout, output parsing 중 하나라도 실패하면 기존 `codex exec`와 read-only review
  경로를 사용한다.
- fallback은 local checks, diff check, scope scan, CI, read-only 불변조건을
  생략하지 않는다.
- fallback 여부와 사유는 실행 결과에 남기되 credential이나 prompt 원문은 남기지
  않는다.
- 실패를 성공으로 바꾸는 무조건 retry는 허용하지 않는다. retry 상한 뒤에는
  `error` 또는 `blocked`로 멈춘다.

## rollback trigger

다음 중 하나면 v2 경로의 배포·기본 전환을 중단하고 마지막 검증된 v1 경로로
rollback한다.

- v1 fixture를 읽거나 기존 terminal status를 보존하지 못함
- scope, read-only review, destructive-command 차단, local/CI gate를 우회함
- task/PR/merge 완료 action을 중복 실행하거나 사용자 worktree·branch를 변경함
- 손상된 state를 진단하지 못하거나 credential·민감정보를 기록함
- `EVALS.md` hard gate 또는 세 운영체제 CI가 실패함

## rollback 절차

1. 새 task 시작과 merge를 중단하고 진행 중 task의 issue, branch, worktree, state를
   보존한다.
2. 실패한 v2 adapter 또는 scheduler를 feature flag/config에서 비활성화한다.
3. `TEMPLATE_VERSION`과 CHANGELOG에서 마지막 검증된 v1 또는 직전 호환 버전을
   식별하고 템플릿 소유 파일을 `scripts/upgrade.py --from <checkout> --dry-run`으로
   먼저 비교한다.
4. 사용자 소유 파일과 v1 phase/index를 덮어쓰지 않는지 확인한 뒤 복구를 적용한다.
5. v1 fixture, 전체 unit test, template doctor, upgrade dry-run, 세 운영체제 CI를
   다시 통과시킨다.
6. 원인, 영향 범위, 보존한 state, 수동 복구 항목과 재도입 조건을 Issue/PR에 남긴다.

rollback은 `git reset --hard`, force push, 사용자 worktree 자동 삭제로 수행하지
않는다. 되돌릴 수 없는 schema migration이나 destructive cleanup은 이 phase의
허용 범위가 아니다.
