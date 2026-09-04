# Phase: harness-v2-modernization

상위 Epic: [#12](https://github.com/vanilalatte03/codex-project-ops-template/issues/12)

## 목표

- 현재의 순차 `codex exec` 기반 Harness를 기존 안전장치와 v1 하위 호환성을
  보존하면서 issue-driven, isolated, resumable orchestration 구조로 현대화한다.
- GitHub Issue는 목표·우선순위·의존성·승인 상태, 이 디렉터리는 실행 계약과
  인수 기준, PR은 실제 변경과 검증 증거의 source of truth로 사용한다.

## 작업 범위

- Must-have: 기준선과 eval 지표, 최소 권한 실행 환경, progressive disclosure,
  outcome task schema v2와 v1 호환, 직렬 worktree 격리
- Must-have: SDK spike, runner adapter와 `codex exec` fallback, 재개 가능한 telemetry,
  위험도별 review, dependency DAG와 bounded concurrency, 최종 eval과 릴리스 gate
- Later: 릴리스 이후 문서·아키텍처 gardening loop는 #24에서 별도로 다룬다.

## 제외 범위

- 현재 step보다 뒤의 기능을 선행 구현하지 않는다.
- 검증되지 않은 SDK 또는 native review를 필수 경로로 만들지 않는다.
- 무제한 concurrency, 여러 PR 동시 merge, 사용자 worktree·branch 자동 삭제를
  허용하지 않는다.
- 제품 요구사항이나 ADR 결정을 자동으로 바꾸는 gardening을 릴리스 blocker로
  포함하지 않는다.

## 실행 순서

각 step은 표의 GitHub Issue 하나를 구현하며 바로 앞 step 완료를 선행 조건으로
삼는다. 한 번에 하나의 ready Issue만 진행하고 Issue 하나는 가능한 한 PR 하나로
완료한다.

실행 순서 ID: #13 -> #14 -> #15 -> #16 -> #17 -> #18 -> #19 -> #20 -> #21 -> #22 -> #23

| Step | Issue | Name | Range | 결과 |
| ---: | ---: | --- | --- | --- |
| 0 | #13 | baseline-and-metrics | Must-have | v1 기준선·eval·rollback 계약 |
| 1 | #14 | minimize-environment-inheritance | Must-have | 최소 권한 환경 변수 정책 |
| 2 | #15 | progressive-guardrails | Must-have | 경로 중심 prompt |
| 3 | #16 | task-schema-v2 | Must-have | outcome task schema와 v1 호환 |
| 4 | #17 | isolated-worktree | Must-have | 동시성 1의 task worktree |
| 5 | #18 | sdk-spike | Must-have | SDK GO/NO-GO ADR |
| 6 | #19 | runner-adapter | Must-have | 공통 runner와 exec fallback |
| 7 | #20 | resumable-telemetry | Must-have | 원자적 상태와 중단 재개 |
| 8 | #21 | risk-based-review | Must-have | native review fallback과 위험도 정책 |
| 9 | #22 | bounded-dag | Must-have | 검증된 DAG와 bounded concurrency |
| 10 | #23 | release-eval | Must-have | v1/v2 비교와 릴리스 판정 |

세부 목표와 금지사항은 각각의 `stepN.md`를 따른다. 기준선은
[`BASELINE.md`](BASELINE.md), eval 표본과 계산식은 [`EVALS.md`](EVALS.md), v1
보존 및 rollback 규칙은 [`COMPATIBILITY.md`](COMPATIBILITY.md)에 고정한다.

## Step PR 리뷰 원칙

- 각 step PR의 리뷰 기준은 현재 `stepN.md`의 작업, 인수 기준, 금지사항이다.
- 미래 step에 배정된 기능이 아직 없다는 사실은 현재 step의 blocker가 아니다.
- 현재 step이 미래 step 범위를 선행 구현하면 blocker로 본다.
- 리뷰 실패는 같은 PR 브랜치에서 수정하고
  `issues/harness-v2-modernization/issue-N.md`에 기록한다.
- correctness와 safety gate는 성능 지표보다 우선한다. 빠르거나 token이 적어도
  안전성 또는 v1 호환성이 회귀하면 merge하지 않는다.

## 완료 기준

- #13~#23이 순서대로 완료되고 각 Issue의 PR과 검증 증거가 남는다.
- `EVALS.md`의 동일 입력·동일 조건으로 v1과 v2를 비교한다.
- v1 phase/index fixture, upgrade, 세 운영체제 CI, unit test, doctor가 통과한다.
- correctness와 safety gate를 모두 통과하고, 품질을 유지하면서 최소 한 가지
  운영 지표가 개선되거나 유지 근거가 기록된다.
- 미달 지표는 blocker 또는 후속 Issue로 남기며, `COMPATIBILITY.md`의 rollback
  조건과 절차를 적용할 수 있다.

## 검증 명령

```powershell
python -m pytest scripts
python scripts/doctor.py --template
python scripts/checks.py --docs-check-config phases/harness-v2-modernization/docs-checks.json --docs-check
git diff --check
```

마지막 step에서는 위 명령에 더해 `python scripts/upgrade.py --from . --dry-run`과
세 운영체제 CI를 확인한다.
