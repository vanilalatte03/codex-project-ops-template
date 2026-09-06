# 단계 4: isolated-worktree (#17)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/docs/ARCHITECTURE.md`
- `/docs/WORKTREE_LIFECYCLE.md`
- `/docs/ADR.md`
- `/docs/adr/0001-step-pr-workflow.md`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/tests/test_execute.py`
- `/scripts/tests/test_autopilot.py`

## 작업

- 구현 전에 `docs/WORKTREE_LIFECYCLE.md`와 ADR-0004에 상태 전이, marker 최소
  필드, 소유권 판정, 실패 보존·재개, safe cleanup gate를 문서화하고 테스트
  검증 방법을 고정한다.
- task별 branch, worktree, owner와 lifecycle을 별도 모듈로 관리한다.
- primary checkout의 branch를 전환하지 않고 동시성 1로 구현·검증·리뷰한다.
- 성공 task만 안전하게 정리하고 실패 또는 blocked task는 재개할 수 있도록
  보존한다. base sync, PR merge와 state 갱신은 직렬화한다.
- Windows path와 stale worktree를 포함한 테스트를 추가한다.
- v1 `steps[]`와 v2 `tasks[]`가 같은 list-order 직렬 의미를 유지하고, task 간
  변경이 실제 checkout 사이에서 격리되는 통합 테스트를 추가한다.

## 인수 기준

```powershell
python -m pytest scripts/tests/test_execute.py scripts/tests/test_autopilot.py
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. 생성·소유권·보존·정리·stale fixture test를 먼저 작성한다.
2. primary checkout branch와 사용자 worktree가 실행 전후 동일한지 확인한다.
3. 실패 task에서 재개 정보가 남고 성공 task만 정리되는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- 복수 task를 동시에 실행하지 마라. 이유: bounded concurrency는 Step 9 범위다.
- 사용자 worktree 또는 branch를 자동 삭제하지 마라. 이유: 소유권이 불명확하다.
- stale administrative entry를 무차별 prune하지 마라. 이유: 다른 checkout의
  보존 가능한 작업을 잃을 수 있다.
- `git reset --hard`나 force push를 사용하지 마라. 이유: 복구 불가능한 변경을 막는다.
- 기존 테스트를 깨뜨리지 마라.
