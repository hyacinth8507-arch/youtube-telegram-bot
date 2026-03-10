"""
main.py - 진입점 + 스케줄러

프로그램 진입점. 설정 파일을 로드하고, 스케줄러를 통해
YouTube 신규 영상 감지 → 자막 추출 → AI 요약 → 텔레그램 전송
파이프라인을 주기적으로 실행한다.
"""

import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import schedule
import yaml
from dotenv import load_dotenv

from summarizer import summarize
from telegram_sender import send_summary
from transcript import get_transcript
from youtube_monitor import filter_new_videos, get_latest_videos, mark_as_processed

logger = logging.getLogger("main")


def load_config(path: str = "config.yaml") -> dict:
    """YAML 설정 파일을 파싱하여 딕셔너리로 반환한다.

    Args:
        path: config.yaml 파일 경로

    Returns:
        설정 딕셔너리

    Raises:
        FileNotFoundError: 설정 파일이 없는 경우
        yaml.YAMLError: YAML 파싱 실패
    """
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info(f"설정 파일 로드 완료: {path}")
    return config


def setup_logging(log_path: str = "logs/bot.log", level: str = "INFO") -> None:
    """로깅 포맷 및 핸들러를 설정한다.

    콘솔(stdout)과 파일에 동시 출력한다.
    파일은 RotatingFileHandler 사용 (최대 5MB, 백업 3개).

    Args:
        log_path: 로그 파일 경로
        level: 로깅 레벨 (DEBUG, INFO, WARNING, ERROR)
    """
    # 로그 디렉토리 생성
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    log_format = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()

    # 콘솔 핸들러 (Windows cp949 인코딩 문제 방지를 위해 UTF-8 스트림 사용)
    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # 파일 핸들러 (RotatingFileHandler: 5MB, 백업 3개)
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    logger.info("로깅 설정 완료")


def run_pipeline(config: dict) -> None:
    """감지 → 자막 → 요약 → 전송 파이프라인을 1회 실행한다.

    각 영상에 대해 순차적으로 처리하며, 개별 영상 실패 시
    해당 영상만 건너뛰고 다음 영상을 처리한다.

    Args:
        config: 설정 딕셔너리
    """
    logger.info("===== 파이프라인 실행 시작 =====")

    # 환경변수에서 API 키 로드
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    # 설정 값 추출
    channels = config.get("youtube", {}).get("channels", [])
    max_results = config.get("youtube", {}).get("max_results", 5)
    # 환경변수 TELEGRAM_CHAT_ID가 있으면 우선 사용 (GitHub Secrets 지원)
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or config.get("telegram", {}).get("chat_id", "")
    preferred_langs = config.get("transcript", {}).get(
        "preferred_languages", ["ko", "en"]
    )
    summarizer_model = config.get("summarizer", {}).get(
        "model", "claude-sonnet-4-20250514"
    )
    summarizer_max_tokens = config.get("summarizer", {}).get("max_tokens", 1024)
    processed_path = config.get("data", {}).get(
        "processed_videos", "data/processed_videos.json"
    )

    # 각 채널에 대해 신규 영상 처리
    for channel in channels:
        channel_id = channel.get("id", "")
        channel_name = channel.get("name", channel_id)

        if not channel_id:
            logger.warning(f"채널 ID가 비어있음 - 건너뜀")
            continue

        logger.info(f"채널 확인 중: {channel_name} ({channel_id})")

        # 1단계: 최신 영상 조회
        videos = get_latest_videos(channel_id, youtube_api_key, max_results)
        if not videos:
            continue

        # 2단계: 신규 영상 필터링
        new_videos = filter_new_videos(videos, processed_path)
        if not new_videos:
            continue

        # 각 신규 영상에 대해 파이프라인 실행
        for video in new_videos:
            video_id = video["video_id"]
            title = video["title"]

            try:
                logger.info(f"영상 처리 중: {title} ({video_id})")

                # 3단계: 자막 추출
                transcript_text = get_transcript(video_id, preferred_langs)
                if not transcript_text:
                    logger.info(f"자막 없음 - 건너뜀: {title}")
                    # 자막 없는 영상도 처리 완료로 기록 (반복 시도 방지)
                    mark_as_processed(video_id, processed_path)
                    continue

                # 4단계: AI 요약
                summary = summarize(
                    transcript_text,
                    anthropic_api_key,
                    model=summarizer_model,
                    max_tokens=summarizer_max_tokens,
                )
                if not summary.get("summary"):
                    logger.warning(f"요약 실패 - 건너뜀: {title}")
                    continue

                # 5단계: 텔레그램 전송
                success = asyncio.run(
                    send_summary(telegram_bot_token, chat_id, video, summary)
                )

                if success:
                    # 전송 성공 시 처리 완료로 기록
                    mark_as_processed(video_id, processed_path)
                else:
                    logger.warning(f"텔레그램 전송 실패: {title}")

            except Exception as e:
                logger.error(f"영상 처리 중 예외 발생 ({video_id}): {e}")
                continue

    logger.info("===== 파이프라인 실행 완료 =====")


def main() -> None:
    """프로그램 진입점.

    1. .env 파일에서 환경변수 로드
    2. config.yaml 설정 파일 로드
    3. 로깅 초기화
    4. 필수 환경변수 검증
    5. 스케줄러로 파이프라인 주기적 실행
    """
    # .env 파일 로드 (시스템 환경변수보다 .env 파일 우선)
    load_dotenv(override=True)

    # 설정 파일 로드
    try:
        config = load_config("config.yaml")
    except FileNotFoundError:
        print("[ERROR] config.yaml 파일을 찾을 수 없습니다.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[ERROR] config.yaml 파싱 실패: {e}")
        sys.exit(1)

    # 로깅 설정
    log_config = config.get("logging", {})
    setup_logging(
        log_path=log_config.get("file", "logs/bot.log"),
        level=log_config.get("level", "INFO"),
    )

    # 필수 환경변수 검증
    required_env_vars = ["YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = [var for var in required_env_vars if not os.getenv(var)]
    if missing:
        logger.error(f"필수 환경변수 누락: {', '.join(missing)}")
        logger.error(".env 파일을 확인하세요.")
        sys.exit(1)

    # 체크 주기 설정
    interval = config.get("schedule", {}).get("interval_minutes", 30)
    logger.info(f"스케줄러 시작 - {interval}분 간격으로 실행")

    # 최초 1회 즉시 실행
    run_pipeline(config)

    # 스케줄러 등록
    schedule.every(interval).minutes.do(run_pipeline, config=config)

    # 스케줄러 무한 루프
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("프로그램 종료 (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
