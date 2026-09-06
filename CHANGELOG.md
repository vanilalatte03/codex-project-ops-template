# Changelog

이 템플릿 harness 의 `templateVersion`(= `scripts/codex_common.py`의
`TEMPLATE_VERSION`)별 변경 내역입니다. 인스턴스를 업그레이드할 때는 출발 버전과
현재 버전 사이의 항목, 특히 **계약 변화**(hook 설정, profile 키, phase 파일
형식, doctor 검사 등)를 먼저 확인합니다. 절차는
[guides/UPGRADE.md](guides/UPGRADE.md)를 따릅니다.

## 2026.09.04.1

### Added
- `scripts/task_schema.py`와 `docs/TASK_SCHEMA.md`를 추가해 outcome task v2의
  `id`, `objective`, `dependsOn`, `issue`, `risk` 계약과 v1 `steps[]` 호환을
  정의했습니다.
- v2 예제 phase, pre-Codex schema validation, duplicate/dependency/type/status
  오류 테스트를 추가했습니다. v1→v2 자동 migration과 DAG/parallel 실행은
  포함하지 않습니다.

## 2026.09.04.2

### Added
- `scripts/worktree.py`와 `docs/WORKTREE_LIFECYCLE.md`를 추가해 task별 Git
  worktree의 create/list/resume/safe cleanup, owner marker, base ref/SHA와 실패
  보존 계약을 정의했습니다.
- primary checkout을 건드리지 않는 직렬 autopilot 경로와 Windows/stale/실패
  복구·task isolation 검증을 추가합니다.

### Changed
- worktree 소유권이 확인된 merge 성공 task만 force 없는 정리 대상이 되며,
  사용자 branch/worktree와 stale administrative entry는 자동 변경하지 않습니다.
- `execute.py`는 task worktree worker로, `autopilot.py`는 base sync·merge를
  repository lock 아래 직렬 조정 경로로 사용합니다.

## 2026.09.04

### Changed
- Codex 실행 명령의 환경 상속을 `core`로 줄이고, 공식 기본 secret-name 제외
  정책을 활성화했습니다. 프로젝트별 non-secret runtime 환경 변수는
  `.codex/config.toml`의 `shell_environment_policy.filters`에서 명시적으로
  확장합니다.
- guardrail prompt를 progressive disclosure 방식으로 전환했습니다. prompt에는
  작업 계약과 직접 읽을 경로만 전달하고, 선택 경로의 누락·판독 불가 상태는
  Codex 호출 전에 진단합니다.

## 2026.06.17

### Added
- `scripts/upgrade.py`: 템플릿 체크아웃에서 인스턴스로 harness 를 동기화하는
  스크립트. 템플릿 소유 단위를 통째로 덮어쓰고 프로젝트 소유 파일은 보존하며
  `templateVersion` 을 자동으로 갱신합니다. `--dry-run` 으로 변경 사항을 미리
  확인할 수 있습니다.
- `LICENSE`: MIT 라이선스.
- `CHANGELOG.md`: 버전별 변경 내역 기록 시작.

### Changed
- 계약 변화: `scripts/doctor.py` 의 `REQUIRED_FILES` 에 `scripts/upgrade.py` 가
  추가되었습니다. 이 버전으로 업그레이드한 인스턴스는 `scripts/` 를 통째로
  덮어쓰면서 `upgrade.py` 를 함께 받습니다.

## 2026.06.12

- 기준 버전. 이전 변경 내역은 git 로그를 참고합니다.
