"""
naver_scraper.py - 네이버 블로그 본문 추출 모듈

네이버 블로그 URL에서 본문 텍스트를 크롤링한다.
모바일 URL(m.blog.naver.com)을 사용하여 iframe 구조를 우회한다.
"""

import logging
import re
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 모바일 블로그 URL 템플릿
MOBILE_BLOG_URL = "https://m.blog.naver.com/{blog_id}/{log_no}"

# 요청 헤더 (봇 차단 방지)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 요청 타임아웃 (초)
REQUEST_TIMEOUT = 15


def parse_blog_url(url: str) -> tuple[str, str] | None:
    """네이버 블로그 URL에서 blog_id와 log_no를 추출한다.

    지원 형식:
      - https://blog.naver.com/{blog_id}/{log_no}
      - https://m.blog.naver.com/{blog_id}/{log_no}
      - https://blog.naver.com/PostView.naver?blogId={}&logNo={}

    Args:
        url: 네이버 블로그 URL

    Returns:
        (blog_id, log_no) 튜플. 파싱 실패 시 None
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if "blog.naver.com" not in host:
            logger.warning(f"네이버 블로그 URL이 아님: {url}")
            return None

        # 쿼리 파라미터 방식: PostView.naver?blogId=xxx&logNo=yyy
        if "PostView" in parsed.path:
            params = parse_qs(parsed.query)
            blog_id = params.get("blogId", [None])[0]
            log_no = params.get("logNo", [None])[0]
            if blog_id and log_no:
                return (blog_id, log_no)
            return None

        # 경로 방식: /blog_id/log_no
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return (parts[0], parts[1])

        return None

    except Exception as e:
        logger.error(f"블로그 URL 파싱 실패 ({url}): {e}")
        return None


def get_blog_text(url: str) -> str | None:
    """네이버 블로그 URL에서 본문 텍스트를 추출한다.

    모바일 URL로 변환하여 요청하고, HTML에서 본문 텍스트만 추출한다.
    이미지, 스티커, 광고 등은 제거된다.

    Args:
        url: 네이버 블로그 URL (PC 또는 모바일)

    Returns:
        본문 텍스트 문자열. 추출 실패 시 None
    """
    # URL 파싱
    parsed = parse_blog_url(url)
    if not parsed:
        logger.error(f"블로그 URL 파싱 실패: {url}")
        return None

    blog_id, log_no = parsed

    # 모바일 URL로 변환 (iframe 우회)
    mobile_url = MOBILE_BLOG_URL.format(blog_id=blog_id, log_no=log_no)
    logger.info(f"블로그 크롤링: {mobile_url}")

    try:
        response = requests.get(
            mobile_url, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        response.encoding = "utf-8"

    except requests.exceptions.Timeout:
        logger.error(f"블로그 요청 타임아웃 ({REQUEST_TIMEOUT}초): {mobile_url}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"블로그 연결 실패: {mobile_url}")
        return None
    except requests.exceptions.HTTPError as e:
        logger.error(f"블로그 HTTP 에러 ({e.response.status_code}): {mobile_url}")
        return None
    except Exception as e:
        logger.error(f"블로그 요청 중 예외 발생: {e}")
        return None

    # HTML 파싱 및 본문 추출
    text = _extract_text_from_html(response.text)
    if text:
        logger.info(f"블로그 본문 추출 완료 ({len(text)}자): {mobile_url}")
    else:
        logger.warning(f"블로그 본문 추출 실패: {mobile_url}")

    return text


def _extract_text_from_html(html: str) -> str | None:
    """HTML에서 블로그 본문 텍스트만 추출한다.

    모바일 네이버 블로그의 본문 컨테이너를 찾아서
    이미지, 스티커, 광고 등을 제거하고 순수 텍스트만 반환한다.

    Args:
        html: 모바일 블로그 페이지 HTML

    Returns:
        정리된 본문 텍스트. 추출 실패 시 None
    """
    soup = BeautifulSoup(html, "html.parser")

    # 모바일 블로그 본문 컨테이너 탐색 (우선순위 순)
    content = None
    selectors = [
        "div.se-main-container",        # 스마트에디터 3 (SE3)
        "div.post_ct",                   # 구형 에디터
        "div.__viewer_container",        # 뷰어 컨테이너
        "div#viewTypeSelector",          # 구형 뷰어
        "div.se_component_wrap",         # SE2
    ]

    for selector in selectors:
        content = soup.select_one(selector)
        if content:
            break

    if not content:
        # 폴백: og:description 메타태그에서 추출
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            text = og_desc["content"].strip()
            if len(text) > 50:
                return text
        logger.warning("블로그 본문 컨테이너를 찾을 수 없음")
        return None

    # 불필요한 요소 제거
    _remove_unwanted_elements(content)

    # 텍스트 추출 및 정리
    text = _clean_text(content)

    if not text or len(text) < 20:
        logger.warning(f"추출된 텍스트가 너무 짧음 ({len(text) if text else 0}자)")
        return None

    return text


def _remove_unwanted_elements(container: BeautifulSoup) -> None:
    """본문에서 불필요한 HTML 요소들을 제거한다.

    이미지, 스티커, 동영상, 광고, 지도, 링크 카드 등을 제거한다.

    Args:
        container: 본문 BeautifulSoup 요소
    """
    # 제거할 CSS 선택자 목록
    remove_selectors = [
        "img",                           # 이미지
        "video",                         # 동영상
        "iframe",                        # 임베드
        "figure.se-image",               # SE3 이미지 블록
        "figure.se-video",               # SE3 동영상 블록
        "figure.se-map",                 # SE3 지도 블록
        "figure.se-sticker",             # SE3 스티커
        "figure.se-ogeneral",            # SE3 링크 카드
        "figure.se-oglink",              # SE3 OG 링크
        "div.se-module-oglink",          # OG 링크 모듈
        "div.se-module-map",             # 지도 모듈
        "div.se-module-video",           # 동영상 모듈
        "div.se-module-image",           # 이미지 모듈
        "div.se-sticker",               # 스티커
        "a.se-link",                     # 링크
        "div._adFoot",                   # 광고
        "div.ad_area",                   # 광고 영역
        "script",                        # 스크립트
        "style",                         # 스타일
        "noscript",                      # noscript
        "button",                        # 버튼
        "span.se-fs-",                   # 폰트 크기 태그 (빈 요소)
    ]

    for selector in remove_selectors:
        for element in container.select(selector):
            element.decompose()


def _clean_text(container: BeautifulSoup) -> str:
    """BeautifulSoup 요소에서 텍스트를 추출하고 정리한다.

    연속 공백, 빈 줄 등을 정리하여 깔끔한 텍스트를 반환한다.

    Args:
        container: 본문 BeautifulSoup 요소

    Returns:
        정리된 텍스트 문자열
    """
    # 블록 요소 앞에 줄바꿈 삽입
    block_tags = ["p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "blockquote", "section"]
    for tag in container.find_all(block_tags):
        tag.insert_before("\n")

    # 텍스트 추출
    text = container.get_text()

    # 정리
    # 1. \xa0 (non-breaking space) 제거
    text = text.replace("\xa0", " ")
    # 2. 탭 → 공백
    text = text.replace("\t", " ")
    # 3. 연속 공백 → 단일 공백 (줄바꿈은 유지)
    text = re.sub(r"[^\S\n]+", " ", text)
    # 4. 3개 이상 연속 줄바꿈 → 2개
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 5. 각 줄 양쪽 공백 제거
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # 6. 앞뒤 공백 제거
    text = text.strip()

    return text
