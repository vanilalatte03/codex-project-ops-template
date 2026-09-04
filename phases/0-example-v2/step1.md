# 단계 1: outcome-check

## 읽어야 할 파일

- `/docs/TASK_SCHEMA.md`
- `/phases/0-example-v2/index.json`

## 작업

앞 task가 남긴 예시 결과를 확인한다.

## 인수 기준

```powershell
python scripts/checks.py --stage manual
```

## 금지사항

- 기존 v1 phase index를 자동으로 다시 쓰지 마라. 이유: migration은 명시적
  opt-in 작업으로만 허용된다.
