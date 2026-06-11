# 단계 1: note-commands

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/COMMANDS.md`
- `/phases/0-example/README.md`
- `/notes/storage.py` (단계 0에서 생성)

이전 단계에서 만들어진 코드를 꼼꼼히 읽고, 설계 의도를 이해한 뒤 작업하라.

## 작업

단계 0의 골격 위에 메모 추가/목록 명령을 구현한다.

- `notes add "<내용>"`: 메모를 저장 파일에 추가한다. 빈 내용은 에러로 거부한다.
- `notes list`: 저장된 메모를 추가 순서대로 출력한다. 메모가 없으면 안내 문구를 출력한다.
- 명령 파싱은 `notes/cli.py`에 두고, 저장 로직은 단계 0의 `notes/storage.py` 함수만 사용한다.
- 두 명령에 대한 테스트를 추가한다.

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

- 메모 삭제/검색/태그 명령을 추가하지 마라. 이유: phase 제외 범위이며, 필요하면 다음 phase에서 다룬다.
- 저장 파일 형식을 바꾸지 마라. 이유: 단계 0에서 확정한 계약이다.
- 기존 테스트를 깨뜨리지 마라
