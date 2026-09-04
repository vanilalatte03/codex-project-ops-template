# 단계 10: release-eval (#23)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/BASELINE.md`
- `/phases/harness-v2-modernization/EVALS.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/phases/0-example/`
- `/README.md`
- `/CHANGELOG.md`
- `/guides/`
- `/.agents/skills/harness/SKILL.md`
- `/.agents/skills/review/SKILL.md`
- `/scripts/upgrade.py`
- `/.github/workflows/template-ci.yml`

## 작업

- 고정 fixture와 조건으로 모든 대표 시나리오를 v1과 v2에서 실행하고 raw 결과와
  집계표를 남긴다.
- 성공률, first-pass 검증률, 재시도, wall time, 사람 개입과 가능한 token을
  `EVALS.md` 계산식대로 비교한다.
- v1 호환, upgrade dry-run, 세 운영체제 CI를 검증하고 README, guides, skills,
  ADR, CHANGELOG, `TEMPLATE_VERSION`을 실제 최종 계약과 동기화한다.
- hard/quality/efficiency gate에 따라 Harness v2 릴리스 판정을 기록한다. 미달 지표는
  blocker 또는 후속 Issue와 owner를 남긴다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
python scripts/upgrade.py --from . --dry-run
python scripts/checks.py --docs-check-config phases/harness-v2-modernization/docs-checks.json --docs-check
git diff --check
```

## 검증 절차

1. fixture hash, base commit, 환경, 반복 횟수와 raw evidence가 모두 있는지 확인한다.
2. EVAL-V1·EVAL-SAFETY 100%, unit test, doctor, upgrade와 Ubuntu/macOS/Windows CI를
   hard gate로 확인한다.
3. 품질 회귀 없이 최소 한 가지 운영 지표가 개선되거나 유지 근거가 있는지
   자체 리뷰한다.
4. 모든 gate가 성공하면 이 step과 phase를 `completed`로 갱신한다.

## 금지사항

- eval 없이 성능 향상을 주장하지 마라. 이유: 같은 입력의 측정 증거가 필요하다.
- CI 성공을 task 품질 향상과 동일시하지 마라. 이유: correctness eval이 별도다.
- gardening #24를 릴리스 blocker로 만들지 마라. 이유: Epic이 Later로 분리했다.
- 실패 실행을 집계에서 삭제하지 마라. 이유: 성공률이 왜곡된다.
- 기존 테스트를 깨뜨리지 마라.
