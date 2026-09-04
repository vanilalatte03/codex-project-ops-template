# Phase: 0-example-v2

## 목표

- v2 outcome task와 v1 실행기의 호환 형태를 보여준다.

## 작업 범위

- `index.json`의 `tasks[]`에 결과 목표, 의존성, Issue와 위험도 메타데이터를
  기록한다.
- 현재 Harness는 배열 순서를 그대로 따라 한 번에 하나의 task를 실행한다.

## 제외 범위

- `dependsOn`을 이용한 DAG 스케줄링, ready set 계산, 병렬 실행은 이 예시에
  포함하지 않는다.
- 기존 phase 파일을 v2로 자동 변환하지 않는다.

## Steps

| 순서 | Task id | 결과 목표 | 상태 |
| ---: | --- | --- | --- |
| 0 | project-setup | 프로젝트 골격을 준비한다 | pending |
| 1 | outcome-check | 예시 결과를 확인한다 | pending |

## 완료 기준

- 두 task가 선언된 배열 순서대로 실행된다.
- v2 필수 필드와 dependency reference가 schema validator를 통과한다.

## 검증 명령

```powershell
python scripts/checks.py --stage manual
```
