# Codex 프롬프트 모음

템플릿을 복사한 직후에는 Codex를 Plan Mode로 전환하고, 셋업과 phase 설계
프롬프트를 위에서부터 순서대로 사용합니다. 목적은 Codex가 임의로 구현을
시작하기 전에 MVP 범위, 기술 스택, 검증 명령, phase 경계를 먼저 문서로
확정하게 만드는 것입니다.

phase 설계가 끝나고 설계 문서가 commit된 뒤에는 일반 작업 모드에서
"운영: autopilot으로 구현 시작" 프롬프트를 사용합니다.

## 셋업: 한 번에 정리하기

프로젝트 그림이 어느 정도 잡혀 있으면 아래 통합 프롬프트 하나로 시작합니다.

```text
이 프로젝트의 MVP를 확정하기 위해 나에게 필요한 질문을 먼저 해줘.
답변을 바탕으로 docs/PRD.md, docs/ARCHITECTURE.md, docs/COMMANDS.md,
docs/ADR.md, AGENTS.md, .codex/project-profile.json의 placeholder를 실제 값으로
채울 계획을 작성해줘. 아직 코드는 구현하지 말아줘.

질문은 MVP 목표, 사용자, must-have 범위, 제외 범위, 기술 스택, 저장소/외부 API,
인증/권한, 테스트/빌드 명령, 배포 또는 실행 방식, 리스크와 ADR 후보를 빠짐없이
확인해줘. 모호한 답변은 임의로 확정하지 말고 후속 질문으로 좁혀줘.
```

## 셋업: 단계별로 정리하기

정보가 부족한 프로젝트는 아래 프롬프트를 단계별로 던집니다.

### 1. 제품 범위 확정

```text
이 프로젝트의 PRD를 채우기 위해 나에게 질문해줘.
질문은 목표, primary/secondary 사용자, MVP must-have, 완료 기준, 제외 범위,
구현 전 결정이 필요한 리스크를 확정하는 데 집중해줘.
답변을 받은 뒤 docs/PRD.md에 들어갈 초안을 제시하고, MVP와 제외 범위를
Codex가 혼동하지 않게 명확한 문장으로 정리해줘.
```

### 2. 아키텍처 확정

```text
확정된 PRD를 기준으로 docs/ARCHITECTURE.md를 채우기 위해 나에게 질문해줘.
런타임/프레임워크, 언어, 저장소, 외부 의존성, 디렉터리 구조, 모듈 경계,
데이터 흐름, 오류 처리, 테스트 전략을 확정해줘.
답변을 바탕으로 구현 경계와 데이터 흐름이 드러나는 아키텍처 초안을 작성해줘.
```

### 3. 명령과 profile 확정

```text
이 프로젝트의 docs/COMMANDS.md와 .codex/project-profile.json을 채우기 위해
필요한 질문을 해줘. dev, lint, test, build 명령과 sourceRoots, testRoots,
guardMode, 필요한 stageChecks/guardrailDocs를 확정해줘.
확정된 기술 스택 기준으로 Windows PowerShell에서 실행 가능한 명령을 우선
작성하고, test와 build가 비어 있으면 안 되는 이유를 함께 표시해줘.
```

### 4. ADR 후보 정리

```text
확정된 docs/PRD.md, docs/ARCHITECTURE.md, docs/COMMANDS.md를 기준으로
ADR에 기록해야 할 기술 결정을 선별해줘.

나중에 바꾸면 코드, 데이터, 배포, 테스트에 큰 영향을 주는 결정만 골라줘.
단순 취향, 파일명, 작은 라이브러리, 미확정 아이디어는 ADR로 만들지 말아줘.

각 후보마다 제목, 왜 ADR인지, 결정 내용, 검토한 대안, 되돌리기 어려운 이유,
제안 파일명(docs/adr/0001-title.md 형식)을 짧게 작성해줘.
아직 파일을 쓰지 말고 먼저 승인받아줘.
```

### 5. AGENTS.md 최종 반영

```text
확정된 PRD, ARCHITECTURE, ADR, COMMANDS 내용을 기준으로 AGENTS.md의
프로젝트명, 목표, 기술 스택, 명령어 placeholder를 채울 계획을 작성해줘.
CRITICAL 규칙은 유지하되, 이 프로젝트에 맞게 외부 API, DB, 인증, 파일 시스템
경계를 더 구체화할 부분이 있으면 제안해줘.
```

## 운영: phase/step 설계

`python scripts/doctor.py --instance`가 통과한 뒤, Plan Mode에서 Harness skill로
phase/step 설계안을 만들 때 사용합니다.

```text
Harness skill을 사용해서 확정된 문서를 기준으로 phase를 설계해줘.
MVP를 phases/{phase}/README.md, index.json, stepN.md로 나누되, 각 step은
하나의 레이어 또는 모듈만 다루게 작게 쪼개줘.
각 step에는 읽어야 할 파일, 작업, 인수 기준, 검증 절차, 금지사항을 포함하고,
docs/COMMANDS.md의 test/build 명령을 완료 기준에 반영해줘.
아직 phase를 실행하거나 코드를 구현하지 말고, 먼저 phase/step 설계안을 제시해줘.
```

## 운영: autopilot으로 구현 시작

phase/step 설계가 끝났고, 설계 문서 변경을 commit해서 worktree가 깨끗한 상태일 때
사용합니다. `{phase-name}`은 `phases/{phase-name}/` 디렉터리 이름으로 바꿉니다.

```text
설계가 끝난 phase를 autopilot으로 구현해줘.

먼저 아래 사전 조건을 확인해줘:
- `git status --short`가 비어 있는 clean worktree 상태
- `git remote get-url origin`이 성공
- `gh auth status`가 성공
- base 브랜치가 origin과 동기화 가능
- base 브랜치에서 `python scripts/checks.py --stage manual`이 통과

사전 조건이 충족되면 아래 명령으로 phase 전체 구현을 진행해줘:

python scripts/autopilot.py {phase-name} --max-review-fixes 2

실패하면 임의로 우회하지 말고, 실패한 명령과 핵심 에러를 요약하고
필요한 수정 방향을 제안해줘.
```
