# Harness 버전과 업그레이드

이 템플릿을 복사한 인스턴스는 시간이 지나면 템플릿과 갈라집니다. 어느 시점의
템플릿에서 출발했는지 추적하기 위해 버전 마커 두 개를 사용합니다.

- `scripts/codex_common.py`의 `TEMPLATE_VERSION`: 설치된 harness의 버전.
  업그레이드로 `scripts/`를 덮어쓰면 자동으로 함께 따라옵니다.
- `.codex/project-profile.json`의 `templateVersion`: 이 인스턴스가 마지막으로
  동기화한 템플릿 버전 기록.

`doctor.py --instance`는 둘이 다르면 실패합니다. harness 파일은 새로 복사했는데
기록을 안 올렸거나, 기록만 올리고 파일을 안 가져온 "절반만 끝난 업그레이드"를
잡습니다.

## 파일 소유 구분

업그레이드의 기본 원칙은 "템플릿 소유 단위는 통째로 덮어쓰고, 프로젝트 소유
단위는 건드리지 않는다"입니다.

| 단위 | 소유 | 업그레이드 시 |
| --- | --- | --- |
| `scripts/` (테스트 포함) | 템플릿 | 통째로 덮어쓰기 |
| `.agents/skills/` | 템플릿 | 통째로 덮어쓰기 |
| `.githooks/`, `.codex/hooks/`, `.codex/hooks.json`, `.codex/config.toml`, `.gitattributes` | 템플릿 | 통째로 덮어쓰기 |
| `guides/PROMPTS.md`, `guides/CONFIGURATION.md`, `guides/UPGRADE.md` | 템플릿 | 통째로 덮어쓰기 |
| `.github/workflows/template-ci.yml` | 템플릿 전용 | 인스턴스에는 복사하지 않음 |
| `AGENTS.md`, `docs/`, `phases/`, `issues/`, `archive/` | 프로젝트 | 덮어쓰지 않음 |
| `.codex/project-profile.json`, `.codex/scope-rules.json`, `phases/*/scope-rules.json` | 프로젝트 | 덮어쓰지 않음. 단 `templateVersion` 키만 갱신 |

`.github/workflows/template-ci.yml`은 템플릿 repo 전용 검증입니다. 실제 프로젝트
인스턴스에는 복사하지 않고, 이미 복사했다면 삭제합니다. 실제 프로젝트의 CI는
`docs/COMMANDS.md`에 확정한 `lint`, `test`, `build` 명령 기준으로 별도 작성합니다.

인스턴스에서 `scripts/` 같은 템플릿 소유 파일을 직접 고치면 다음 업그레이드 때
덮어써 사라집니다. harness 개선이 필요하면 템플릿 repo에 먼저 반영해 버전을
올리고, 업그레이드 절차로 인스턴스에 가져옵니다.

## 업그레이드 절차

1. 인스턴스 `.codex/project-profile.json`의 `templateVersion`과 템플릿 repo의
   현재 `TEMPLATE_VERSION`을 비교하고, 그 사이의 템플릿 커밋 로그에서 계약
   변화(hook 설정, profile 키 추가, phase 파일 형식 변경 등)를 확인합니다.
2. 위 표의 템플릿 소유 단위를 템플릿에서 통째로 복사해 덮어씁니다.
3. 1번에서 확인한 계약 변화가 프로젝트 소유 파일에 영향을 주면 수동으로
   반영합니다.
4. `.codex/project-profile.json`의 `templateVersion`을 새 버전으로 갱신합니다.
5. `python -m pytest scripts`와 `python scripts/doctor.py --instance`가 통과하는지
   확인합니다.

## 템플릿 repo에서 버전 올리기

템플릿 repo에서 harness 동작을 바꾸는 커밋은 `scripts/codex_common.py`의
`TEMPLATE_VERSION`과 `.codex/project-profile.json`의 `templateVersion`을 함께
올립니다. 한쪽만 올리면 `doctor.py --template`(CI)이 실패합니다.
