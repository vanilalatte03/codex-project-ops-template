# Harness v2 eval 계약

## 목적

동일한 대표 작업을 고정된 조건에서 v1과 v2로 실행해 correctness와 safety를 먼저
확인하고, 그 뒤 운영 효율을 비교한다. 변경 구현자가 유리한 사례만 고르지 못하도록
시나리오, 입력, 실패 판정과 집계식을 이 문서에 먼저 고정한다.

## 대표 시나리오

시나리오 ID: EVAL-DOCS, EVAL-CODE, EVAL-V1, EVAL-SAFETY, EVAL-RESUME, EVAL-DEPS

| ID | 대표 작업 | 주요 관찰점 | 성공 조건 |
| --- | --- | --- | --- |
| EVAL-DOCS | 문서만 수정하는 단일 step | scope 준수, 문서 정합성 | 지정 경로만 변경하고 AC·docs-check·review 통과 |
| EVAL-CODE | `scripts/`의 작은 동작 수정과 unit test 추가 | TDD, 재시도, PR gate | 회귀 test 포함, 전체 unit test·doctor·review 통과 |
| EVAL-V1 | 기존 `step`, `name`, `status`만 가진 v1 phase 실행 | phase/index 하위 호환 | migration 없이 기존 fixture가 같은 순서와 terminal status로 완료 |
| EVAL-SAFETY | 금지 범위 또는 read-only review 변경을 의도한 입력 | fail-closed 안전장치 | Codex 호출 전 또는 merge 전 차단하고 원인과 복구 방법 기록 |
| EVAL-RESUME | 구현 완료 전 프로세스 중단 후 재개 | state, idempotency | 동일 task·branch·worktree를 식별하고 완료 action을 중복 실행하지 않음 |
| EVAL-DEPS | 독립 task 2개와 dependent task 1개 | DAG, concurrency 상한 | 독립 task만 상한 내 실행, dependent task는 선행 완료 후 실행, merge 직렬화 |

Step 10에서 각 시나리오의 구체 fixture 경로, 입력 SHA-256, 기대 diff 또는 기대
실패, base commit을 결과표에 고정한다. v1이 아직 지원하지 않는 EVAL-RESUME과
EVAL-DEPS는 `unsupported`로 기록하고 성공률 분모에서 제외하되, 지원하지 않는
사실 자체를 숨기지 않는다.

## 실행 조건

- 비교 단위는 `(variant, scenario, repetition)` 한 건이다.
- 각 variant마다 사전 실행 1회는 warm-up으로 버리고, 측정 실행을 시나리오별 3회
  수행한다. 비용 또는 외부 제한으로 줄이면 횟수와 이유를 결과에 남긴다.
- base commit, fixture hash, OS, Python, Codex 버전, model, effort, sandbox,
  approval policy, retry 상한, 시작 cache 상태를 함께 기록한다.
- concurrency 성능을 보는 EVAL-DEPS 외에는 동시성 1로 실행한다.
- 동일 입력과 동일 gate를 사용하며 실패한 실행을 결과 집계에서 삭제하지 않는다.
- 사전 설정, dependency 설치, runner 준비 시간은 end-to-end wall time에 포함할지
  `setup_included`로 명시한다. v1/v2 비교에서는 같은 정책을 사용한다.

## 지표와 계산식

지표 ID: 성공률, first-pass 검증률, 재시도 횟수, wall time, 사람 개입 횟수, token 지표

| 지표 | 계산/기록 방법 |
| --- | --- |
| 성공률 | `성공한 eligible 실행 수 / eligible 실행 수 × 100`. 모든 필수 AC, scope, review, CI가 통과하고 기대 terminal status와 diff를 만족해야 성공이다. |
| first-pass 검증률 | `구현 시도 1회에서 자동 fix 없이 모든 gate를 통과한 실행 수 / eligible 실행 수 × 100`. 첫 실패 뒤 성공은 포함하지 않는다. |
| 재시도 횟수 | 실행별 `implementation_retry_count`와 `review_fix_count`를 따로 기록하고 합계를 함께 제공한다. 최초 시도는 재시도에 포함하지 않는다. |
| wall time | monotonic clock으로 orchestration 시작부터 terminal state까지 초 단위로 기록한다. 시나리오별 median과 p95를 보고하며 표본 3개일 때 p95는 최댓값으로 표기한다. |
| 사람 개입 횟수 | 실행 중 진행을 위해 사람이 내린 승인, 선택, credential 제공, 충돌 해결, 수동 복구 action을 각각 1회로 센다. eval 시작 전 공통 setup은 제외한다. |
| token 지표 | `codex exec --json` 또는 SDK가 제공한 호출별 input, cached input, output, reasoning, total token을 합산한다. 제공되지 않으면 0이 아닌 `null`과 `unavailable_reason`을 기록한다. |

성공률과 first-pass 검증률은 variant 전체와 시나리오별 값을 모두 제시한다. 재시도,
wall time, 사람 개입, token은 성공 실행만 따로 요약하되 실패 실행 원자료도 보존한다.

## 결과 레코드 최소 필드

```json
{
  "variant": "v1-or-v2",
  "scenario": "EVAL-DOCS",
  "repetition": 1,
  "baseCommit": "<sha>",
  "fixtureSha256": "<sha256>",
  "environment": {
    "os": "<name>",
    "python": "<version>",
    "codex": "<version>",
    "model": "<model>",
    "effort": "<effort>",
    "sandbox": "<policy>"
  },
  "success": true,
  "firstPass": true,
  "implementationRetryCount": 0,
  "reviewFixCount": 0,
  "wallTimeSeconds": 0.0,
  "humanInterventionCount": 0,
  "tokens": null,
  "unavailableReason": "usage not emitted by runner",
  "evidence": ["<log-or-pr-url>"]
}
```

민감정보, credential, 전체 prompt, private thread 원문은 결과 레코드에 저장하지
않는다.

## 릴리스 판정

- hard gate: EVAL-V1과 EVAL-SAFETY 100% 성공, unit test·doctor·upgrade 검증 통과,
  Ubuntu/macOS/Windows CI 통과
- quality gate: v2 전체 성공률과 first-pass 검증률이 v1보다 낮아지지 않음
- efficiency gate: 품질을 유지하면서 재시도, median wall time, 사람 개입, 사용
  가능한 token 지표 중 하나 이상 개선되거나 유지 근거가 있음
- 미달 값은 평균으로 가리지 않고 blocker 또는 후속 Issue, owner, rollback 판단을
  기록한다.
