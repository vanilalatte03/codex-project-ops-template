# 단계 7: resumable-telemetry (#20)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/EVALS.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/codex_common.py`
- `/scripts/tests/`

## 작업

- run, task, issue, thread, worktree, branch, model, effort, attempt, 검증과 review
  상태 및 상태 전이를 정의한다.
- state를 원자적으로 기록하고 중단 후 resume 또는 reconcile하며 stale process를
  식별한다.
- 완료 action의 idempotency를 보장하고 `EVALS.md` 최소 필드 중 제공 가능한 측정값을
  생성한다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. 상태 전이, atomic write 실패, 손상 state, stale process, 중복 완료 action과
   redaction test를 먼저 작성한다.
2. EVAL-RESUME을 실행해 task·thread·worktree가 동일하게 재식별되는지 확인한다.
3. 로그와 state에 credential, 전체 prompt, private thread 원문이 없는지 검사한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- 원격 telemetry 서비스나 dashboard를 추가하지 마라. 이유: 로컬 상태 계약 범위다.
- 병렬 scheduler를 구현하지 마라. 이유: Step 9 범위다.
- 미제공 token 값을 0으로 기록하지 마라. 이유: 미측정과 실제 0을 구분해야 한다.
- 기존 테스트를 깨뜨리지 마라.
