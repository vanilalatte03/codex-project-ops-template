# Archive

완료된 MVP/phase의 요약 기록을 보관하는 디렉터리입니다.

phase가 누적되면 현재 문서(`README.md`, `docs/`)에 과거 MVP 맥락이 쌓여
문서가 부패합니다. MVP를 전환할 때 직전 MVP의 요약을 여기로 옮기고, 현재
문서에는 현재 baseline만 남깁니다.

## 원칙

- archive는 과거 MVP 맥락 확인용이며 **구현 source of truth가 아닙니다**.
  현재 구현 기준은 루트 `README.md`와 `docs/` 아래 현재 문서입니다.
- API 목록, 스키마, 점수 체계 같은 계약 원문을 archive에 복사하지 않습니다.
  당시 ADR과 phase 기록으로 링크합니다.
- archive를 만든 뒤에는 갱신하지 않습니다. 고칠 내용이 생기면 현재 문서나
  새 ADR에 반영합니다.
- 전환 시 함께 갱신할 현재 문서 목록은 `docs/SCOPE_CHANGE_CHECKLIST.md`를
  따릅니다.

## 작성 시점

새 MVP를 기획하면서 현재 baseline 문구를 바꾸기 직전에, 직전 MVP 디렉터리를
만들고 4개 파일을 작성합니다.

```text
archive/{직전-mvp-또는-phase-이름}/
  README.md      # 한 화면 요약과 관련 링크
  SUMMARY.md     # 구현/유지/제외된 기능
  CHANGELOG.md   # 완료 목록과 후속 작업
  DECISIONS.md   # 주요 결정 요약과 다음 MVP로 넘긴 문제
```

## 파일별 형식

### `README.md` — 한 화면 요약

```markdown
# {프로젝트} {MVP/phase 이름} Archive

이 문서는 {MVP 이름}을 이해하기 위한 최소 요약이다.

- 아카이브 정리 시점: {YYYY-MM-DD}
- 완료 시점: {phases/{phase}/index.json의 completed_at}
- 상태: {완료 후 어떤 MVP로 전환했는지 한 줄}
- 목표: {이 MVP가 달성하려던 것 한 줄}
- 최종 범위: {실제로 구현된 범위 한 줄}

현재 구현 기준 문서는 루트 `README.md`와 `docs/` 아래 문서다.
이 archive는 과거 MVP 맥락 확인용이며 구현 source of truth가 아니다.

## 관련 링크

- 현재 PRD: ../../docs/PRD.md
- ADR 인덱스: ../../docs/ADR.md
- 이 MVP의 ADR: ../../docs/adr/{NNNN}-{title}.md
- 이 MVP의 phase 기록: ../../phases/{phase}/README.md
- 요약: SUMMARY.md / 결정: DECISIONS.md / 변경 이력: CHANGELOG.md
```

### `SUMMARY.md` — 기능 스냅샷

```markdown
# {MVP 이름} Summary

## 구현된 기능
- {이번 MVP에서 새로 만든 것}

## 유지된 기능
- {이전 MVP에서 이어받아 그대로 동작하는 것}

## 제외된 기능
- {이번 MVP에서 의도적으로 하지 않은 것}
```

### `CHANGELOG.md` — 완료와 후속

```markdown
# {MVP 이름} Changelog

## 완료
- {phase 완료, ADR 추가, 주요 구현 항목}

## 후속
- {다음 MVP에서 진행하기로 한 것}
```

### `DECISIONS.md` — 결정 요약

```markdown
# {MVP 이름} Decisions

상세 결정 기록은 `docs/adr/`에 유지한다. 이 문서는 주요 결정만 요약한다.

## 주요 결정
- {결정 한 줄}. 자세한 내용은 ../../docs/adr/{NNNN}-{title}.md 를 따른다.

## 다음 MVP로 넘긴 문제
- {이번에 결정하지 않고 미룬 것}
```
