---
name: keyword-news-cloud
description: Unattended, cloud-schedule-only variant of keyword-news. No AskUserQuestion anywhere — keyword, sort, report style, and insight count are all fixed in assets/config.json. Triggered exclusively by a Claude Code cloud routine's cron prompt (never by a human typing in a chat), since this repository exists for one purpose only — the daily "취업시장과 AI" digest published via GitHub Pages.
---
# keyword-news-cloud — 무인 실행 전용 키워드 뉴스 인사이트 뉴스레터

> `fastcampus-cc`의 `keyword-news` 스킬(대화형, 매번 키워드를 물어봄)을 이 저장소 전용으로 단순화한 버전이다. 이 저장소는 오직 하나의 고정 키워드(`assets/config.json`의 `keyword`)만 다루고, 사람이 답할 수 없는 클라우드 스케줄 루틴에서만 호출되므로 `AskUserQuestion`을 아예 쓰지 않는다. 매 실행 결과는 이 저장소에 커밋+푸시되고, GitHub Pages로 공개된다.

## 사전 준비

`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`이 실행 환경의 환경변수로 주입돼 있어야 한다 (클라우드 루틴을 만들 때 사용한 Environment 설정에서 등록 — 이 저장소에는 `.env` 파일을 두지 않는다, 공개 저장소이기 때문).

## 워크플로우

### Step 1: 설정 로드

**타입**: script

`assets/config.json`을 읽어 `keyword`, `sort`, `insight_count`, `insight_count_minimum`, `report_style`, `role_tags`를 확정한다. 질문은 하지 않는다 — 값이 곧 이 저장소의 정체성이다.

### Step 2: 뉴스 수집

**타입**: script

```
python3 .claude/skills/keyword-news-cloud/scripts/fetch_news.py --keywords "<config.json의 keyword>" --sort date --auto
```

`--auto`가 요일·공휴일 기반 자동 기간계산(전 영업일 00:00 ~ 실행일 00:00, KST)을 수행한다. 결과는 stdout JSON. `result.status`가 `"empty"`이면 Step 3~6을 건너뛰고 바로 Step 7로 가서 "해당 기간 이슈 없음" 안내만 발행한다 — 억지로 인사이트를 채우지 않는다.

### Step 3: 이슈 클러스터링

**타입**: prompt

전체 기사를 토픽(사건) 단위로 묶는다. 각 클러스터의 기사 수·고유 매체 수를 기록한다 — 매체 1~2개는 화제성 낮은 "단신"으로 표시한다.

### Step 4: 원문 보강

**타입**: api_mcp

매체 3개 이상이거나 인사이트 후보로 유력한 상위 클러스터만 WebFetch로 `originallink` 원문을 확인한다. 전수 조사하지 않는다.

### Step 5: 인사이트 도출

**타입**: prompt

`insight_count`(기본 5) 개를 뽑되 `insight_count_minimum`(기본 5) 미만으로 내려가지 않는다. 원인/변화/함의 중 최소 1개를 답하지 못하면 인사이트로 인정하지 않는다 — 사실 나열은 인사이트가 아니다. 상위 클러스터가 부족하면 "단신" 등급까지 재검토해 최소치를 채운다.

이전 회차 아카이브(`archive/` 아래 가장 최근 JSON)를 Read로 읽어 "신규 등장"/"언급 급감"이 있으면 인사이트에 반영한다.

### Step 6: 액션 태그 부착 + self-check

**타입**: prompt / review

각 인사이트에 액션 제안 한 줄, `role_tags` 중 관련 태그, 중요도(★~★★★)를 붙인다. 그다음 Step 4에서 확보한 원문과 인사이트를 다시 대조해 원문에 없는 주장은 수정·제거한다.

### Step 7: 발행 + 커밋 + 푸시

**타입**: generate

루트의 `index.html`을 참고해 새 HTML을 생성한다. 저장 위치는 저장소 루트 기준:

- `{YYYY-MM}/{YYYYMMDD}.html` — 오늘의 뉴스레터
- `archive/{YYYYMMDD}.json` — 클러스터·인사이트 요약 (다음 회차 diff용)
- `index.html` — 아카이브 목록 맨 위에 새 항목 추가 (날짜 역순 유지)

저장 후 HTML이 비어있지 않은지, `</html>`로 잘 닫혔는지 확인한다. 그다음:

```
git add -A
git commit -m "chore: <YYYY-MM-DD> 취업시장과 AI 뉴스 인사이트 발행"
git push
```

커밋 메시지는 항상 이 형식을 따른다 — 매일 쌓이는 로그이므로 일관성이 검색성보다 중요하다. 커밋에 실패하면(네트워크 등) 에러를 그대로 삼키지 말고 세션 로그에 남긴다.

## Assets

- **`assets/config.json`** — 고정 키워드·정렬·인사이트 개수·리포트 스타일·역할 태그. 이 값을 바꾸려면 사람이 직접 이 파일을 편집하고 커밋해야 한다 (실행 중 절대 스스로 바꾸지 않는다).

## Scripts

- **`scripts/fetch_news.py`** — `fastcampus-cc`의 `keyword-news` 스킬과 동일한 스크립트. `--auto`만 쓴다.

## fastcampus-cc/keyword-news와의 차이

- 대화형 질문(Step 0/8, `AskUserQuestion`)이 전혀 없다 — 모든 값이 `assets/config.json`에 고정.
- 저장 경로에 키워드 슬러그 폴더가 없다 — 저장소 자체가 이미 그 키워드 전용이므로 루트에 바로 저장한다.
- 발행 후 `git add/commit/push`까지 이 스킬의 일부다 — `fastcampus-cc`의 `keyword-news`는 저장까지만 하고 커밋은 사람이 한다.
