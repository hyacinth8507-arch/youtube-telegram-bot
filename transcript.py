"""
transcript.py -- YouTube 자막 추출 모듈

youtube-transcript-api를 사용하여 영상의 자막을 추출한다.
한국어(ko) 자막을 우선 시도하고, 없으면 영어(en) 자막을 추출한다.
RequestBlocked 발생 시 yt-dlp를 폴백으로 사용한다.
"""

import glob
import logging
import os
import re
import subprocess
import tempfile
import time

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)

# RequestBlocked 재시도 설정
_BLOCKED_MAX_RETRIES = 3
_BLOCKED_RETRY_DELAYS = [30, 45, 60]  # 각 재시도 전 대기 시간(초)


def get_transcript(
    video_id: str, preferred_langs: list[str] | None = None
) -> str | None:
    """영상의 자막 텍스트를 추출한다.

    1차: youtube-transcript-api (RequestBlocked 시 재시도)
    2차: yt-dlp 폴백 (youtube-transcript-api 완전 실패 시)

    Args:
        video_id: YouTube 영상 ID
        preferred_langs: 선호 언어 코드 리스트 (기본값: ["ko", "en"])

    Returns:
        자막 텍스트 문자열. 자막이 없으면 None
    """
    if preferred_langs is None:
        preferred_langs = ["ko", "en"]

    # 1차: youtube-transcript-api 시도
    for attempt in range(_BLOCKED_MAX_RETRIES):
        result = _fetch_transcript(video_id, preferred_langs)

        if result is not None:
            return result
        if result is None and not _last_was_blocked:
            # RequestBlocked가 아닌 다른 이유로 실패 → 재시도 무의미
            break

        # RequestBlocked → 대기 후 재시도
        if attempt < _BLOCKED_MAX_RETRIES - 1:
            delay = _BLOCKED_RETRY_DELAYS[attempt]
            logger.info(
                f"RequestBlocked - {delay}초 대기 후 재시도 "
                f"({attempt + 1}/{_BLOCKED_MAX_RETRIES}): {video_id}"
            )
            time.sleep(delay)

    if _last_was_blocked:
        logger.warning(
            f"영상 {video_id} RequestBlocked {_BLOCKED_MAX_RETRIES}회 연속 실패"
        )
        # 2차: yt-dlp 폴백 시도
        logger.info(f"영상 {video_id} yt-dlp 폴백 시도")
        result = _fetch_transcript_ytdlp(video_id, preferred_langs)
        if result is not None:
            return result
        logger.warning(f"영상 {video_id} yt-dlp 폴백도 실패")

    return None


# 마지막 실패가 RequestBlocked였는지 추적하는 플래그
_last_was_blocked = False


def _fetch_transcript(
    video_id: str, preferred_langs: list[str]
) -> str | None:
    """자막 추출을 1회 시도한다.

    성공 시 텍스트, 실패 시 None을 반환한다.
    _last_was_blocked 플래그로 RequestBlocked 여부를 알린다.
    """
    global _last_was_blocked
    _last_was_blocked = False

    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        proxy = GenericProxyConfig(https_url=proxy_url)
        api = YouTubeTranscriptApi(proxy_config=proxy)
        logger.debug(f"프록시 사용: {proxy_url[:20]}...")
    else:
        api = YouTubeTranscriptApi()

    try:
        fetched = api.fetch(video_id, languages=preferred_langs)
        text = format_transcript(fetched)
        lang = fetched.language_code
        logger.info(
            f"영상 {video_id} 자막 추출 완료 ({lang}, {len(text)}자)"
        )
        return text

    except NoTranscriptFound:
        logger.info(
            f"영상 {video_id}에서 지원하는 언어의 자막을 찾을 수 없음 - 건너뜀"
        )
        return None
    except TranscriptsDisabled:
        logger.info(f"영상 {video_id}의 자막이 비활성화됨 - 건너뜀")
        return None
    except VideoUnavailable:
        logger.warning(f"영상 {video_id}을 사용할 수 없음 - 건너뜀")
        return None
    except Exception as e:
        error_name = type(e).__name__
        if "Blocked" in error_name or "blocked" in str(e).lower():
            _last_was_blocked = True
            logger.warning(f"영상 {video_id} 요청 차단됨: {repr(e)}")
        else:
            logger.error(f"영상 {video_id} 자막 추출 중 예외 발생: {repr(e)}")
        return None


def _fetch_transcript_ytdlp(
    video_id: str, preferred_langs: list[str]
) -> str | None:
    """yt-dlp를 사용하여 자막을 추출한다 (폴백).

    yt-dlp는 youtube-transcript-api보다 RequestBlocked 우회 능력이 강하다.
    자동 생성 자막도 지원한다.

    Args:
        video_id: YouTube 영상 ID
        preferred_langs: 선호 언어 코드 리스트

    Returns:
        자막 텍스트 문자열. 실패 시 None
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    lang_str = ",".join(preferred_langs)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = os.path.join(tmpdir, "sub")

        cmd = [
            "yt-dlp",
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang", lang_str,
            "--sub-format", "vtt",
            "--skip-download",
            "--no-warnings",
            "-o", output_template,
            url,
        ]

        proxy_url = os.getenv("PROXY_URL")
        if proxy_url:
            cmd.extend(["--proxy", proxy_url])

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # 다운로드된 자막 파일 찾기 (선호 언어 순서대로)
            for lang in preferred_langs:
                for ext in [f".{lang}.vtt", f".{lang}.vtt"]:
                    sub_path = output_template + ext
                    if os.path.exists(sub_path):
                        text = _parse_vtt(sub_path)
                        if text:
                            logger.info(
                                f"영상 {video_id} yt-dlp 자막 추출 완료 "
                                f"({lang}, {len(text)}자)"
                            )
                            return text

            # 언어 무관하게 아무 자막 파일이든 찾기
            vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
            if vtt_files:
                text = _parse_vtt(vtt_files[0])
                if text:
                    logger.info(
                        f"영상 {video_id} yt-dlp 자막 추출 완료 "
                        f"(자동감지, {len(text)}자)"
                    )
                    return text

            logger.info(f"영상 {video_id} yt-dlp로 자막 파일을 찾지 못함")
            return None

        except subprocess.TimeoutExpired:
            logger.warning(f"영상 {video_id} yt-dlp 타임아웃 (120초)")
            return None
        except FileNotFoundError:
            logger.error("yt-dlp가 설치되어 있지 않음 - pip install yt-dlp")
            return None
        except Exception as e:
            logger.error(f"영상 {video_id} yt-dlp 실행 중 예외: {repr(e)}")
            return None


def _parse_vtt(vtt_path: str) -> str:
    """VTT 자막 파일에서 텍스트만 추출한다.

    타임스탬프, 헤더, 중복 라인을 제거하고 순수 텍스트만 반환한다.

    Args:
        vtt_path: VTT 파일 경로

    Returns:
        정리된 자막 텍스트
    """
    with open(vtt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    texts = []
    prev_text = ""
    for line in lines:
        line = line.strip()
        # 헤더, 빈 줄, 타임스탬프 줄 건너뛰기
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") \
                or line.startswith("Language:") or "-->" in line:
            continue
        # HTML 태그 제거
        clean = re.sub(r"<[^>]+>", "", line)
        clean = clean.strip()
        # 중복 라인 제거 (자동 자막에서 흔함)
        if clean and clean != prev_text:
            texts.append(clean)
            prev_text = clean

    return " ".join(texts)


def format_transcript(fetched_transcript) -> str:
    """FetchedTranscript에서 텍스트만 추출하여 이어붙인다.

    Args:
        fetched_transcript: youtube-transcript-api v1.x FetchedTranscript 객체
            순회하면 FetchedTranscriptSnippet(text, start, duration)을 반환

    Returns:
        정리된 자막 텍스트 (공백으로 연결)
    """
    # 각 스니펫의 텍스트를 추출하여 공백으로 연결
    texts = [snippet.text.strip() for snippet in fetched_transcript if snippet.text]
    return " ".join(texts)
