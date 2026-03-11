"""
naver_monitor.py - 네이버 블로그 신규 글 감지 모듈

RSS 피드를 사용하여 지정된 블로그들의 신규 글을 감지하고,
processed_blogs.json으로 중복을 방지한다.
"""

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

# RSS 피드 URL 템플릿
RSS_URL_TEMPLATE = "https://rss.blog.naver.com/{blog_id}"

# 요청 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NaverBlogBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

# 요청 타임아웃 (초)
REQUEST_TIMEOUT = 15


def get_latest_posts(blog_id: str, max_results: int = 10) -> list[dict]:
    """블로그의 최신 글 목록을 RSS 피드에서 조회한다.

    Args:
        blog_id: 네이버 블로그 ID
        max_results: 조회할 최대 글 수

    Returns:
        글 정보 딕셔너리 리스트
        [{"post_id", "title", "blog_name", "url", "published_at"}, ...]
    """
    rss_url = RSS_URL_TEMPLATE.format(blog_id=blog_id)
    logger.info(f"RSS 피드 조회: {rss_url}")

    try:
        response = requests.get(
            rss_url, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        response.encoding = "utf-8"

    except requests.exceptions.Timeout:
        logger.error(f"RSS 요청 타임아웃 ({REQUEST_TIMEOUT}초): {rss_url}")
        return []
    except requests.exceptions.ConnectionError:
        logger.error(f"RSS 연결 실패: {rss_url}")
        return []
    except requests.exceptions.HTTPError as e:
        logger.error(f"RSS HTTP 에러 ({e.response.status_code}): {rss_url}")
        return []
    except Exception as e:
        logger.error(f"RSS 요청 중 예외 발생: {e}")
        return []

    # RSS XML 파싱
    posts = _parse_rss(response.text, blog_id)
    posts = posts[:max_results]

    logger.info(f"블로그 {blog_id}에서 글 {len(posts)}개 조회 완료")
    return posts


def _parse_rss(xml_text: str, blog_id: str) -> list[dict]:
    """RSS XML을 파싱하여 글 목록을 추출한다.

    Args:
        xml_text: RSS XML 문자열
        blog_id: 네이버 블로그 ID

    Returns:
        글 정보 딕셔너리 리스트
    """
    posts = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"RSS XML 파싱 실패 ({blog_id}): {e}")
        return []

    # RSS 2.0: channel > item
    channel = root.find("channel")
    if channel is None:
        logger.warning(f"RSS channel 요소 없음 ({blog_id})")
        return []

    # 블로그 이름 추출
    blog_name = ""
    title_elem = channel.find("title")
    if title_elem is not None and title_elem.text:
        blog_name = title_elem.text.strip()

    for item in channel.findall("item"):
        post = _parse_item(item, blog_id, blog_name)
        if post:
            posts.append(post)

    return posts


def _parse_item(item: ET.Element, blog_id: str, blog_name: str) -> dict | None:
    """RSS item 요소를 파싱하여 글 정보 딕셔너리를 반환한다.

    Args:
        item: RSS item XML 요소
        blog_id: 네이버 블로그 ID
        blog_name: 블로그 이름

    Returns:
        글 정보 딕셔너리. 파싱 실패 시 None
    """
    # 제목
    title_elem = item.find("title")
    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

    # URL (link)
    link_elem = item.find("link")
    url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

    # 발행일 (pubDate)
    pub_date_elem = item.find("pubDate")
    published_at = ""
    if pub_date_elem is not None and pub_date_elem.text:
        published_at = pub_date_elem.text.strip()

    if not url:
        return None

    # URL에서 post_id(logNo) 추출
    post_id = _extract_post_id(url)
    if not post_id:
        # URL 자체를 ID로 사용 (폴백)
        post_id = url

    return {
        "post_id": post_id,
        "title": title,
        "blog_id": blog_id,
        "blog_name": blog_name,
        "url": url,
        "published_at": published_at,
    }


def _extract_post_id(url: str) -> str | None:
    """네이버 블로그 URL에서 글 번호(logNo)를 추출한다.

    지원 형식:
      - https://blog.naver.com/{blog_id}/{log_no}
      - https://blog.naver.com/PostView.naver?blogId=...&logNo=...

    Args:
        url: 네이버 블로그 글 URL

    Returns:
        글 번호 문자열. 추출 실패 시 None
    """
    # 경로 방식: /blog_id/12345
    match = re.search(r"blog\.naver\.com/[^/]+/(\d+)", url)
    if match:
        return match.group(1)

    # 쿼리 파라미터 방식: logNo=12345
    match = re.search(r"logNo=(\d+)", url)
    if match:
        return match.group(1)

    return None


def load_processed_blogs(processed_path: str) -> set[str]:
    """처리된 블로그 글 ID 집합을 JSON 파일에서 로드한다.

    파일이 없거나 손상된 경우 빈 집합을 반환한다.

    Args:
        processed_path: processed_blogs.json 파일 경로

    Returns:
        처리된 글 ID의 집합
    """
    if not os.path.exists(processed_path):
        logger.info(f"{processed_path} 파일 없음 - 빈 상태로 시작")
        return set()

    try:
        with open(processed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        processed = set(data.get("processed", []))
        logger.info(f"처리 완료 블로그 글 {len(processed)}개 로드됨")
        return processed
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"{processed_path} 파일 손상 - 빈 상태로 초기화: {e}")
        return set()


def filter_new_posts(
    posts: list[dict], processed_path: str, max_age_hours: int = 1
) -> list[dict]:
    """이미 처리된 글을 제외한 신규 글만 반환한다.

    processed_blogs.json이 없는 첫 실행 시에는 최근 max_age_hours 이내에
    발행된 글만 신규로 판정하여, 과거 글 대량 처리를 방지한다.

    Args:
        posts: 글 정보 딕셔너리 리스트
        processed_path: processed_blogs.json 파일 경로
        max_age_hours: 첫 실행 시 신규로 판정할 최대 시간 (기본 1시간)

    Returns:
        신규 글 정보 리스트
    """
    is_first_run = not os.path.exists(processed_path)
    processed = load_processed_blogs(processed_path)
    new_posts = [p for p in posts if p["post_id"] not in processed]

    # 첫 실행 시 날짜 기반 필터링 적용
    if is_first_run and new_posts:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        before_count = len(new_posts)
        new_posts = [p for p in new_posts if _is_recent(p, cutoff)]
        logger.info(
            f"첫 실행 - 최근 {max_age_hours}시간 이내 글만 처리: "
            f"{before_count}개 -> {len(new_posts)}개"
        )

    if new_posts:
        logger.info(f"신규 블로그 글 {len(new_posts)}개 발견")
    else:
        logger.info("신규 블로그 글 없음")

    return new_posts


def _is_recent(post: dict, cutoff: datetime) -> bool:
    """글의 발행일이 cutoff 이후인지 확인한다.

    Args:
        post: 글 정보 딕셔너리 (published_at 포함)
        cutoff: 기준 시각 (UTC)

    Returns:
        cutoff 이후 발행이면 True, 아니면 False.
        발행일 파싱 실패 시 False 반환 (안전하게 건너뜀).
    """
    pub_str = post.get("published_at", "")
    if not pub_str:
        return False

    try:
        # RSS pubDate 형식: "Wed, 11 Mar 2026 07:38:25 +0900"
        pub_dt = parsedate_to_datetime(pub_str)
        # UTC로 변환하여 비교
        pub_utc = pub_dt.astimezone(timezone.utc)
        return pub_utc >= cutoff
    except (ValueError, TypeError) as e:
        logger.warning(f"발행일 파싱 실패 ({pub_str}): {e}")
        return False


def mark_as_processed(post_id: str, processed_path: str) -> None:
    """처리 완료된 글 ID를 JSON 파일에 기록한다.

    Args:
        post_id: 처리 완료된 글 ID (logNo)
        processed_path: processed_blogs.json 파일 경로
    """
    processed = load_processed_blogs(processed_path)
    processed.add(post_id)

    # 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(processed_path) or ".", exist_ok=True)

    data = {
        "processed": sorted(processed),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"블로그 글 {post_id} 처리 완료로 기록됨")
