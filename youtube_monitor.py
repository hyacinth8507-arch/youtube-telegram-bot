"""
youtube_monitor.py - YouTube 신규 영상 감지 모듈

YouTube Data API v3를 사용하여 지정된 채널들의 최신 영상을 확인하고,
이미 처리한 영상을 processed_videos.json으로 관리하여 중복을 방지한다.
"""

import json
import logging
import os
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def get_latest_videos(
    channel_id: str, api_key: str, max_results: int = 5
) -> list[dict]:
    """채널의 최신 영상 목록을 YouTube Data API v3로 조회한다.

    Args:
        channel_id: YouTube 채널 ID (UC로 시작)
        api_key: YouTube Data API 키
        max_results: 조회할 최대 영상 수

    Returns:
        영상 정보 딕셔너리 리스트
        [{"video_id", "title", "channel_name", "published_at"}, ...]
    """
    youtube = build("youtube", "v3", developerKey=api_key)

    try:
        # 채널의 최신 영상 검색
        search_response = (
            youtube.search()
            .list(
                channelId=channel_id,
                part="snippet",
                order="date",
                maxResults=max_results,
                type="video",
            )
            .execute()
        )

        videos = []
        for item in search_response.get("items", []):
            video = {
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel_name": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
            }
            videos.append(video)

        logger.info(f"채널 {channel_id}에서 영상 {len(videos)}개 조회 완료")
        return videos

    except HttpError as e:
        if e.resp.status == 403:
            logger.warning(f"API 할당량 초과 (채널: {channel_id}): {e}")
        else:
            logger.error(f"YouTube API 에러 (채널: {channel_id}): {e}")
        return []
    except Exception as e:
        logger.error(f"영상 조회 중 예외 발생 (채널: {channel_id}): {e}")
        return []


def load_processed_videos(processed_path: str) -> set[str]:
    """처리된 영상 ID 집합을 JSON 파일에서 로드한다.

    파일이 없거나 손상된 경우 빈 집합을 반환한다.

    Args:
        processed_path: processed_videos.json 파일 경로

    Returns:
        처리된 영상 ID의 집합
    """
    if not os.path.exists(processed_path):
        logger.info(f"{processed_path} 파일 없음 - 빈 상태로 시작")
        return set()

    try:
        with open(processed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        processed = set(data.get("processed", []))
        logger.info(f"처리 완료 영상 {len(processed)}개 로드됨")
        return processed
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"{processed_path} 파일 손상 - 빈 상태로 초기화: {e}")
        return set()


def filter_new_videos(videos: list[dict], processed_path: str) -> list[dict]:
    """이미 처리된 영상을 제외한 신규 영상만 반환한다.

    Args:
        videos: 영상 정보 딕셔너리 리스트
        processed_path: processed_videos.json 파일 경로

    Returns:
        신규 영상 정보 리스트
    """
    processed = load_processed_videos(processed_path)
    new_videos = [v for v in videos if v["video_id"] not in processed]

    if new_videos:
        logger.info(f"신규 영상 {len(new_videos)}개 발견")
    else:
        logger.info("신규 영상 없음")

    return new_videos


def mark_as_processed(video_id: str, processed_path: str) -> None:
    """처리 완료된 영상 ID를 JSON 파일에 기록한다.

    Args:
        video_id: 처리 완료된 영상 ID
        processed_path: processed_videos.json 파일 경로
    """
    # 기존 데이터 로드
    processed = load_processed_videos(processed_path)
    processed.add(video_id)

    # 디렉토리가 없으면 생성
    os.makedirs(os.path.dirname(processed_path) or ".", exist_ok=True)

    # JSON 파일에 저장
    data = {
        "processed": sorted(processed),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"영상 {video_id} 처리 완료로 기록됨")
