# 단계 2: progressive-guardrails (#15)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/EVALS.md`
- `/scripts/execute.py`
- `/scripts/codex_common.py`
- `/scripts/tests/test_execute.py`
- `/scripts/tests/test_codex_common.py`
- `/.codex/project-profile.json`
- `/docs/COMMANDS.md`

## 작업

- Codex prompt를 objective, 읽을 경로, acceptance criteria, hard constraints, 이전
  summary 중심으로 축소하고 문서 본문은 Codex가 직접 읽게 한다.
- `guardrailDocs`는 경로 선택 입력으로 유지하며 누락·존재하지 않는 참조를 명확히
  진단한다.
- EVAL-DOCS와 EVAL-CODE의 동일 fixture로 v1 대비 품질과 prompt/token 지표를
  기록한다.

## 인수 기준

```powershell
python -m pytest scripts/tests/test_execute.py scripts/tests/test_codex_common.py
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. prompt 계약과 누락 참조 test를 먼저 작성한다.
2. 위 인수 기준을 실행하고 대표 eval 결과를 `EVALS.md` 형식으로 남긴다.
3. 필요한 경로와 검증 명령이 prompt에 남는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- phase/index schema를 바꾸지 마라. 이유: Step 3 범위다.
- SDK나 worktree를 도입하지 마라. 이유: Step 4~6 범위다.
- token을 추정값으로 채우지 마라. 이유: runner가 제공하지 않으면 null과 사유를
  기록해야 한다.
- 기존 테스트를 깨뜨리지 마라.
