# 단계 9: bounded-dag (#22)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/EVALS.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/tests/`

## 작업

- missing, self dependency와 cycle을 Codex 호출 전에 검증하고 충족된 task의 ready
  set만 계산한다.
- task 실행은 기본 동시성 2와 명시적 상한 안에서 병렬화하되 merge와 state 갱신은
  직렬화한다.
- 공유 자원별 lock, 실패·중단·재개·reconcile 규칙을 구현한다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. invalid DAG, ready set, 상한, dependency 순서, 충돌, 중단 후 reconcile test를
   먼저 작성한다.
2. EVAL-DEPS를 실행해 task 실행만 병렬이고 PR merge/state 갱신은 직렬인지 확인한다.
3. 동일 공유 자원을 가진 task가 lock 없이 동시에 실행되지 않는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- 무제한 concurrency를 허용하지 마라. 이유: 비용과 공유 자원 충돌을 제한해야 한다.
- 불명확한 dependency를 추측하지 마라. 이유: 잘못된 실행 순서를 만들 수 있다.
- 여러 PR을 동시에 merge하지 마라. 이유: base와 state 전이를 직렬화해야 한다.
- 기존 테스트를 깨뜨리지 마라.
