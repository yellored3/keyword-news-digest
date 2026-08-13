# 취업시장과 AI — 뉴스 인사이트 아카이브

`keyword-news-cloud` 스킬(`.claude/skills/keyword-news-cloud/`)이 평일 오전 8시(KST) 클라우드 스케줄 루틴으로 실행되며, NAVER API HUB에서 "취업시장과 AI" 키워드로 전일 뉴스를 모아 교차비교 인사이트를 뽑아 발행한다.

발행 결과는 GitHub Pages로 공개된다: `index.html`이 아카이브 목록, `{YYYY-MM}/{YYYYMMDD}.html`이 회차별 뉴스레터, `archive/{YYYYMMDD}.json`이 다음 회차 diff 비교용 원본 데이터다.

- 원본(대화형) 스킬: [`yellored3/fastcampus-cc`](https://github.com/yellored3/fastcampus-cc)의 `.claude/skills/keyword-news/`
- 이 저장소는 그 스킬을 "취업시장과 AI" 키워드 전용, 무인 실행 전용으로 단순화한 버전만 담는다.
