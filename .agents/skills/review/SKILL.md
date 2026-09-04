---
name: review
description: "Codex가 이 Harness 기반 프로젝트의 변경사항을 AGENTS.md, 아키텍처 문서, ADR 결정, 테스트 기대사항, 빌드 준비 상태에 맞춰 리뷰해야 할 때 사용한다."
---

# 리뷰

## 개요

저장소 변경사항을 프로젝트 문서의 규칙에 맞춰 검토하고, 구체적인 수정 방향이 포함된 간결한 체크리스트 보고서를 작성할 때 이 워크플로우를 사용한다.

## 워크플로우

### 맥락 읽기

먼저 아래 파일을 읽는다:

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/COMMANDS.md`

`docs/adr/` 디렉터리가 있으면 분리된 ADR도 함께 읽는다. 변경 diff가 다른 문서에서 설명하는 영역을 건드릴 때만 추가 문서를 읽는다.

### 변경사항 확인

변경된 파일과 관련 주변 코드를 확인한다. `git status --short`, `git diff --stat`, `git diff`, 대상이 분명한 `rg` 검색을 우선 사용한다.

### 체크리스트 검증

다음을 확인한다:

1. 아키텍처 준수: 변경사항이 `ARCHITECTURE.md`의 디렉터리와 모듈 구조를 따르는가?
2. 기술 선택: 변경사항이 ADR 결정을 위반하지 않는가?
3. 테스트 커버리지: 새로운 동작에 적절한 테스트가 있거나, 테스트가 필요 없는 명확한 이유가 있는가?
4. 핵심 규칙: 변경사항이 `AGENTS.md`의 CRITICAL 규칙을 위반하지 않는가?
5. 빌드 준비 상태: `docs/COMMANDS.md`의 빌드, 린트, 테스트 명령을 로컬에서 실행할 수 있을 때 통과하는가?
6. task schema: `phases/0-example/index.json`의 v1 원형이 유지되고, v2 변경은
   `docs/TASK_SCHEMA.md`의 `id`·`objective`·`dependsOn`·`issue`·`risk` 및 공통
   status 계약을 따르는가?
7. pre-Codex safety: 중복 id, missing/self dependency, 필수 필드·타입·status 오류가
   Codex/GitHub 호출 전에 파일 및 필드 경로와 reason으로 거부되는가?
8. scope boundary: v2 alias가 저장 시 v1/v2 원형을 바꾸지 않고, #22의 DAG
   scheduler·ready set·cycle 처리·parallelism이나 자동 migration을 선행하지 않는가?
9. worktree safety: `scripts/worktree.py`의 marker owner/task/path/branch/base SHA가
   일치하는 경우만 resume하고, primary branch 불변·동시성 1·실패 보존·stale
   administrative entry 진단·merged/clean/head 검증 뒤의 non-force cleanup을
   지키는가? 사용자 worktree/branch를 자동 삭제·이동·prune하지 않는가?

### 출력

아래 표를 반환한다:

| 항목 | 결과 | 비고 |
| --- | --- | --- |
| 아키텍처 준수 | 통과/실패 | {상세} |
| 기술 스택 준수 | 통과/실패 | {상세} |
| 테스트 존재 | 통과/실패 | {상세} |
| CRITICAL 규칙 | 통과/실패 | {상세} |
| task schema와 pre-Codex 검증 | 통과/실패 | {v1/v2 contract, path/reason 오류, 실행 전 차단} |
| 후속 범위 격리 | 통과/실패 | {DAG/parallel/migration 선행 여부} |
| worktree 소유권·정리 안전성 | 통과/실패 | {primary 불변, marker, stale/실패 보존, cleanup gate} |
| 빌드 가능 | 통과/실패 | {상세} |

어떤 항목이라도 실패하면 파일 경로, 구체적인 문제, 수정 방안을 포함한다. 의존성이 없어서 검사를 실행하지 못한 경우에는 빌드 행에 그 사실을 명확히 적는다.

## 리뷰 관점

스타일 의견보다 버그, 회귀, 누락된 테스트, 규칙 위반을 우선한다. 응답은 간결하고 실행 가능하게 유지한다.
