# Issue 1: 외부 Codex read-only review 실행 차단

## 상태

- Phase: `harness-v2-modernization`
- Step: `5 sdk-spike`
- GitHub Issue: `#18`
- 분류: 외부 review gate 실행 정책 차단
- 현재 상태: 해결 — 후속 수정의 외부 재리뷰 CLEAR (2026-09-07)

## 최초 현상 (PR #30 작성 당시)

외부 Codex read-only review를 실행하려 했으나 비공개 저장소 내용의 외부 전송에는 별도의 명시적 승인이 필요하다는 정책으로 차단되었다. 최초 요청 뒤 계약 파일과 변경 파일만 명시한 축소 재시도 1회도 같은 이유로 차단되었다.

코드 또는 문서에 대한 review finding은 생성되지 않았다.

## 최초 영향

- 구현과 로컬 자동 검증은 통과했다.
- 외부 review gate가 완료되지 않아 Step 5는 `blocked`로 유지한다.
- PR은 Draft로 유지하며 Ready 전환과 병합을 하지 않는다.

## 복구 조건

사용자가 비공개 저장소의 지정된 계약 파일과 변경 파일을 외부 Codex read-only review에 전송하도록 명시적으로 승인한 뒤 review를 다시 실행한다. finding이 없거나 허용된 retry 범위에서 모두 해소되면 Step 5를 `completed`로 갱신하고 PR Ready 전환을 검토한다.

## 검증 근거

- SDK spike targeted tests: 통과
- 전체 `scripts` pytest: 통과
- compileall: 통과
- template doctor: 통과
- phase docs-check: 통과
- `git diff --check`: 통과
- manual/final stage: 템플릿의 미설정 `test`, `build` 명령 때문에 실패하며 SDK spike 회귀와 무관

## 후속 복구 실행 (2026-09-07)

- PR #30은 `03347e086942e33611461daa635c64318fb72f45`로 develop에 병합됐다.
  위 Draft/미병합 기록은 최초 작성 당시 상태이며 현재 PR 상태가 아니다.
- 고정 리뷰 범위는 `git diff 75a5b3e7c51c9c464da3b4e26a238b309fac003b 03347e086942e33611461daa635c64318fb72f45`다.
- 이번 복구의 승인 전 실행 요청 2회는 정책상 거절됐다. 명시적 승인 후 실행 1회는
  허용 목록 밖 전역 메모리 읽기가 관찰되어 중단했고 그 결과를 채택하지 않았다.
- 이후 허용 파일과 고정 diff만 stdin으로 전달했다. `codex exec --ignore-user-config
  --ephemeral --skip-git-repo-check -s read-only`에 shell_tool, unified_exec, plugins,
  apps, memories, multi_agent, hooks, skill_search 비활성화와
  `memories.use_memories=false`, `project_doc_max_bytes=0`, `web_search="disabled"`를
  적용하고 빈 임시 cwd에서 실행했다. 원문과 실행 식별자는 이 기록에 저장하지 않는다.
- 완료된 최초 리뷰는 runtime pin 검증 누락, lifecycle false-positive,
  timeout 오류 시 무기한 executor 대기 3건을 지적했다. 같은 후속 branch에서 수정했다.
- 수정 후 전체 pytest는 245 passed다. doctor, docs-check, compileall, diff 검사와
  artifact secret/thread/user-path 검사가 통과했다. manual/final은 기존 템플릿
  `Missing required check commands: test, build` 제한으로 실패했다.
- Python은 PATH에 없어 PR #30과 같은 `uv run --isolated --no-project`를 사용했고,
  테스트는 `--with pytest python -X utf8 -m pytest scripts`로 실행했다.
- JSON live artifact는 기존 관찰값을 보존했다. 수정 후 live SDK 재측정은 하지 않았고
  실패 경로는 fake SDK로 검증했다. 조건부 GO, SDK opt-in, exec 기본값과 fallback은 유지한다.
- 수정 후 외부 재리뷰 1회가 exit 0 및 `CLEAR`로 끝났다. 완료된 리뷰는 최초 1회와
  재리뷰 1회이며, 위 정책 거절·중단 실행은 성공 리뷰 횟수에 포함하지 않는다.
  CLI 0.146.0, 최초 기본 effort와 재리뷰 high, read-only로 실행했다.
- Step 5를 `completed`와 한 줄 summary로 변경하고 blocked 필드를 제거했다.
  Step 6은 `pending`이며 이번 후속 PR의 병합은 수행하지 않는다.
- 후속 diff 자체 리뷰: 아키텍처·기술 결정·테스트·CRITICAL·task schema·후속 범위
  격리·worktree 안전성은 통과했다. 빌드 항목은 compileall 통과와 템플릿 build
  미설정을 구분했다. production runner와 worktree lifecycle 변경은 없다.
