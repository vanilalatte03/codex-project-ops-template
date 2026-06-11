# 단계 0: project-setup

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/COMMANDS.md`
- `/phases/0-example/README.md`

## 작업

메모 CLI의 프로젝트 골격을 만든다.

- `notes/` 패키지와 진입점 `notes/cli.py`를 생성한다.
- `notes/storage.py`에 메모를 로컬 JSON 파일로 읽고 쓰는 `load_notes()`, `save_notes(notes)` 함수 시그니처를 정의한다.
- 저장 파일 경로는 `notes.json` 하나로 고정한다.
- 빈 저장 파일과 파일 없음 상태를 동일하게 빈 목록으로 처리한다.

## 인수 기준

```bash
python scripts/checks.py --stage manual
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md의 디렉터리 구조를 따르는가?
   - ADR의 기술 스택을 벗어나지 않았는가?
   - AGENTS.md의 CRITICAL 규칙을 위반하지 않았는가?
   - COMMANDS.md의 검증 명령을 실행했는가?
3. 결과에 따라 `phases/0-example/index.json`의 해당 단계를 업데이트한다:
   - 성공 -> `"status": "completed"`, `"summary": "산출물 한 줄 요약"`
   - 수정 3회 시도 후에도 실패 -> `"status": "error"`, `"error_message": "구체적 에러 내용"`
   - 사용자 개입 필요 -> `"status": "blocked"`, `"blocked_reason": "구체적 사유"` 후 즉시 중단

## 금지사항

- 메모 추가/목록 명령 로직을 이 단계에서 구현하지 마라. 이유: 단계 1의 범위이며, 선행 구현은 step PR 리뷰에서 blocker다.
- 원격 저장소 연동 코드를 추가하지 마라. 이유: phase 제외 범위다.
- 기존 테스트를 깨뜨리지 마라
