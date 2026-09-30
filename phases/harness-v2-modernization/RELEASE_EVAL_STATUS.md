# Harness v2 릴리스 평가 진행 기록 (#23)

## 판정

2026-09-30 기준 **릴리스 보류**. 이 문서는 확인된 검증과 아직 없는 평가 자료를
구분한다. `EVALS.md`의 v1/v2 동일 작업 반복 실행, hard/quality/efficiency
gate 판정, 현재 PR의 세 운영체제 CI가 끝나기 전에는 Step 10을 완료하거나
`TEMPLATE_VERSION`을 릴리스 버전으로 올리지 않는다. 담당 owner는 #23이다.

## 고정된 관찰 조건

- v2 base commit: `bcfadc383f0b1a599bca7a34b0eba73482d8cc41`
- v1 기준 commit: `a945f5bc9a64c40e97dcee18de91c4f59b39c7cb`
- v1 phase fixture: `phases/0-example/index.json`, SHA-256
  `AA8B5FF872FEC64BD83ED243378FBFF638282FE57625780E45CB5FA76B02125D`
- v2 phase fixture: `phases/0-example-v2/index.json`, SHA-256
  `7C104AB509777F5B59C375C0CC566014BE10CAEC2DA3593EB2C4FAFD6AFADD9D`
- 로컬 검증 환경: Windows, uv Python 3.12.13, pytest 9.1.1, Codex CLI 0.146.0.
  모델, effort, sandbox, approval policy, cache 상태는 실제 대표 작업을
  실행할 때 raw record에 고정해야 한다.

## 현재 검증 증거

| 항목 | 결과 | 재현 또는 증거 |
| --- | --- | --- |
| Harness 단위 테스트 | 285 passed | `uv run --with pytest python -m pytest scripts` |
| 템플릿 doctor | 통과 | `uv run --with pytest python scripts/doctor.py --template` |
| phase docs-check | 통과 | `uv run --with pytest python scripts/checks.py --docs-check-config phases/harness-v2-modernization/docs-checks.json --docs-check` |
| upgrade dry-run | 통과 | 서로 다른 체크아웃에서 `upgrade.main(['--from', <현재 템플릿>, '--dry-run'], instance_root=<기존 main>)` 실행, exit 0, 파일 변경 없음 |
| 선행 #22의 CI | Ubuntu, macOS, Windows 통과 | [PR #36](https://github.com/vanilalatte03/codex-project-ops-template/pull/36)과 [develop run](https://github.com/vanilalatte03/codex-project-ops-template/actions/runs/36677819824) |

기존 Step 10의 `python scripts/upgrade.py --from . --dry-run`은 exit 1
(`--from must point to a different checkout than this instance`)로 재현됐다.
이는 upgrade 자체의 실패가 아니라 잘못된 인수 기준이다. Step 10에는 자동
dry-run 테스트와 별도 체크아웃 smoke 검증을 명시했다.

## 남은 대표 평가

아래 수치는 **미측정**이다. 단위 테스트 통과나 과거 CI를 대표 작업의 성공률,
first-pass, 성능 개선으로 환산하지 않는다.

| 시나리오 | v1 | v2 | 남은 자료 |
| --- | --- | --- | --- |
| EVAL-DOCS | 미실행 | 미실행 | 고정 입력·기대 diff, warm-up 1회와 측정 3회 raw record |
| EVAL-CODE | 미실행 | 미실행 | 동일 동작 수정·회귀 테스트 fixture와 raw record |
| EVAL-V1 | 미실행 | 미실행 | 원본 v1 phase의 동일 순서·terminal status 반복 증거 |
| EVAL-SAFETY | 미실행 | 미실행 | 금지 범위·read-only 변경 차단 반복 증거 |
| EVAL-RESUME | unsupported | 미실행 | 중단·재개와 중복 action 방지 raw record |
| EVAL-DEPS | unsupported | 미실행 | 독립 2개·의존 1개, 자원 충돌·직렬 merge raw record |

각 raw record에는 `EVALS.md`의 필수 필드 외에 fixture hash, 기대 결과,
`setupIncluded`, retry 상한, cache 상태, 시작·종료 근거를 넣는다. v1의
unsupported 실행은 분모에서 제외하고, 실패 실행은 삭제하지 않는다.
비용이나 환경 제약으로 3회를 채우지 못하면 횟수와 사유를 남긴다.

## 완료 절차

1. 모든 시나리오의 fixture와 입력 hash를 확정한 뒤 v1/v2에 동일 gate를 적용한다.
2. raw record로 성공률, first-pass, retry, median/p95 wall time, 사람 개입,
   가능한 token을 계산한다. token이 없으면 `null`과 사유를 기록한다.
3. EVAL-V1·EVAL-SAFETY 100%와 v2 품질 비회귀를 확인한다.
4. 이 PR의 Ubuntu/macOS/Windows CI와 자체 review를 확인한다.
5. 모든 gate가 통과한 경우에만 CHANGELOG, 버전 마커, Step 10·phase 상태와
   최종 판정을 함께 갱신한다. 미달이면 #23에 blocker, owner, rollback 판단을 남긴다.
