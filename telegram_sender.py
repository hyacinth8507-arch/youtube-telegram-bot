"""
telegram_sender.py - 텔레그램 전송 모듈

요약 결과를 포맷팅하여 Telegram Bot API로 메시지를 전송한다.
"""

import logging
import time

import telegram

logger = logging.getLogger(__name__)

# 텔레그램 메시지 최대 길이
TELEGRAM_MAX_LENGTH = 4096


def format_message(video_info: dict, summary: dict) -> str:
    """영상 정보와 요약 결과를 텔레그램 메시지 형식으로 포맷팅한다.

    HTML 파싱 모드를 사용한다.

    Args:
        video_info: {"title", "channel_name", "video_id"}
        summary: {"summary": str, "keywords": list[str]}

    Returns:
        HTML 포맷의 메시지 문자열
    """
    title = video_info.get("title", "제목 없음")
    channel = video_info.get("channel_name", "채널 없음")
    video_id = video_info.get("video_id", "")
    summary_text = summary.get("summary", "요약 없음")
    keywords = summary.get("keywords", [])

    # 키워드를 해시태그 형식으로 변환
    keyword_tags = " ".join(f"#{kw}" for kw in keywords) if keywords else ""

    url = f"https://www.youtube.com/watch?v={video_id}"

    message = (
        f"🎬 <b>{_escape_html(title)}</b>\n"
        f"\n"
        f"📺 채널: {_escape_html(channel)}\n"
        f"\n"
        f"📝 <b>요약</b>\n"
        f"{_escape_html(summary_text)}\n"
    )

    if keyword_tags:
        message += f"\n🏷 <b>키워드</b>\n{_escape_html(keyword_tags)}\n"

    message += f'\n🔗 <a href="{url}">영상 보기</a>'

    return message


def _escape_html(text: str) -> str:
    """텔레그램 HTML 모드에서 특수문자를 이스케이프한다.

    텔레그램은 <, >, & 만 이스케이프하면 된다.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_summary(
    bot_token: str, chat_id: str, video_info: dict, summary: dict
) -> bool:
    """요약 결과를 텔레그램으로 전송한다.

    메시지가 4096자를 초과하면 분할 전송한다.
    Rate limit(429) 발생 시 최대 3회 재시도한다.

    Args:
        bot_token: 텔레그램 봇 토큰
        chat_id: 메시지를 보낼 채팅방 ID
        video_info: 영상 정보 딕셔너리
        summary: 요약 결과 딕셔너리

    Returns:
        전송 성공 여부
    """
    message = format_message(video_info, summary)
    bot = telegram.Bot(token=bot_token)

    max_retries = 3

    for attempt in range(max_retries):
        try:
            # 메시지 길이 초과 시 분할 전송
            if len(message) > TELEGRAM_MAX_LENGTH:
                await _send_split_message(bot, chat_id, message)
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=telegram.constants.ParseMode.HTML,
                    disable_web_page_preview=False,
                )

            logger.info(
                f"메시지 전송 성공 (chat_id: {chat_id}, "
                f"영상: {video_info.get('video_id', 'unknown')})"
            )
            return True

        except telegram.error.RetryAfter as e:
            # 텔레그램 Rate limit - 지정된 시간만큼 대기
            wait_time = e.retry_after
            logger.warning(
                f"Rate limit - {wait_time}초 후 재시도 "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)

        except telegram.error.Forbidden:
            # python-telegram-bot v22.x: Unauthorized -> Forbidden
            logger.error("봇 토큰이 유효하지 않거나 차단됨 - 토큰을 확인하세요")
            return False

        except telegram.error.InvalidToken:
            logger.error("봇 토큰 형식이 잘못됨 - 토큰을 확인하세요")
            return False

        except telegram.error.BadRequest as e:
            logger.error(f"잘못된 요청 (chat_id: {chat_id}): {e}")
            return False

        except Exception as e:
            logger.error(f"메시지 전송 중 예외 발생: {e}")
            return False

    logger.error("최대 재시도 횟수 초과 - 메시지 전송 실패")
    return False


async def _send_split_message(
    bot: telegram.Bot, chat_id: str, message: str
) -> None:
    """긴 메시지를 여러 개로 분할하여 전송한다.

    줄바꿈 기준으로 최대 길이에 맞게 나눈다.
    """
    # 줄바꿈 기준으로 분할
    lines = message.split("\n")
    current_chunk = ""

    for line in lines:
        # 현재 청크에 줄을 추가해도 제한 이내인지 확인
        test = current_chunk + "\n" + line if current_chunk else line
        if len(test) <= TELEGRAM_MAX_LENGTH:
            current_chunk = test
        else:
            # 현재 청크 전송
            if current_chunk:
                await bot.send_message(
                    chat_id=chat_id,
                    text=current_chunk,
                    parse_mode=telegram.constants.ParseMode.HTML,
                )
            current_chunk = line

    # 남은 청크 전송
    if current_chunk:
        await bot.send_message(
            chat_id=chat_id,
            text=current_chunk,
            parse_mode=telegram.constants.ParseMode.HTML,
        )
