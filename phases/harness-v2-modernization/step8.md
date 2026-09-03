# 단계 8: risk-based-review (#21)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/.agents/skills/review/SKILL.md`
- `/docs/adr/0001-step-pr-workflow.md`
- `/scripts/autopilot.py`
- `/scripts/codex_common.py`
- `/scripts/tests/test_autopilot.py`
- `/scripts/tests/test_codex_common.py`

## 작업

- 기존 read-only review를 공통 adapter로 이동하고 지원되는 경우 native review를
  사용하되 capability 또는 실행 실패 시 기존 방식으로 fallback한다.
- 일반 task는 reviewer 1명, 고위험 task만 risk에 맞는 전문 review를 추가한다.
- review 전후 worktree 불변조건과 기존 local checks, diff, scope, CI gate 의미를
  유지한다.

## 인수 기준

```powershell
python -m pytest scripts/tests/test_autopilot.py scripts/tests/test_codex_common.py
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. risk 선택, native success/failure fallback, read-only 변경 감지 test를 먼저 쓴다.
2. review 중 파일 변경 시 PR ready 전 실패하는지 확인한다.
3. 위험도가 낮은 task에 불필요한 reviewer가 실행되지 않는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- 모든 task에 여러 reviewer를 강제하지 마라. 이유: 비용과 지연을 위험도에 맞춘다.
- local checks, diff check, scope scan 또는 CI를 native review로 대체하지 마라.
  이유: 기존 gate를 보존해야 한다.
- review가 worktree를 변경한 상태로 통과시키지 마라. 이유: read-only 계약 위반이다.
- 기존 테스트를 깨뜨리지 마라.
