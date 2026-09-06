# ADR-0005: Python Codex SDK 조건부 도입과 exec fallback

- 상태: Accepted
- 날짜: 2026-09-06
- 관련 이슈: #18
- 결정 식별자: SDK-CONDITIONAL-GO-0.147.0-EXEC-FALLBACK

## 문맥

현재 Harness는 `codex exec --json` subprocess를 구현, review와 fix에 사용한다.
stable Python SDK가 같은 기능을 typed API, 지속 thread와 직접 interrupt로 제공하면
Step 6 이후 runner 경계를 단순화할 수 있다. 반면 spike에서 검증하지 않은 API나
실험적 App Server surface를 기본 경로로 만들면 기존 v1 호환, sandbox, approval와
read-only review gate를 약화시킬 수 있다.

공식 문서와 `openai-codex==0.147.0` live spike 결과는
[`SDK_SPIKE.md`](../../phases/harness-v2-modernization/SDK_SPIKE.md)와 sanitized
[`SDK_SPIKE_RESULTS.json`](../../phases/harness-v2-modernization/SDK_SPIKE_RESULTS.json)에
고정한다.

## 결정

**조건부 GO**로 결정한다. 이 GO는 Step 6에서 opt-in SDK runner adapter를 설계할
수 있다는 뜻이며, production 기본 경로를 SDK로 전환한다는 뜻이 아니다.

1. 다음 adapter spike 기준은 `openai-codex==0.147.0`과 자동 설치되는
   `openai-codex-cli-bin==0.147.0`으로 고정한다.
2. 현재 `codex exec` runner와 read-only review를 기본 fallback으로 유지한다.
3. SDK adapter는 feature flag 기본 off, missing/version mismatch/auth/model/sandbox/
   approval/timeout/interrupt/output failure 시 fail-closed exec fallback을 전제로 한다.
4. SDK에는 native turn timeout이 없으므로 caller deadline, active turn interrupt,
   terminal wait, client close 순서가 검증되기 전에는 Harness timeout을 대체하지 않는다.
5. stable high-level SDK에는 native review method가 없으므로 Step 8 전에는 기존
   read-only review를 유지한다. private client나 generated `review/start`, 직접
   App Server protocol 구현을 필수 의존성으로 사용하지 않는다.
6. credential, account identifier, thread identifier, prompt와 response 본문을
   telemetry나 committed artifact에 기록하지 않는다.

## 근거

Windows 11, Python 3.12.13에서 SDK의 saved login 재사용, model list, thread
start/run/continue, 새 client에서 resume, read-only write 차단, `deny_all`, invalid
resume 뒤 같은 client 복구, caller timeout 뒤 interrupt가 통과했다. SDK와 runtime은
같은 stable version으로 설치됐다.

반면 native timeout과 high-level native review는 없었다. 아주 짧은 timeout에서는
turn completion과 interrupt가 경합했고, client 종료 전 Windows 임시 디렉터리
정리도 file lock에 실패할 수 있었다. Ubuntu/macOS, headless CI와 장시간 안정성은
아직 검증하지 않았다.

## 전환 전제

- Step 6 adapter가 기존 환경 상속 최소화, worktree owner/base pin, v1/v2 원형과
  serial list-order를 그대로 보존한다.
- SDK/exec가 같은 acceptance, scope, diff, CI gate를 거치고 fallback 원인만
  비민감 structured result에 남긴다.
- Ubuntu/macOS/Windows와 headless CI에서 package install, auth boundary, sandbox,
  timeout/cleanup을 검증한다.
- Step 10의 EVAL-V1과 EVAL-SAFETY hard gate가 100%이고 quality gate가 회귀하지
  않는다.

## Fallback과 rollback

SDK import 또는 version pin, bundled runtime 시작, 인증, model capability,
sandbox/approval mapping, timeout/interrupt, typed output 처리 중 하나라도 실패하면
그 task는 현재 `codex exec` 경로에서 같은 gate로 다시 실행한다. 무조건 retry하지
않고 기존 retry 상한을 적용한다.

fallback 자체가 실패하거나 safety/v1 gate를 우회하면 새 task와 merge를 중단하고
진행 중 issue/branch/worktree/state를 보존한다. SDK flag를 비활성화한 뒤
`COMPATIBILITY.md`의 마지막 검증된 exec 경로와 rollback 절차로 복구한다. force
push, hard reset과 사용자 worktree 자동 삭제는 사용하지 않는다.

## 결과

- Step 5는 production runner를 수정하지 않는다.
- Step 6은 SDK와 exec를 공통 contract 뒤에 둘 수 있지만 SDK 기본 전환은 별도
  검증과 승인이 필요하다.
- Step 8 native review adapter는 이번 결정과 분리한다.
