# 문서 점검

템플릿 저장소의 `docs`, `guides`, `README.md`를 주 1회 정적으로 점검한다.
`.github/workflows/docs-gardening.yml`은 읽기 전용으로 실행되며 변경이 없으면
`No drift detected`만 실행 요약에 남긴다. 모델 호출, 자동 커밋, 브랜치 push,
이슈 또는 PR 생성은 하지 않는다. 실행 시간 상한은 10분이다.

## 검사 범위

- Markdown의 로컬 파일 링크가 존재하는지 확인한다. 외부 URL과 같은 문서 내부
  anchor는 검사하지 않는다.
- `docs/COMMANDS.md`와 `docs/ARCHITECTURE.md`에서 `python scripts/*.py`로
  표기한 스크립트가 존재하는지 확인한다. 명령의 실제 실행 가능성과 의미는
  검증하지 않는다.
- `docs/adr/*.md`의 ADR 번호와 제목이 `docs/ADR.md` 인덱스에 있는지 확인한다.
  제목 형식이 모호하면 자동 수정하지 않는다.
- phase schema와 profile 검사는 같은 workflow의 `doctor.py --template`가 맡는다.
  정적 경로 검사가 아키텍처 의미의 일치까지 증명하지는 않는다.

## 수동 실행과 처리

```bash
python scripts/garden_docs.py
python scripts/garden_docs.py --fix-safe --json
python -m pytest scripts
python scripts/doctor.py --template
```

첫 명령은 파일을 바꾸지 않는다. `--fix-safe`는 새 ADR의 제목이 명확하고
`## ADR 목록`이 있을 때 빠진 인덱스 항목만 추가한다. 출력의 `safeChanges`는
추가한 ADR 경로이고 `needsJudgment`는 깨진 링크, 없는 스크립트, 모호한 ADR
제목 등 사람이 판단할 항목이다. 변경이 있으면 diff를 확인하고 별도 PR로
제출한다. 판단 항목은 원문과 실제 경로·명령을 대조한 뒤 수정한다.

## 자동 실행과 비활성화

GitHub Actions의 매주 월요일 03:23 UTC `schedule`과 `workflow_dispatch`가
같은 읽기 전용 점검을 실행한다. 발견 사항이 있으면 실행 요약에 경로와 줄을
표시하고 job을 실패로 끝낸다. 동일 항목에 대해 이슈나 PR을 반복 생성하지
않는다. GitHub의 예약 workflow는 기본 브랜치에 workflow가 있어야 실행되므로
`develop`에만 병합된 동안에는 예약 실행이 시작되지 않는다.

수동 실행은 Actions 탭의 `Documentation gardening`에서 `Run workflow`를
선택한다. 중단하려면 GitHub Actions에서 해당 workflow를 비활성화하거나
`.github/workflows/docs-gardening.yml`의 `schedule`을 제거한다. 파일을 수정한
경우에는 PR과 CI로 반영한다.
