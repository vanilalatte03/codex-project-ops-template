# 단계 5: sdk-spike (#18)

## 읽어야 할 파일

- `/phases/harness-v2-modernization/README.md`
- `/phases/harness-v2-modernization/EVALS.md`
- `/phases/harness-v2-modernization/COMPATIBILITY.md`
- `/scripts/codex_common.py`
- `/scripts/execute.py`
- `/scripts/autopilot.py`
- `/docs/ADR.md`
- `/docs/adr/`

## 작업

- 안정 버전 Python Codex SDK의 thread start, run, resume, Windows 인증, sandbox,
  approval, timeout, interrupt, 오류 복구와 model capability를 재현 가능한 spike로
  검증한다.
- 기존 `codex exec`와 설치, runtime, 출력, 테스트 난이도, native review 가능 범위와
  위험을 비교한다.
- GO 또는 NO-GO, 전환 전제와 `codex exec` fallback 조건을 새 ADR로 남긴다.

## 인수 기준

```powershell
python -m pytest scripts
python scripts/doctor.py --template
git diff --check
```

## 검증 절차

1. 고정된 SDK 버전, 환경과 spike 명령을 기록한다.
2. 성공과 의도된 실패를 모두 재현하고 결과 artifact에서 secret을 검사한다.
3. ADR과 `COMPATIBILITY.md` fallback 원칙이 일치하는지 자체 리뷰한다.
4. 성공하면 index의 해당 step을 `completed`와 한 줄 `summary`로 갱신한다.

## 금지사항

- 기존 runner를 제거하거나 production 기본 경로를 전환하지 마라. 이유: spike는
  의사결정 단계다.
- 실험적 App Server API를 필수 의존성으로 만들지 마라. 이유: 안정성 검증 범위를
  벗어난다.
- credential이나 thread 원문을 커밋하지 마라. 이유: 민감정보 경계를 위반한다.
- 기존 테스트를 깨뜨리지 마라.
