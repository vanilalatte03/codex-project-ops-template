# 배포용 템플릿 파일 목록과 검증 계약

Issue #39의 고정 입력은 `origin/develop`의
`22b2d5141f7135904c73460e4308df2c4138806f`이다. 이 문서는 배포본의
파일 경계를 정한다. 실제 파일 제거, 변환, `main` 반영은 후속 PR에서 한다.
기계 판정의 기준은 [DISTRIBUTION_MANIFEST.json](DISTRIBUTION_MANIFEST.json)이다.
그 파일은 소스 commit의 tracked 파일 150개를 각 경로 또는 명시적 glob으로
정확히 한 번 분류한다. 현재 판정은 포함 59개, 제외 80개, 초기화·변환 11개다.
이 PR에서 새로 만드는 `docs/DISTRIBUTION_MANIFEST.md`,
`docs/DISTRIBUTION_MANIFEST.json`, `scripts/verify_distribution_manifest.py`,
`scripts/tests/test_distribution_manifest.py`는 고정 commit에 없으며
배포 검토용 저장소 파일이다. 후속 PR에서 최신 파일 목록을 비교할 때는
이 네 파일을 제외하고 `README.md`의 이 문서 링크도 정리한다.

| 판정 | 의미 | 소유자 |
| --- | --- | --- |
| `include` | 바이트 그대로 배포 후보에 포함 | `template`은 업그레이드 원본, `new-project`는 복사 후 프로젝트가 관리 |
| `exclude` | 새 프로젝트에 복사하지 않음 | `template-repository`는 이 저장소에만 남음 |
| `transform` | 배포 전에 명시한 변경을 적용해 포함 | 규칙의 `owner`가 최종 소유자 |

## 판정의 핵심

- Harness 실행 코드, 공통 skill, hook, 설정, v1/v2 예시 phase,
  `docs/TASK_SCHEMA.md`, `docs/REVIEW_POLICY.md`,
  `docs/RUN_STATE.md`, `docs/WORKTREE_LIFECYCLE.md`를 포함한다.
  `scripts/tests`는 공통 Harness 회귀 테스트를 포함하고 아래 평가 전용 테스트만
  제외한다. `requirements-dev.txt`와 `CHANGELOG.md`도 각각 회귀 테스트 설치와
  템플릿 버전 이력을 위해 포함한다.
- `phases/harness-v2-modernization/**`와
  `issues/harness-v2-modernization/**`는 완료된 개발 기록이므로 제외한다.
  `scripts/eval_progressive_guardrails.py`, `scripts/eval_release.py`,
  `scripts/eval_release_contracts.py`, `scripts/sdk_spike.py` 및 해당 전용 테스트도
  제외한다. `.github/workflows/template-ci.yml`과
  `.github/workflows/docs-gardening.yml`은 템플릿 저장소 전용이라 제외한다.
- `docs/adr/0001-*.md`부터 `0006-*.md`까지는 Harness 개발 결정을 기록한다.
  새 프로젝트의 ADR이 아니므로 제외하고 `docs/ADR.md`는 빈 인덱스로 초기화한다.
  새 프로젝트가 따라야 할 실행 계약은 포함하는 `docs/REVIEW_POLICY.md` 등과
  공통 skill에 남는다.
- `docs/PRD.md`와 `AGENTS.md`는 이미 placeholder 골격이므로 그대로 포함한다.
  `.codex/scope-rules.json`은 빈 범위 규칙으로 포함한다.
  `docs/ARCHITECTURE.md`는 Harness 자체 구조를 설명하므로 프로젝트 골격으로
  초기화한다.

## 후속 PR에서 적용할 변환

| 경로 | 필요한 결과 |
| --- | --- |
| `phases/index.json` | `{"phases":[]}`로 초기화. 완료한 Harness phase를 남기지 않는다. |
| `docs/ARCHITECTURE.md`, `docs/ADR.md` | 새 프로젝트용 placeholder 아키텍처와 비어 있는 ADR 인덱스로 바꾼다. 제외된 ADR 링크가 없어야 한다. |
| `docs/adr/.gitkeep` (새 파일) | 빈 ADR 디렉터리를 Git에서 유지한다. 현재 `garden_docs.py`는 이 디렉터리가 없으면 실패한다. |
| `.codex/project-profile.json` | `templateVersion`은 `scripts/codex_common.py`와 일치시킨다. `projectName`, 명령, source/test roots는 새 프로젝트가 채울 골격으로 둔다. |
| `docs/COMMANDS.md` | 일반 Harness 명령 계약은 유지하고 `docs/GARDENING.md`와 저장소 전용 정기 점검 설명을 제거한다. 실제 프로젝트의 test/build 명령은 셋업 단계에서 채운다. |
| `README.md`, `guides/UPGRADE.md` | 템플릿 저장소 전용 CI·gardening 링크와 복사 후 workflow 삭제 안내를 배포 경계에 맞춰 고친다. 아래 복사 경로를 명시한다. |
| `scripts/doctor.py`, `scripts/tests/test_doctor.py` | 새 프로젝트 배포본에서는 제외된 `template-ci.yml` 때문에 template 검사에 실패하지 않게 모드와 fixture를 조정한다. 예시 phase/schema/profile 검사와 instance placeholder 검사는 유지한다. |
| `scripts/upgrade.py`, `scripts/tests/test_upgrade.py` | `TEMPLATE_ONLY`와 fixture의 제외된 workflow 가정을 배포 경계에 맞춰 고친다. 기존 인스턴스에 있는 workflow를 지우는 업그레이드 동작은 별도로 판단한다. |

## 제외 파일 참조의 처리

| 참조 위치 | 현재 참조 | 후속 조치 |
| --- | --- | --- |
| `scripts/tests/test_eval_release_artifacts.py` | `eval-results/**`, `eval_release.py` | 테스트 자체를 제외한다. 실행에 필요한 산출물과 도구도 함께 제외한다. |
| `scripts/tests/test_eval_release.py` | `eval_release.py` | 테스트 자체를 제외한다. |
| `scripts/tests/test_sdk_spike.py` | `sdk_spike.py`, `SDK_SPIKE_RESULTS.json` | 테스트 자체를 제외한다. |
| `docs/adr/0005-python-codex-sdk-spike.md` | `SDK_SPIKE.md`, `SDK_SPIKE_RESULTS.json` | ADR을 제외한다. SDK 실행 계약은 `codex_runner.py`와 공통 운영 문서에서 유지한다. |
| `phases/harness-v2-modernization/**` | 내부 평가 도구·결과·step 간 참조 | phase 전체를 제외한다. |
| `phases/index.json` | 완료 phase 이름 | 빈 인덱스로 초기화한다. |
| `docs/ADR.md` | 제외할 ADR 6개 | 빈 ADR 인덱스로 초기화한다. |
| `docs/COMMANDS.md`, `README.md` | `docs/GARDENING.md` | 정기 점검 설명과 링크를 제거한다. `scripts/garden_docs.py`의 로컬 수동 기능은 유지한다. |
| `docs/GARDENING.md` | `docs-gardening.yml` | 두 파일 모두 제외한다. |
| `README.md`, `guides/UPGRADE.md` | `template-ci.yml` | 배포본 설명을 고친다. |
| `scripts/doctor.py`, `scripts/tests/test_doctor.py` | `template-ci.yml` | 배포본 검증과 fixture를 조정한다. |
| `scripts/upgrade.py`, `scripts/tests/test_upgrade.py` | `template-ci.yml` | 배포본 업그레이드 계약과 fixture를 조정한다. |

이 표는 고정 commit에서 `rg`로 확인한 직접 참조다. 후속 PR에서는 변환 후
전체 파일에서 제외된 경로와 깨진 로컬 링크를 다시 검색해야 한다.

## 복사 경로

GitHub의 [템플릿 생성 문서](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)는
기본 브랜치만 복사하거나 `Include all branches`로 모든 브랜치를 복사할 수
있다고 설명한다. 현재 기본 브랜치 `main`은 이 고정 `develop` 스냅샷이 아니다.
후속 정리 PR에서 배포 파일만 있는 기본 브랜치를 준비한 뒤 **기본 브랜치만
복사**하는 경로를 지원한다. `Include all branches`는 개발·평가 브랜치까지
새 저장소에 가져올 수 있으므로 지원하지 않는다. 정리 PR이 끝나기 전에는
`develop`이나 현재 `main`을 배포본이라고 안내하지 않는다.

## 검증 계약

1. `python scripts/verify_distribution_manifest.py --check-ref`로 고정 commit의
   tracked 파일을 `git ls-tree -r`에서 읽고, 누락·중복·빈 패턴이 없음을 확인한다.
   `--check-ref`는 `origin/develop`이 고정 commit에서 움직였으면 실패시킨다.
   후속 PR에서 소스 commit을 바꾸면 manifest 전체를 재검토한다.
2. 후속 PR의 배포 후보를 **별도의 임시 새 저장소**에 펼친다. manifest의
   `include`는 원본 바이트를 복사하고 `transform`은 위 표의 결과를 적용한다.
   그 저장소에 완료 phase, `issues/harness-v2-modernization`, `eval-results`,
   SDK spike, 두 workflow가 없으며 PRD/AGENTS/ARCHITECTURE/ADR/profile/COMMANDS는
   새 프로젝트가 채울 상태인지 검사한다. 원본 개발 체크아웃은 수정하지 않는다.
3. 배포 후보에서 `python scripts/garden_docs.py`,
   `python scripts/doctor.py --template`, `python -m pytest scripts`를 실행한다.
   `phases/index.json`과 두 예시의 schema, profile
   `templateVersion` 일치 여부, Markdown 로컬 링크를 확인한다.
   `doctor.py --template`는 현재 소스에서는 저장소 전용 CI를 필수로 보므로
   위 변환 전 후보에는 적용되지 않는다.
4. 새 프로젝트 값을 채운 별도 fixture에서는 `AGENTS.md`, PRD,
   ARCHITECTURE, profile projectName, test/build 명령과 Git hook을 준비하고
   `python scripts/doctor.py --instance`를 실행한다.
5. 최종 배포 후보의 추적 파일 목록과 manifest의 include/transform 판정을
   비교하고, 제외 파일이 하나도 없는지 확인한다. README의 복사 안내와
   `git diff --check`를 확인한다.

후속 PR은 위 명령의 성공 출력 또는 실패 로그와 수정 이유를 PR 본문에 남겨야
한다. 이 Issue의 PR은 판정과 검증 계약까지만 확정한다.

## 고정 소스의 예비 검증

- manifest 검증: 150개 경로가 정확히 한 번 분류됐다
  (`include=59`, `exclude=80`, `transform=11`).
- 현재 개발 체크아웃: `python scripts/doctor.py --template` 통과,
  `python scripts/garden_docs.py`에서 변경 필요 0건,
  `python -m pytest scripts`에서 304개 통과.
- 임시 새 저장소에 include/transform 원본 파일만 펼친 후보: 완료 phase,
  이슈 기록, 평가 결과와 두 workflow가 없는 것을 확인했다.
  `python -m pytest scripts -q`는 266개 통과했다. 아직 변환을 적용하지 않았으므로
  `doctor.py --template`은 제외된 `template-ci.yml` 요구로 실패한다.
  `garden_docs.py`는 빈 `docs/adr/`이 Git에 기록되지 않아 실패한다.
  이 두 실패는 위 변환과 새 `.gitkeep` 파일로 해결해야 한다.
- 같은 후보에서 AGENTS/PRD/ARCHITECTURE/ADR/index/profile에 데모 프로젝트 값을
  채우고 Git hook 경로를 설정한 별도 fixture는
  `python scripts/doctor.py --instance`를 통과했다. 이 검증은
  `doctor.py --template`의 배포본 CI 요구 변경까지 증명하지 않는다.
