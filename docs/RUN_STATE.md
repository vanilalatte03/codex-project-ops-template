# Local run state 계약

## 목적

Harness가 중단된 task를 같은 issue, branch, worktree로 재식별하고, 이미 완료된
외부 action을 중복 실행하지 않도록 한다. 이 상태는 원격 telemetry나 dashboard가
아닌 로컬 운영 상태다.

## 위치와 식별자

- 일반 checkout은 Git administrative directory의 `.git/harness-runs/`에 저장한다.
- linked worktree는 `.git` 파일이 가리키는 Git administrative directory를 사용한다.
- 파일명은 task id의 SHA-256이므로 task id가 path로 해석되지 않는다.
- state는 phase, task, issue, branch, worktree, model, effort, attempt, 검증·리뷰
  상태와 EVAL 최소 metric을 기록한다. model 또는 token이 제공되지 않으면 `null`과
  `unavailableReason`을 사용하며 0으로 바꾸지 않는다.

## 상태 전이와 재개

`created -> running -> implemented -> reviewing -> ready -> merged`가 정상 흐름이다.
`error`, `blocked`, `interrupted`는 보존 상태이며 같은 immutable identity만
`running`으로 재개할 수 있다. 살아 있는 process가 가리키는 `running` state는
재사용하지 않고, stale process를 확인한 경우에만 `interrupted`로 reconcile한 뒤
재개한다. 손상된 JSON은 자동 덮어쓰지 않고 진단 오류로 남긴다.

## 원자성·idempotency

state write는 같은 directory의 temporary file, flush/fsync, `os.replace` 순서로
원자화한다. PR 생성과 merge 같은 완료 action은 fingerprint와 함께 기록한다. 같은
fingerprint 재기록은 no-op이며, 다른 fingerprint로의 중복 action은 fail-closed 한다.

## 민감정보 경계

prompt, response 본문, credential, password, authorization 값은 state API에 없으며,
diagnostic과 metric 사유의 key=value 형태 민감값은 기록 전에 redaction한다. runner
thread 식별자는 local resume state에만 둘 수 있고, 로그나 phase artifact에 쓰는
commit-safe record에서는 제외한다.
