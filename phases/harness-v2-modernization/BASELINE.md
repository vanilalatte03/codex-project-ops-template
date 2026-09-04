# Harness v1 기준선

## 스냅샷

- 관찰일: 2026-09-04
- 기준 commit: `a945f5bc9a64c40e97dcee18de91c4f59b39c7cb`
- `TEMPLATE_VERSION`: `2026.06.17`
- `.codex/project-profile.json`의 `templateVersion`: `2026.06.17`
- Python 요구사항: CI Python 3.11, `requirements-dev.txt`의 `pytest>=8.0`

이 값은 Harness v2의 성능 향상을 주장하는 결과가 아니라 변경 전 비교점을
고정한 것이다. 대표 작업의 v1/v2 반복 실행 결과는 Step 10(#23)에서
`EVALS.md` 계약에 따라 별도로 측정한다.

## 현재 실행 경로

1. `scripts/execute.py`가 v1 `steps[]`에서 다음 `pending` step을 순서대로 선택한다.
2. 구현은 `codex exec --json`으로 실행하며 기본 effort는 `medium`, 호출 timeout은
   1,800초, step 구현 최대 시도 횟수는 3회다.
3. 현재 subprocess 환경은 `shell_environment_policy.inherit=all`이다. 이는 변경 전
   사실을 기록한 것이며 안전한 목표 상태로 승인한 것이 아니다.
4. Codex가 `completed`를 기록해도 실행기가 인수 기준을 다시 실행하고 성공한
   경우에만 timestamp와 커밋을 남긴다.
5. 전체 phase의 pending step이 사라지면 `checks.py --stage final`을 실행하고
   `docs-checks.json`의 final 규칙까지 통과해야 phase를 완료한다.
6. `scripts/autopilot.py`는 전역 lock으로 한 번에 한 프로세스만 허용하고 step을
   직렬 처리한다. step 브랜치와 Draft PR을 만든 뒤 local checks, `git diff
   --check`, scope scan, read-only review, 원격 CI를 통과한 경우에만 ready 전환 및
   squash merge한다. 자동 review-fix 기본 상한은 2회다.

## CI 기준선

`.github/workflows/template-ci.yml`은 Python 3.11에서 `ubuntu-latest`,
`macos-latest`, `windows-latest`를 `fail-fast: false` matrix로 검증한다. 각 job은
dependency 설치, `python -m pytest scripts`, template doctor, configured checks
목록 확인을 실행한다.

기준 commit의 최신 main 실행은
[GitHub Actions run 27660324520](https://github.com/vanilalatte03/codex-project-ops-template/actions/runs/27660324520)이며
세 운영체제 job이 모두 성공했다. job wall time은 GitHub의 시작/완료 timestamp
기준으로 Ubuntu 11초, macOS 13초, Windows 34초다. runner 준비와 후처리를 포함한
값이므로 로컬 pytest 시간과 직접 비교하지 않는다.

## 로컬 기준선 결과

| 검증 | 결과 | 관찰값 |
| --- | --- | --- |
| `python -m pytest scripts` | 환경 문제로 시작 실패 | 현재 Codex 셸 PATH에 `python` 없음 |
| 대체: `uv run --with pytest python -m pytest scripts` | PASS | Python 3.12.13, pytest 9.1.1, 175 passed, pytest 4.47초, 프로세스 10.34초 |
| `python scripts/doctor.py --template` | 환경 문제로 시작 실패 | 현재 Codex 셸 PATH에 `python` 없음 |
| 대체: Codex 번들 Python으로 template doctor | PASS | profile `mixed`, version 일치, required files 정상, readiness `ok`, 프로세스 약 0.31초 |
| 대체: Codex 번들 Python으로 `checks.py --list` | PASS | 프로젝트용 lint/test/build 미설정(템플릿 저장소의 의도된 상태) |
| `git diff --check` | PASS | 변경 전 diff 없음 |

원래 명령의 실패는 test/doctor 실패로 세지 않는다. 실행 파일 탐색 실패로 따로
분류하며, 대체 런타임 결과와 CI 결과를 기능 기준선의 증거로 사용한다.

## 템플릿 저장소의 checks gate 제한

이 저장소는 복사 대상 운영 템플릿이므로 `docs/COMMANDS.md`와
`.codex/project-profile.json`의 프로젝트별 `test` 및 `build` 명령이 의도적으로
비어 있다. 따라서 `python scripts/checks.py --stage manual`과
`python scripts/checks.py --stage final`은 `Missing required check commands: test,
build`로 종료한다. 이는 #13의 문서 변경이나 Harness 기준선 검증의 실패가 아니라
템플릿 저장소 자체의 기존 제한이다. 이 PR의 검증은 위의 직접 unit test, template
doctor, phase docs-check, `git diff --check`와 세 운영체제 CI로 수행하며, 실제
프로젝트 인스턴스에서는 `test`와 `build`를 채운 뒤 checks gate를 사용한다.

## 아직 측정하지 않은 값

대표 eval의 성공률, first-pass 검증률, 재시도 횟수, end-to-end wall time, 사람
개입 횟수와 token 사용량은 이 step에서 실제 반복 task를 실행하지 않았으므로
`미측정`이다. 수치를 0으로 기록하지 않으며 Step 10(#23)에서 같은 fixture와
조건으로 v1/v2를 측정한다.
