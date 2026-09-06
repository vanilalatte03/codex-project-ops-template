# Issue 1: 외부 Codex read-only review 실행 차단

## 상태

- Phase: `harness-v2-modernization`
- Step: `5 sdk-spike`
- GitHub Issue: `#18`
- 분류: 외부 review gate 실행 정책 차단

## 현상

외부 Codex read-only review를 실행하려 했으나 비공개 저장소 내용의 외부 전송에는 별도의 명시적 승인이 필요하다는 정책으로 차단되었다. 최초 요청 뒤 계약 파일과 변경 파일만 명시한 축소 재시도 1회도 같은 이유로 차단되었다.

코드 또는 문서에 대한 review finding은 생성되지 않았다.

## 영향

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
