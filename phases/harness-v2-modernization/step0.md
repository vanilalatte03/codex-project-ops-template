# 단계 0: baseline-and-metrics (#13)

## 읽어야 할 파일

- `/AGENTS.md`
- `/.agents/skills/harness/SKILL.md`
- `/README.md`
- `/docs/COMMANDS.md`
- `/docs/SCOPE_CHANGE_CHECKLIST.md`
- `/docs/adr/0001-step-pr-workflow.md`
- `/phases/0-example/`
- `/scripts/codex_common.py`
- `/.github/workflows/template-ci.yml`

## 작업

- 변경 전 commit, `TEMPLATE_VERSION`, 실행 경로, CI matrix, doctor와 unit test
  기준선을 `BASELINE.md`에 기록한다.
- 동일 대표 작업을 v1/v2에서 비교할 eval 시나리오, 실행 조건, 성공률,
  first-pass 검증률, 재시도, wall time, 사람 개입과 가능한 token 측정법을
  `EVALS.md`에 고정한다.
- v1 phase/index 보존 기준, fallback, rollback trigger와 복구 절차를
  `COMPATIBILITY.md`에 기록한다.
- #14~#23을 각각 하나의 순차 step으로 연결하고 phase 문서만으로 목표, 순서,
  인수 기준과 제외 범위를 이해할 수 있게 한다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
python scripts/checks.py --docs-check-config phases/harness-v2-modernization/docs-checks.json --docs-check
git diff --check
```

## 검증 절차

1. 원래 명령과 exit code를 기록한다. 로컬 runtime 탐색 문제는 기능 실패와
   분리하고 동일 스크립트를 사용한 대체 runtime 증거를 남긴다.
2. Issue #13의 완료 조건과 제외 범위를 대조한다.
3. 자체 리뷰에서 문서의 수치가 실행 결과와 일치하고 미측정 값을 0으로 쓰지
   않았는지 확인한다.
4. 성공하면 이 step을 `completed`로 바꾸고 한 줄 `summary`를 기록한다.

## 금지사항

- 실행기 동작을 변경하지 마라. 이유: 이 step은 변경 전 기준선 계약만 고정한다.
- worktree, SDK, DAG 또는 병렬 실행을 구현하지 마라. 이유: 후속 Issue 범위다.
- 대표 eval을 실행하지 않고 성능 개선을 주장하지 마라. 이유: 수치는 Step 10에서
  동일 조건으로 측정해야 한다.
- 기존 테스트를 깨뜨리지 마라.
