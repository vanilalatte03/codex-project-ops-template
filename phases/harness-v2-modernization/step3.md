# 단계 3: task-schema-v2 (#16)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/phases/0-example/index.json`
- `/.agents/skills/harness/SKILL.md`
- `/.agents/skills/review/SKILL.md`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/doctor.py`
- `/scripts/tests/`

## 작업

- outcome task의 `id`, `objective`, `dependsOn`, `issue`, `risk` 필드와 validation
  오류를 정의한다.
- 기존 `step`, `name`, `status`만 가진 v1 파일을 migration 없이 계속 읽고 같은
  의미로 실행한다.
- 예제, Harness와 review skill, doctor, unit test, opt-in migration 규칙을 함께
  갱신한다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. v1 fixture와 v2 valid/invalid fixture를 먼저 고정한다.
2. 중복 id, missing/self/unknown dependency와 잘못된 status가 Codex 호출 전에
   거부되는지 확인한다.
3. EVAL-V1을 실행하고 원본 phase/index가 자동 변경되지 않았는지 대조한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- DAG scheduler나 병렬 실행을 구현하지 마라. 이유: Step 9 범위다.
- 기존 phase 파일을 자동 덮어쓰지 마라. 이유: v1 보존 계약을 위반한다.
- 새 필드가 없다는 이유로 v1 입력을 실패시키지 마라. 이유: additive schema다.
- 기존 테스트를 깨뜨리지 마라.
