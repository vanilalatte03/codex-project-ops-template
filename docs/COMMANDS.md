# Commands

이 파일은 프로젝트 실행 명령의 단일 출처입니다. Plan Mode에서 기술 스택을
확정한 뒤 실제 명령으로 채웁니다. 비어 있는 명령은 실행하지 않습니다.
`test`와 `build`는 필수 gate입니다. 둘 중 하나라도 비어 있거나 감지되지 않으면
`scripts/checks.py --stage manual`과 autopilot review gate가 실패합니다.

## 활성 명령

| 이름 | 명령 | 필수 | 설명 |
| --- | --- | --- | --- |
| dev |  | no | 개발 서버 또는 watch 실행 |
| lint |  | no | 정적 분석과 포맷 검사 |
| test |  | yes | 자동 테스트 |
| build |  | yes | 배포 가능한 빌드 또는 패키징 |
| review | `python3 scripts/doctor.py --template` | no | 템플릿 원본 구조 점검 |
| phase | `python3 scripts/execute.py <phase-name>` | no | Harness phase 실행 |
| phase-step | `python3 scripts/execute.py <phase-name> --next-step-only` | no | 다음 pending step만 실행 |
| autopilot | `python3 scripts/autopilot.py <phase-name> --base main --max-review-fixes 2` | no | step별 PR 생성, 자체 리뷰, 이슈 기록, 자동 병합 루프 |

## 기술별 예시

```bash
# Spring Boot - Gradle
./gradlew test
./gradlew build

# Spring Boot - Maven
./mvnw test
./mvnw package

# Python
uv run pytest
uv run ruff check .
python -m pytest

# Node
npm run lint
npm test
npm run build
pnpm test
yarn test
```
