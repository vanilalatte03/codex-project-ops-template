# Phase Issues

phase 검증 또는 리뷰가 통과하지 못하면 이 디렉터리에 실패 기록을 남깁니다.
`scripts/autopilot.py`는 step PR gate가 실패했을 때 GitHub Issue와 같은 내용의
로컬 기록을 자동으로 생성합니다.

파일 경로:

```text
issues/{phase-name}/issue-N.md
```

권장 형식:

````markdown
# Issue N: <짧은 제목>

## 발생 위치
- Phase: <phase-name>
- Step: <step-number 또는 review>
- PR: <GitHub PR URL>

## 재현 명령
```bash
<실패한 명령>
```

## 핵심 에러
<가장 중요한 에러 메시지 또는 관찰 결과>

## 수정 방향
- <fix step에서 처리할 작업>

## 완료 기준
- <수정 후 통과해야 할 명령 또는 리뷰 기준>
````

자동 리뷰 실패는 같은 PR 브랜치에서 수정합니다. 재시도 후 gate를 통과하면
기록 하단에 해결 내용을 추가하고, 통과하지 못하면 PR과 Issue를 열어둔 채
후속 작업의 기준으로 사용합니다.
