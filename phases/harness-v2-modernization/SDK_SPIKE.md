# Python Codex SDK spike 결과

- 관련 이슈: [#18](https://github.com/vanilalatte03/codex-project-ops-template/issues/18)
- 기준 commit: `75a5b3e7c51c9c464da3b4e26a238b309fac003b`
- 기록일: 2026-09-06
- 결정: **조건부 GO**. Step 6에서 opt-in adapter를 설계할 근거는 확보했지만,
  현재 production 기본 경로는 계속 `codex exec`로 유지한다.

## 공식 근거

- [Codex SDK](https://developers.openai.com/codex/sdk)는 Python SDK를 stable release로
  명시하며 Python 3.10+, pinned Codex CLI runtime, thread start/run/resume와 sandbox
  preset을 설명한다.
- [Codex App Server](https://developers.openai.com/codex/app-server)는 custom client가
  인증, 대화 이력, 승인과 streaming event를 직접 다룰 때의 경계다. 자동화/CI에는
  SDK 사용을 권한다.
- [Non-interactive mode](https://learn.chatgpt.com/codex/non-interactive-mode)는
  `codex exec`의 JSONL, sandbox, saved CLI auth 재사용과 `exec resume` 계약을
  설명한다.
- 공식 `openai/codex` 저장소의
  [Python API reference](https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md)와
  [FAQ](https://github.com/openai/codex/blob/main/sdk/python/docs/faq.md)를 package
  surface 대조에 사용했다.

## 고정 환경

| 항목 | 값 |
| --- | --- |
| OS | Windows 11 `10.0.26200` |
| Python | uv managed CPython `3.12.13` |
| SDK | `openai-codex==0.147.0` stable |
| SDK runtime | `openai-codex-cli-bin==0.147.0` |
| 기존 CLI | `codex-cli 0.146.0` (`@openai/codex==0.146.0`) |
| model | `gpt-5.6-terra` |
| sandbox / approval | `read-only`; `deny_all` 또는 interrupt probe의 `auto_review` |
| cwd | probe마다 새 빈 임시 디렉터리 |

`openai-codex` 파일 크기는 474,769 byte, pinned runtime은 370,445,518 byte였다.
기존 global npm CLI 디렉터리는 429,301,280 byte였다. 서로 다른 package layout과
cache를 잰 값이므로 설치 footprint의 대략적인 관찰값이며 직접 성능 비교값은 아니다.

## 재현 명령

offline surface probe와 live probe는 사용자 전역 Python 또는 Codex 설정을 바꾸지
않는 uv isolated environment에서 실행한다.

```powershell
uv run --isolated --no-project --with openai-codex==0.147.0 `
  python -X utf8 scripts/sdk_spike.py

uv run --isolated --no-project --with openai-codex==0.147.0 `
  python -X utf8 scripts/sdk_spike.py --live `
  --model gpt-5.6-terra --timeout-seconds 1
```

두 번째 명령은 기존 Codex 인증을 읽고 모델 호출을 수행한다. stdout과
[`SDK_SPIKE_RESULTS.json`](SDK_SPIKE_RESULTS.json)에는 boolean, duration, error
class만 남기며 credential, 계정 식별자, thread ID, prompt와 응답 본문은 남기지
않는다. live 실행은 지속성 확인용 thread를 새 SDK client에서 resume한 뒤 archive한다.

기존 CLI 비교 실행은 빈 비-Git 디렉터리라서 명시적으로 repository 검사를
건너뛰었다.

```powershell
codex exec --json --skip-git-repo-check -s read-only -C <empty-temp-dir> `
  "Reply with exactly EXEC_OK and do not use tools."
```

실제 결과는 exit `0`, JSONL event 5개, wall time `17.13s`였다. 처음
`--skip-git-repo-check` 없이 실행한 결과는 의도한 안전 precondition에 따라 exit
`1`과 `Not inside a trusted directory`로 중단됐다.

## capability 결과

| capability | 기대 결과 | 실제 결과 | 판정 |
| --- | --- | --- | --- |
| stable package / runtime pin | 같은 버전의 SDK와 runtime 설치 | 둘 다 `0.147.0` | 가능 |
| Windows 인증 | 기존 Codex login 재사용, 값 비노출 | account 존재 여부만 `true` | 가능 |
| thread start / run | 지정 model로 terminal completion | exact sentinel, `completed` | 가능 |
| 같은 thread 연속 run | 두 번째 turn 완료 | exact sentinel, `completed` | 가능 |
| client 재시작 후 resume | 같은 thread 재개 | same identifier 확인 후 sentinel 완료 | 가능 |
| model capability | model list에서 지정 model 확인 | 5개 중 `gpt-5.6-terra` 존재 | 가능 |
| read-only sandbox | 쓰기 요청이 파일을 만들지 않음 | marker 없음 | 가능 |
| approval | `deny_all`에서 사용자 입력 없이 종료 | 사람 개입 0회 | 가능 |
| 오류 복구 | invalid resume 뒤 같은 client 재사용 | `InvalidRequestError` 뒤 새 turn 완료 | 가능 |
| timeout | turn 자체 timeout 인자 | `Thread.run`에 timeout 없음 | 불가능 |
| interrupt | active turn 중단 | caller 1초 timeout 뒤 `interrupted` | 가능 |
| native review | stable high-level review method | `Codex`/`Thread`에 없음 | 불가능 |

첫 interrupt 시도는 10ms timeout 뒤 turn이 이미 끝나 `InvalidRequestError: no active
turn` race가 발생했고, client 종료 전 임시 디렉터리 정리에서 Windows file lock도
관찰됐다. 30초 shell wait로 active turn을 보장하고 client를 먼저 닫은 재현에서는
1초 caller timeout, `TurnHandle.interrupt()`, terminal `interrupted`가 통과했다.
adapter는 interrupt를 idempotent completion으로 취급하고 client 종료 뒤 임시 파일을
정리해야 한다.

## `codex exec` 비교

| 관점 | Python SDK 0.147.0 | 기존 `codex exec` 0.146.0 |
| --- | --- | --- |
| 설치 | Python 3.10+, `openai-codex`와 pinned binary runtime | Node/npm 또는 설치된 CLI binary |
| runtime | bundled app-server subprocess와 JSON-RPC | CLI subprocess 한 번과 JSONL stdout |
| 인증 | Windows saved Codex login 재사용 확인 | saved CLI auth 재사용 확인 |
| 출력 | typed `TurnResult`, items, usage, typed exception | JSONL event와 exit code/stderr 직접 parsing |
| thread | object로 연속 run, ID resume, read/list | `codex exec resume`와 persisted session |
| sandbox/approval | enum preset과 turn override; `deny_all`, `auto_review` | CLI flag/config를 subprocess 인자로 전달 |
| timeout/interrupt | native timeout 없음; caller timeout + handle interrupt 필요 | Harness가 subprocess timeout/termination 담당 |
| review | stable high-level native review 없음; read-only prompt는 가능 | `codex review` 또는 현재 read-only `codex exec` gate |
| 테스트 난이도 | typed API unit test는 쉽지만 live auth/app-server test 필요 | subprocess/JSONL fixture와 exit-code test 필요 |
| 주요 위험 | app-server lifecycle, version pin, cleanup/race, API surface 변화 | 문자열 command, JSONL drift, process cleanup, resume ID 관리 |

SDK의 `CodexConfig.experimental_api` 기본값은 `true`로 관찰됐다. 이 값만으로 core
thread API 전체가 실험적이라고 단정하지는 않지만, Step 6 adapter가 private client나
generated `review/start`를 직접 사용해서는 안 된다는 추가 경계로 본다.

## 가능 / 불가능 / 미검증

가능:

- Windows saved login으로 stable SDK thread start/run/continue/resume
- `read-only` sandbox와 `deny_all` 무인 failure behavior
- typed invalid-request 분류 뒤 같은 client 복구
- caller-managed timeout과 active turn interrupt

현재 stable high-level surface에서 불가능:

- `Thread.run(..., timeout=...)` 형태의 native turn timeout
- `Codex.review(...)` 또는 `Thread.review(...)` 형태의 native review

미검증:

- Ubuntu/macOS의 인증 저장소와 sandbox 동작
- headless CI credential provisioning, proxy와 enterprise policy
- `workspace-write`/`full-access`, 사용자 승인 callback, concurrent turn 부하
- SDK usage/token과 기존 JSONL의 장기 schema 호환, 장시간 app-server 안정성

## 결론과 Step 6 전환 전제

SDK-CONDITIONAL-GO-0.147.0-EXEC-FALLBACK

Step 6은 다음 전제를 모두 지키는 opt-in adapter만 설계할 수 있다.

1. `openai-codex==0.147.0`과 matching runtime을 고정하고 기본 runner는 바꾸지 않는다.
2. SDK가 없거나 version/auth/model/sandbox/approval/timeout/interrupt/output 중 하나라도
   검증에 실패하면 현재 `codex exec` 경로로 fail-closed fallback한다.
3. caller timeout 뒤 interrupt, terminal wait, client close 순서를 지키고 이미 끝난
   turn의 interrupt race는 성공 완료와 구분해 idempotent하게 처리한다.
4. native review는 이번 GO에 포함하지 않는다. Step 8까지 기존 read-only review를
   유지하며 private/generated app-server review API에 의존하지 않는다.
5. Linux/macOS와 headless CI를 검증하고 EVAL-V1/EVAL-SAFETY hard gate를 통과하기
   전에는 feature flag 기본값을 SDK로 바꾸지 않는다.

위 전제 중 하나가 깨지면 SDK adapter를 비활성화하고
[`COMPATIBILITY.md`](COMPATIBILITY.md)의 `codex exec` fallback과 rollback 절차를
적용한다.
