# 단계 6: runner-adapter (#19)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/docs/ADR.md`
- `/scripts/codex_common.py`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/tests/test_codex_common.py`
- `/scripts/tests/test_execute.py`
- `/scripts/tests/test_autopilot.py`

## 작업

- `start`, `run`, `resume`, `review`, `interrupt` 공통 runner contract와 정규화된
  결과 모델을 정의한다.
- Step 5 ADR에 따라 SDK 또는 exec adapter를 추가하고 구현·review-fix thread를
  지속한다.
- capability 검증 뒤 adapter를 선택하고 실패 시 명시적으로 기존 `codex exec`
  fallback을 사용한다.

## 인수 기준

```powershell
python -m pytest scripts/tests/test_codex_common.py scripts/tests/test_execute.py scripts/tests/test_autopilot.py
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. 공통 contract와 adapter별 정상·resume·timeout·fallback test를 먼저 작성한다.
2. executor와 autopilot이 구체 호출 명령을 직접 구성하지 않는지 확인한다.
3. model/effort capability 오류와 결과 정규화를 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- task 병렬 실행을 추가하지 마라. 이유: Step 9 범위다.
- 모든 오류를 무조건 retry하지 마라. 이유: 비복구 오류와 사람 개입을 구분해야 한다.
- fallback에서 기존 safety gate를 생략하지 마라. 이유: 호환성보다 안전성이 우선이다.
- 기존 테스트를 깨뜨리지 마라.
