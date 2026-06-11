# Phase: 0-example

> 이 디렉터리는 Harness skill이 생성하는 phase 파일의 **형식 예시**입니다.
> 실행 대상이 아니라 참고용이며, 실제 phase는 Plan Mode에서 Harness skill로 생성합니다.
> `python scripts/doctor.py --template`이 이 예시의 스키마를 검증하므로,
> 파일 형식을 바꿀 때는 예시도 함께 갱신합니다.

가상의 최소 프로젝트(로컬 메모 CLI)를 기준으로 작성한 예시입니다.

## 목표

- 사용자가 터미널에서 메모를 추가하고 목록을 확인할 수 있는 최소 CLI를 제공한다.

## 작업 범위

- Must-have: 메모 추가 명령, 메모 목록 명령, 로컬 JSON 파일 저장

## 제외 범위

- 메모 삭제, 검색, 태그 기능
- 원격 저장소 연동과 계정/인증

## Steps

| Step | Name | Range |
| ---: | --- | --- |
| 0 | project-setup | Must-have |
| 1 | note-commands | Must-have |

## Step PR 리뷰 원칙

- 각 step PR의 리뷰 기준은 현재 `stepN.md`의 작업, 인수 기준, 금지사항이다.
- 미래 step에 배정된 기능이 아직 없다는 사실은 현재 step의 blocker가 아니다.
- 현재 step이 미래 step 범위를 선행 구현하면 blocker로 본다.
- 리뷰 실패는 같은 PR 브랜치에서 수정하고 `issues/0-example/issue-N.md`에 기록한다.

## 완료 기준

- 메모 추가/목록 명령이 동작하고 모든 step의 인수 기준이 통과한다.
- `python scripts/checks.py --stage final`이 통과한다.

## 검증 명령

```bash
python scripts/checks.py --stage manual
```
