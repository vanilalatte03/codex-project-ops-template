# Harness v2 릴리스 평가 (#23)

## 판정

2026-09-30 기준 **Harness v2 릴리스 gate 통과**. DOCS·CODE 모델 실행은
양쪽 variant에서 같은 fixture로 로컬 acceptance를 통과했고, V1·SAFETY 계약은
측정 3/3회 통과했다. 보관된 네 출력의 CI 재검증과 자체 review, 전체 로컬 검증,
Ubuntu/macOS/Windows CI를 확인했다. 버전은 `2026.09.30`이다. 담당 owner는 #23이다.

## 조건과 원자료

- v1 base: `a945f5bc9a64c40e97dcee18de91c4f59b39c7cb`; v2 base:
  `bcfadc383f0b1a599bca7a34b0eba73482d8cc41`.
- DOCS fixture SHA-256: `9d48d0b2b2499a854ec90da950a699ff23a31eca45bb602c582fac8be9037bd0`.
  CODE fixture SHA-256: `a6ce6777939244b9815989902fb94c6bda8e7bd73a4b924ace38d96fa632bcd6`.
- Windows 11, Python 3.12.13, Codex CLI 0.146.0, `gpt-5.6-luna`, effort `low`,
  `workspace-write`, approval `never`, retry 상한 3, 기존 로컬 CLI cache.
  각 실행은 임시 checkout에서 concurrency 1로 수행했다. `setupIncluded=false`.
- [eval-results](eval-results/)에 실패 및 탐색 실행을 포함한 raw JSON을 보존한다.
  `*-reviewed-1.json` 네 건은 허용된 합성 출력 파일을 보관하며
  `scripts/tests/test_eval_release_artifacts.py`가 CI에서 다시 실행한다.
  전체 prompt, credential, private thread 원문은 저장하지 않는다.
- 재현: `uv run --with pytest python -B scripts/eval_release.py --variant v2
  --scenario docs --repetition 1 --execute --output <result.json>`.
  계약 반복은 `scripts/eval_release_contracts.py`로 실행한다.

## 대표 시나리오 결과

DOCS·CODE의 비교 대상 측정은 각 variant·시나리오에서 1회다. 사전 탐색 실행
(`*-ast-1.json`)은 측정과 별도로 남겼다. 각 모델 실행이 약 100초이며 고정된
CLI 지원 모델 확인과 출력 보존을 위한 재실행에도 호출 비용이 들었으므로,
`EVALS.md`가 허용한 비용 사유에 따라 warm-up 1회 + 측정 3회에서 줄였다.
따라서 이 네 표본의 p95·성능 개선은 주장하지 않는다.

| 시나리오 | v1 | v2 | 근거 |
| --- | --- | --- | --- |
| EVAL-DOCS | 로컬 1/1, 101.782초, 재시도 1 | 로컬 1/1, 101.906초, 재시도 1 | 같은 `docs/STATUS.md` 출력, scope·acceptance 통과 |
| EVAL-CODE | 로컬 1/1, 104.391초, 재시도 1 | 로컬 1/1, 110.000초, 재시도 1 | 버그 수정과 회귀 테스트 출력, scope·acceptance 통과 |
| EVAL-V1 | 계약 3/3 | 계약 3/3 | 기존 `steps[]` 순서 `[0,1]`, terminal `completed` |
| EVAL-SAFETY | 계약 3/3 | 계약 3/3 | 위험 Git 명령을 pre-tool-use에서 `block`/`deny` |
| EVAL-RESUME | unsupported | 계약 3/3 | run state, 동일 worktree 재개, merge idempotency 테스트 |
| EVAL-DEPS | unsupported | 계약 3/3 | DAG 및 병렬 branch reconcile 테스트 |

계약 시나리오는 각각 warm-up `run0`과 측정 `run1`~`run3`을 보관했다.
RESUME은 지정 테스트 12개, DEPS는 8개가 각 반복에서 통과했다. V1·SAFETY의
계약 실행은 Codex 모델 호출이 없는 격리 replay이며, task PR·CI의 대체물이
아니다. v1의 RESUME·DEPS는 분모에서 제외한다.

DOCS·CODE의 **로컬** 성공률은 v1 2/2, v2 2/2이고 first-pass는 양쪽 0/2다.
각 실행의 구현 재시도 1회, review fix 0회, 사람 개입 0회다. 측정 직후 저장한
raw record의 `success=false`는 당시 PR review·CI가 아직 없었다는 시점 상태다.
출력 파일을 동일 PR에 보관하고 CI에서 다시 실행한 뒤 자체 review를 적용한 최종
판정 성공률은 v1 2/2, v2 2/2이고 first-pass는 양쪽 0/2다. 사용량이 runner의
commit-safe 출력에 없어 token은
0이 아닌 `null`로 기록했다. wall time의 시나리오별 단일 측정값을 median/p95로
일반화하지 않는다. 이전 [EVALS.md](EVALS.md)의 prompt 구성 proxy는 UTF-8
byte 86.03% 감소를 보여 주지만 실제 token·작업 성능 개선의 증거는 아니다.
재시도와 사람 개입은 v1과 같아 운영 지표 유지 근거로만 사용한다.

초기 `v1-docs-1.json`은 CLI 미지원 모델 선택으로 실패했고,
`v1-compat-1.json`은 평가 스크립트 import 경로 오류로 실패했다. 두 기록을
보존했으며 고정 비교 조건 확정 전 설정 실패로 분리했다. Codex CLI의 모델
cache 갱신·MCP 종료 경고는 v1 runner 출력에 남았지만 해당 실행은 acceptance를
통과했다. 이 경고를 제품 코드 실패로 집계하지 않는다.

## 릴리스 gate

| 항목 | 현재 증거 | 상태 |
| --- | --- | --- |
| hard: V1·SAFETY | 양쪽 측정 3/3 계약 통과 | 충족 |
| hard: unit test | `uv run --with pytest python -m pytest -q scripts`: 298 passed | 충족 |
| hard: doctor·upgrade·docs-check | doctor, upgrade 테스트 4개, docs-check 통과 | 충족 |
| hard: Ubuntu/macOS/Windows CI | 평가 출력 포함 `d01b95e`의 [CI run](https://github.com/vanilalatte03/codex-project-ops-template/actions/runs/36715289860) 3개 job 통과 | 충족 |
| quality | 최종 성공률 2/2 동률, first-pass 0/2 동률 | 충족 |
| efficiency | 재시도 2회/variant, 사람 개입 0회/variant 유지 | 약한 유지 근거; 성능 향상 미주장 |

`upgrade.py --from . --dry-run`은 동일 체크아웃을 source와 instance로 주면
exit 1 (`--from must point to a different checkout than this instance`)이다.
Step 10 인수 기준은 별도 checkout dry-run과 upgrade 테스트로 바로잡았다.
기존 별도 checkout smoke 실행은 exit 0이고 파일 변경이 없었다. 자체 review에서
아키텍처·ADR·scope·v1 원형·worktree 경계를 확인했다. 평가 스크립트는 임시
checkout만 만들고 기존 실행 모듈의 동작을 바꾸지 않는다. 세 운영체제 CI는
평가 출력과 bytecode 캐시 수정이 포함된 고정 SHA에서 통과했다. 최종 버전·상태
commit의 CI도 병합 전에 다시 확인한다. rollback은 PR 병합 전에는 병합 중단,
병합 뒤에는 `2026.09.30` 버전 commit의 revert 및 기존
`2026.09.04.2` 사용으로 판단한다.
