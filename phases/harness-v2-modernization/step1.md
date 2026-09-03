# 단계 1: minimize-environment-inheritance (#14)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/BASELINE.md`
- `/scripts/codex_common.py`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/scripts/tests/test_codex_common.py`
- `/scripts/tests/test_execute.py`
- `/scripts/tests/test_autopilot.py`
- `/.codex/config.toml`

## 작업

- `shell_environment_policy.inherit=all`을 제거하고 core 또는 filter 기반의 최소
  환경 상속 정책과 프로젝트별 명시적 확장 지점을 정의한다.
- Windows, Linux, macOS의 PATH와 runtime 탐색을 유지하면서 secret-name 환경
  변수가 Codex subprocess로 전달되지 않는 테스트를 추가한다.

## 인수 기준

```powershell
python -m pytest scripts/tests/test_codex_common.py scripts/tests/test_execute.py scripts/tests/test_autopilot.py
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. 세 운영체제별 허용·차단 환경 변수 fixture를 먼저 작성한다.
2. 위 인수 기준과 CI matrix를 실행한다.
3. 기존 command 탐색과 project별 확장 경로가 유지되는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- credential 값을 코드나 fixture에 넣지 마라. 이유: 이름과 가짜 sentinel만으로
  차단을 검증할 수 있다.
- 사용자 전역 Codex 설정을 수정하지 마라. 이유: 템플릿 범위를 벗어난다.
- prompt, schema 또는 worktree 동작을 함께 바꾸지 마라. 이유: 후속 step 범위다.
- 기존 테스트를 깨뜨리지 마라.
