# 프로젝트 작업 에이전트 문서

## 기본 원칙

- 오버엔지니어링하지 않고 필요한 작업만 수행합니다.
- 설명은 한글로 간결하게 작성합니다.
- 초중급자도 이해할 수 있도록 주요 명령과 목적을 쉽게 설명합니다.
- 실제 크롤링 실행 전에는 저장 위치, 날짜 범위, 실행 옵션을 먼저 확인합니다.

## 현재 문서 구성

| 경로 | 용도 |
| --- | --- |
| `README.md` | 프로젝트 전체 사용법과 기본 실행 안내 |
| `DESIGN.md` | 프로젝트 설계와 구조 설명 |
| `READ_JARN페이지구성.md` | eJARN 페이지 구성 관련 메모 |
| `docs/ejarn_2605_crawling_guide.md` | 2026-04-15부터 2026-05-10까지 수집하여 `result/2605/`에 저장하는 실행 가이드 |

## 2605 크롤링 작업 기준

- 대상 기간: 2026-04-15 ~ 2026-05-10
- 저장 폴더: `result/2605/`
- 실행 모드: `main.py --batch-all-sections`
- 저장 형식: 섹션별 JSON 파일
- 상세 절차 문서: `docs/ejarn_2605_crawling_guide.md`

## 권장 실행 전 확인

1. `.env`에 `EJARN_LOGIN_EMAIL`, `EJARN_LOGIN_PASSWORD`가 있는지 확인합니다.
2. LLM 요약/분류를 사용할 경우 `.env`의 `OPENAI_API_KEY`를 확인합니다.
3. 테스트 실행은 `--batch-section-max 2`로 먼저 진행합니다.
4. 문제가 없으면 `--batch-section-max 10` 이상으로 본 실행합니다.

## 추천 명령

테스트 실행:

```powershell
python main.py --batch-all-sections --since 2026-04-15 --until 2026-05-10 --result-subdir 2605 --batch-section-max 2
```

본 실행:

```powershell
python main.py --batch-all-sections --since 2026-04-15 --until 2026-05-10 --result-subdir 2605 --batch-section-max 10
```
