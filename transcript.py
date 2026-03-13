"""
transcript.py -- YouTube 자막 추출 모듈

youtube-transcript-api를 사용하여 영상의 자막을 추출한다.
한국어(ko) 자막을 우선 시도하고, 없으면 영어(en) 자막을 추출한다.
"""

import logging

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

logger = logging.getLogger(__name__)


def get_transcript(
    video_id: str, preferred_langs: list[str] | None = None
) -> str | None:
    """영상의 자막 텍스트를 추출한다.

    선호 언어 순서대로 자막을 시도하며, 모두 실패하면 None을 반환한다.

    Args:
        video_id: YouTube 영상 ID
        preferred_langs: 선호 언어 코드 리스트 (기본값: ["ko", "en"])

    Returns:
        자막 텍스트 문자열. 자막이 없으면 None
    """
    if preferred_langs is None:
        preferred_langs = ["ko", "en"]

    # youtube-transcript-api v1.x: 인스턴스 생성 필요
    api = YouTubeTranscriptApi()

    try:
        # fetch()는 languages 순서대로 자막을 탐색한다
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
        logger.error(f"영상 {video_id} 자막 추출 중 예외 발생: {repr(e)}")
        return None


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
