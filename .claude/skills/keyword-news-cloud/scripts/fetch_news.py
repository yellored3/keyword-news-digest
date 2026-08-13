#!/usr/bin/env python3
# NAVER API HUB 뉴스 검색 — 이 저장소 전용 고정 키워드로 수집·중복제거까지 담당한다.
# fastcampus-cc의 keyword-news 스킬(scripts/fetch_news.py)에서 그대로 가져왔다 — 무인
# 실행(--auto, 요일·공휴일 기반 자동 기간계산)만 쓰는 것이 이 저장소의 유일한 실행 경로다.
# 출력은 stdout에 JSON 한 덩어리. 에러/경고는 stderr.
import sys
import os
import json
import re
import html
import argparse
import urllib.request
import urllib.parse
import urllib.error
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

MAX_PAGES_PER_KEYWORD = 5  # display=100 * 5 = 최대 500건/키워드, 고빈도 키워드의 API 폭주 방지 안전장치
NAVER_START_LIMIT = 1000  # NAVER API HUB 문서상 start 파라미터 최대값

KST = timezone(timedelta(hours=9))
API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def load_env():
    """.env를 프로젝트 루트/현재 디렉토리에서 찾아 수동 파싱한다 (외부 의존성 없이).
    클라우드 루틴에서는 보통 .env가 없고 Environment의 환경변수로 바로 주입되므로,
    못 찾아도 조용히 넘어간다 (이후 os.environ.get이 실제 값을 읽는다)."""
    for candidate in (os.path.join(os.getcwd(), ".env"), os.path.join(SKILL_DIR, ".env")):
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
            break


def get_holiday_set(years):
    """holidays 라이브러리가 있으면 공휴일 집합을 반환, 없으면 빈 집합 + 경고."""
    try:
        import holidays  # type: ignore
        kr = holidays.KR(years=years)
        return set(kr.keys())
    except ImportError:
        print(
            "[경고] 'holidays' 패키지가 없어 공휴일 미반영 — 요일 로직만 적용됩니다. "
            "정확도를 높이려면: pip install holidays",
            file=sys.stderr,
        )
        return set()


def compute_period(scheduled_date):
    """예정 실행일 기준 검색 기간을 계산한다.
    어제부터 거슬러 올라가며 주말/공휴일을 건너뛰어 '가장 최근 영업일'을 찾고,
    그 영업일 00:00부터 오늘 00:00까지를 검색 기간으로 잡는다. 화~금은 자동으로
    전일 하루치, 월요일이나 연휴 다음 날은 자동으로 주말·연휴 전체가 포함된다.
    """
    holidays_set = get_holiday_set([scheduled_date.year - 1, scheduled_date.year])

    def is_business_day(d):
        return d.weekday() < 5 and d not in holidays_set

    cursor = scheduled_date - timedelta(days=1)
    max_lookback = scheduled_date - timedelta(days=10)  # 무한루프 방지 가드
    while not is_business_day(cursor) and cursor > max_lookback:
        cursor -= timedelta(days=1)
    start = cursor

    period_start = datetime.combine(start, datetime.min.time(), tzinfo=KST)
    period_end = datetime.combine(scheduled_date, datetime.min.time(), tzinfo=KST)
    return period_start, period_end


def call_api(query, client_id, client_secret, display=100, start=1, sort="date", retries=3):
    params = urllib.parse.urlencode({"query": query, "display": display, "start": start, "sort": sort, "format": "json"})
    url = f"{API_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    })
    backoff = 1
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            print(f"[재시도 {attempt}/{retries}] '{query}' 호출 실패: {e}", file=sys.stderr)
            time.sleep(backoff)
            backoff *= 2
    print(f"[실패] '{query}' 최종 실패, 이 키워드는 건너뜁니다: {last_err}", file=sys.stderr)
    return None


def fetch_keyword_items(keyword, client_id, client_secret, period_start, period_end, sort):
    """sort=date면 최신순 페이지네이션 중 기간보다 오래된 기사가 나오는 순간 중단한다 (호출 절약).
    sort=sim(정확도순)은 시간 순서가 보장되지 않으므로 조기 중단 없이 MAX_PAGES까지 모두 훑고
    이후 기간으로 필터링한다.
    """
    items = []
    start = 1
    while start <= NAVER_START_LIMIT and start <= (MAX_PAGES_PER_KEYWORD - 1) * 100 + 1:
        data = call_api(keyword, client_id, client_secret, display=100, start=start, sort=sort)
        if not data:
            break
        page_items = data.get("items", [])
        if not page_items:
            break

        if sort == "date":
            reached_older_than_period = False
            for item in page_items:
                pubdate = parse_pubdate(item.get("pubDate", ""))
                if pubdate is None:
                    continue
                if pubdate >= period_end:
                    continue  # 아직 기간보다 최신 — 건너뛰고 계속 훑는다
                if pubdate < period_start:
                    reached_older_than_period = True
                    break  # 최신순 정렬이므로 여기서부터는 전부 기간 이전
                items.append(item)
            if reached_older_than_period or len(page_items) < 100:
                break
        else:
            items.extend(page_items)
            if len(page_items) < 100:
                break

        start += 100

    if start > (MAX_PAGES_PER_KEYWORD - 1) * 100 + 1:
        print(
            f"[안내] '{keyword}'는 발행량이 많아 최대 {MAX_PAGES_PER_KEYWORD * 100}건까지만 훑고 중단했습니다 "
            f"(기간 시작까지 못 미쳤을 수 있음).",
            file=sys.stderr,
        )
    return items


def clean_tags(text):
    return html.unescape(re.sub(r"</?b>", "", text or ""))


def parse_pubdate(pubdate_str):
    # 예: "Mon, 03 Aug 2026 09:00:00 +0900"
    try:
        return datetime.strptime(pubdate_str, "%a, %d %b %Y %H:%M:%S %z")
    except ValueError:
        return None


def is_duplicate(article, seen):
    """URL 완전일치 또는 제목 유사도 0.85 이상이면 중복으로 본다."""
    if article["link"] in seen["urls"] or article["originallink"] in seen["urls"]:
        return True
    for existing_title in seen["titles"]:
        if SequenceMatcher(None, article["title"], existing_title).ratio() >= 0.85:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="NAVER API HUB 키워드 뉴스 수집 (결정론 구간)")
    parser.add_argument("--keywords", required=True, help="검색 키워드, 쉼표로 여러 개 구분 가능")
    parser.add_argument("--sort", choices=["date", "sim"], default="date", help="date=최신순(기본), sim=정확도순")
    parser.add_argument("--start", help="검색 시작일 YYYY-MM-DD (포함). --auto 미사용 시 필수")
    parser.add_argument("--end", help="검색 종료일 YYYY-MM-DD (포함). --auto 미사용 시 필수")
    parser.add_argument("--auto", action="store_true", help="요일·공휴일 기반 자동 기간계산 사용 (이 저장소의 기본 실행 방식)")
    parser.add_argument("--date", help="--auto 기준 실행일 YYYY-MM-DD (기본: 오늘, KST)", default=None)
    args = parser.parse_args()

    if not args.auto and (not args.start or not args.end):
        parser.error("--auto를 쓰지 않으면 --start와 --end가 필요합니다")

    load_env()
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[에러] NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not keywords:
        print("[에러] 유효한 키워드가 없습니다.", file=sys.stderr)
        sys.exit(1)

    if args.auto:
        scheduled_date = (
            datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(KST).date()
        )
        period_start, period_end = compute_period(scheduled_date)
    else:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
        period_start = datetime.combine(start_date, datetime.min.time(), tzinfo=KST)
        period_end = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=KST)

    seen = {"urls": set(), "titles": []}
    collected = []

    for keyword in keywords:
        page_items = fetch_keyword_items(keyword, client_id, client_secret, period_start, period_end, args.sort)
        for item in page_items:
            title = clean_tags(item.get("title", ""))
            description = clean_tags(item.get("description", ""))
            link = item.get("link", "")
            originallink = item.get("originallink", link)
            pubdate = parse_pubdate(item.get("pubDate", ""))
            if pubdate is None or not (period_start <= pubdate < period_end):
                continue
            article = {
                "title": title,
                "description": description,
                "link": link,
                "originallink": originallink,
                "pubDate": item.get("pubDate", ""),
                "matched_keyword": keyword,
            }
            if is_duplicate(article, seen):
                continue
            seen["urls"].add(link)
            seen["urls"].add(originallink)
            seen["titles"].append(title)
            collected.append(article)

    result = {
        "keywords": keywords,
        "sort": args.sort,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_collected": len(collected),
        "status": "empty" if not collected else "ok",
        "articles": collected,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
