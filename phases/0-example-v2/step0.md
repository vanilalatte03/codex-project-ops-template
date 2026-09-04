# 단계 0: project-setup

## 읽어야 할 파일

- `/docs/TASK_SCHEMA.md`
- `/phases/0-example-v2/README.md`

## 작업

예시 프로젝트 골격을 준비한다.

## 인수 기준

```powershell
python scripts/checks.py --stage manual
```

## 금지사항

- `dependsOn`을 스케줄러로 해석하거나 병렬 실행을 추가하지 마라. 이유: 이
  예시는 현재의 직렬 실행 계약만 보여준다.
