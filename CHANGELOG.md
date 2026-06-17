# Changelog

이 템플릿 harness 의 `templateVersion`(= `scripts/codex_common.py`의
`TEMPLATE_VERSION`)별 변경 내역입니다. 인스턴스를 업그레이드할 때는 출발 버전과
현재 버전 사이의 항목, 특히 **계약 변화**(hook 설정, profile 키, phase 파일
형식, doctor 검사 등)를 먼저 확인합니다. 절차는
[guides/UPGRADE.md](guides/UPGRADE.md)를 따릅니다.

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
