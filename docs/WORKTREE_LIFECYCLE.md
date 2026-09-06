# Task worktree lifecycle

이 문서는 Harness가 task별 Git worktree를 만들고 재개하며 정리할 때의 운영
계약이다. 기본 checkout은 사용자의 작업 공간으로 간주하고, Harness가 소유하지
않은 branch·worktree·stale administrative entry는 자동으로 바꾸거나 삭제하지
않는다.

## 역할과 기본 경로

- **primary checkout**: autopilot을 시작한 checkout이다. 현재 branch, 파일,
  index와 사용자의 변경을 보존하며 branch switch, commit, stage를 하지 않는다.
- **task worktree**: 한 task의 구현·인수 검증·read-only review·PR 준비가 일어나는
  독립 checkout이다. autopilot은 동시성 1로 하나만 활성화한다.
- 기본 task worktree root는 primary checkout의 부모 아래
  `.codex-worktrees/<repository-name>/`이다. `--worktree-root`로 다른 절대 경로를
  지정할 수 있지만 primary checkout 안쪽 경로는 사용하지 않는다.
- marker는 working tree 파일이 아니라 Git worktree administrative directory의
  `harness-worktree.json`에 저장한다. 따라서 marker가 task 변경에 섞이거나
  primary checkout을 dirty하게 만들지 않는다.

## Marker 최소 계약

marker는 UTF-8 JSON이며 전체 prompt, credential, Codex thread 원문을 저장하지
않는다.

| 필드 | 의미 |
| --- | --- |
| `schemaVersion` | marker 형식 버전. 현재 `1` |
| `owner` | 정확히 `codex-harness`여야 Harness 소유로 인정 |
| `taskId` | phase 안에서 task를 재식별하는 안정적인 ID |
| `phase` | 실행 중인 phase 이름 |
| `branch` | task branch 이름 |
| `worktreePath` | 정규화된 절대 worktree 경로 |
| `baseRef` | 생성에 사용한 remote/base ref, 예: `origin/develop` |
| `baseSha` | `baseRef`를 생성 시점에 해석한 전체 commit SHA |
| `status` | lifecycle 상태 |
| `headSha` | 마지막으로 확인한 task HEAD SHA(선택) |
| `createdAt`, `updatedAt` | marker 기록 시각 |
| `lastError`, `diagnostics` | 재개·수동 복구에 필요한 축약 진단(선택) |

marker는 임시 파일에 먼저 기록한 뒤 같은 administrative directory 안에서
atomic replace한다. 부분 JSON은 유효한 상태로 보지 않으며, 읽기 실패는 해당
task를 보존한 채 진단한다.

## 상태 전이

```text
created -> running -> implemented -> reviewing -> ready -> merged -> cleanup
   |         |            |             |          |
   +---------+------------+-------------+----------+--> error | blocked | interrupted
                                                        ^
                                                        |
                                      error/blocked/interrupted --resume--> running
```

- `created`부터 `ready`까지는 같은 marker의 task만 갱신한다.
- `error`, `blocked`, `interrupted`는 실패 원인과 진단을 기록하고 checkout과
  branch를 남긴다. 재실행은 새 branch를 만들지 않고 marker의 동일 task/path/
  branch/base를 검증한 뒤 `running`으로 재개한다.
- `merged`는 PR merge 성공만 의미한다. `completed`라는 Codex 보고만으로는
  정리할 수 없다.
- 상태 갱신·base sync·PR merge는 autopilot의 repository lock 안에서 한 번에
  하나씩 수행한다. `dependsOn`은 이 단계에서 scheduler로 해석하지 않는다.

## 소유권과 재개 판정

다음 네 값이 marker와 요청에 모두 일치해야 기존 task를 재개한다.

1. `owner == codex-harness`
2. `taskId`와 phase/branch가 일치
3. 정규화한 `worktreePath`가 일치하고 managed root 아래에 있음
4. `baseRef`와 `baseSha`가 일치하고 Git administrative entry가 그 경로와
   branch를 가리킴

marker가 없거나, owner가 다르거나, 이미 존재하는 branch/path가 다른 작업에
속하면 `WorktreeConflict`로 중단한다. 기존 내용을 덮어쓰거나 `git checkout`으로
사용자 branch를 이동하지 않는다. path는 존재하지만 marker가 없는 경우 비어
있어 보여도 소유권을 추측하지 않는다.

Git administrative entry만 남은 stale 상태도 자동 `git worktree prune` 대상이
아니다. Harness 소유 marker와 실제 경로가 불일치하면 stale 진단을 보존하고
사람이 entry와 파일을 확인한 뒤 복구한다.

## 안전 정리 gate

`safe_cleanup`은 다음 조건을 모두 확인한 Harness 소유 task에만 적용한다.

- marker status가 `merged`이고 owner/task/path/branch가 일치한다.
- path가 primary가 아니며 managed root 아래의 절대 경로다.
- Git이 path를 해당 branch의 active worktree로 보고하고 administrative entry가
  stale하지 않다.
- `git status --porcelain --untracked-files=all --ignored`가 비어 있고, HEAD가
  marker의 `headSha` 또는 호출자가 고정한 expected SHA와 같다.
- `git worktree remove`가 force 없이 성공한다. local branch 삭제는 marker의
  Harness 소유 branch에 대해서만 `git branch -d`로 시도하며, 실패하면 branch를
  보존한다.

어느 gate라도 실패하면 worktree·marker·진단을 보존한다. `--force`, `reset --hard`,
사용자 branch 삭제, 사용자 worktree 이동, 무차별 `prune`은 lifecycle 구현에서
사용하지 않는다.

## 운영 및 migration

```powershell
python scripts/worktree.py list
python scripts/worktree.py resume <task-id>
python scripts/worktree.py cleanup <task-id> --expected-head-sha <sha>
python scripts/autopilot.py <phase-name> --base develop --max-review-fixes 2
```

`list`는 active/stale marker를 읽기만 한다. `resume`은 동일 marker의 소유권과
경로를 검증해 재개 정보를 출력한다. `cleanup`은 merge와 expected SHA를 사람이
확인한 뒤에도 위 gate를 다시 통과해야 한다.

기존 phase/index의 v1 `steps[]`와 v2 `tasks[]`는 그대로 유지한다. worktree
marker는 phase index migration이 아니며, v1을 v2로 바꾸거나 기존 branch를
Harness 소유로 소급하지 않는다. 인스턴스에 이 계약을 적용할 때는
`guides/UPGRADE.md`의 template-owned 파일 복사, marker가 없는 기존 작업 보존,
doctor·unit test·CI 검증 순서를 따른다.
