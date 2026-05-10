# eJARN 2605 크롤링 실행 가이드

## 목적

2026년 4월 15일부터 현재 기준일인 2026년 5월 10일까지의 eJARN 기사를 수집하고, 결과를 `result/2605/` 폴더에 JSON 파일로 저장합니다.

## 실행 전 확인

- `.env`에 `EJARN_LOGIN_EMAIL`과 `EJARN_LOGIN_PASSWORD`가 있어야 합니다.
- `.env`에 `OPENAI_API_KEY`가 있으면 요약/분류 기능을 사용할 수 있습니다.
- 실행 중 Chrome 창에서 로그인과 hCaptcha를 직접 완료해야 합니다.

## 추천 실행 명령

```powershell
python main.py --batch-all-sections --since 2026-04-15 --until 2026-05-10 --result-subdir 2605 --batch-section-max 10
```

## 옵션 설명

- `--batch-all-sections`: 8개 섹션을 일괄 수집합니다.
- `--since 2026-04-15`: 2026년 4월 15일 이상 게시글만 수집합니다.
- `--until 2026-05-10`: 2026년 5월 10일 이하 게시글만 수집합니다.
- `--result-subdir 2605`: 결과를 `result/2605/`에 저장합니다.
- `--batch-section-max 10`: 섹션별 최대 10건까지 저장합니다.

## 저장 예상 파일

```text
result/2605/eJarn_News_2605.json
result/2605/Cover_Story_2605.json
result/2605/Event_Exhibition_2605.json
result/2605/Report_2605.json
result/2605/Special_Issue_2605.json
result/2605/Regular_Issue_2605.json
result/2605/Jarn_Regular_2605.json
result/2605/Jarn_Special_2605.json
```

## 실행 흐름

1. 위 명령어를 터미널에서 실행합니다.
2. Chrome 창이 열리면 eJARN 로그인을 완료합니다.
3. hCaptcha가 나오면 직접 해결합니다.
4. 터미널 안내에 따라 `완료`를 입력합니다.
5. 수집이 끝나면 `result/2605/` 폴더의 JSON 파일을 확인합니다.

## 테스트 실행

처음에는 아래처럼 섹션별 2건만 수집해 확인하는 것을 권장합니다.

```powershell
python main.py --batch-all-sections --since 2026-04-15 --until 2026-05-10 --result-subdir 2605 --batch-section-max 2
```

문제가 없으면 `--batch-section-max 10` 또는 필요한 숫자로 늘려 본 실행을 진행합니다.
