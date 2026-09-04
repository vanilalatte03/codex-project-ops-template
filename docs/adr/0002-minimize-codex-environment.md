# ADR-0002: Codex subprocess 환경 상속 최소화

- 상태: Accepted
- 날짜: 2026-09-04
- 관련 이슈: #14

## 문맥

Harness의 Codex 실행 명령은 이전에 `shell_environment_policy.inherit=all`을
명시해 부모 환경 전체를 Codex subprocess에 노출했다. 실행 파일 탐색은 현재
프로세스의 `PATH`와 플랫폼별 `codex` 후보를 사용해야 하지만, 인증·토큰 이름의
환경 변수까지 명령 환경에 넓게 전달할 필요는 없다.

## 결정

1. `scripts/codex_common.py`의 공통 명령 생성기는
   `shell_environment_policy.inherit="core"`를 사용한다. `execute.py`의 구현
   호출과 `autopilot.py`의 review/fix 호출이 같은 생성기를 공유한다.
2. `shell_environment_policy.ignore_default_excludes=false`를 명시한다. 이 값은
   Codex의 공식 기본 secret-name 제외 규칙을 켜며, credential 값을 Harness가
   직접 다루거나 재구성하지 않는다.
3. 프로젝트별 non-secret runtime 확장은 프로젝트 루트
   `.codex/config.toml`의 `[shell_environment_policy.filters]`에서 변수 이름으로
   선언한다. `include`가 allowlist를 만들 수 있으므로 `PATH`와 필요한 core
   변수도 함께 명시해야 한다.
4. 기존 legacy `include_only`/`exclude` 배열이나 사용자 전역 Codex 설정은
   사용하지 않는다. 플랫폼별 `shutil.which` 후보 탐색은 변경하지 않는다.

공식 설정 의미는 [Codex Configuration Reference](https://developers.openai.com/codex/config-reference/)
및 [Config basics](https://developers.openai.com/codex/config-basic/)를 따른다.

## 결과와 한계

- 기본 실행은 core 환경과 `PATH`를 유지하면서 부모 환경 전체 상속을 피한다.
- 공식 기본 제외 규칙에 따라 secret-name 변수는 Codex shell 환경에 전달되지
  않는다. 프로젝트가 allowlist를 추가할 때에는 이름만 검토해야 한다.
- `.codex/config.toml`은 템플릿의 설정 확장 지점이므로 업그레이드 시
  `guides/UPGRADE.md`의 소유 구분과 프로젝트별 설정을 함께 검토한다.
- 이 결정은 Codex CLI 자체의 인증 저장 방식이나 부모 Python 프로세스의 인증
  환경을 변경하지 않는다. 즉, Codex를 시작하는 데 필요한 인증 경계는 기존
  동작으로 남긴다.

## 검증

- 공통 명령에 `core`와 기본 secret-name 제외 설정이 포함되고 `inherit=all` 및
  legacy 키가 사라졌는지 단위 테스트로 확인한다.
- Windows, macOS, Linux 후보에 대해 `PATH` 기반 `codex` runtime 탐색 계약을
  parameterized test로 확인한다.
- 프로젝트 config의 filters 확장 테이블과 secret-name fixture가 credential
  값을 포함하지 않는지 확인한다.
