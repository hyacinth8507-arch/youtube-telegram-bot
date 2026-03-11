"""
telegram_sender.py - 텔레그램 전송 모듈

요약 결과 + 정리된 전체 스크립트를 포맷팅하여 Telegram Bot API로 전송한다.
메시지가 4096자를 초과하면 섹션 단위로 분할 전송한다.
"""

import logging
import re
import time

import telegram

logger = logging.getLogger(__name__)

# 텔레그램 메시지 최대 길이
TELEGRAM_MAX_LENGTH = 4096


def _escape_html(text: str) -> str:
    """텔레그램 HTML 모드에서 특수문자를 이스케이프한다."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_header(video_info: dict, summary: dict) -> str:
    """메시지 상단부(제목, 채널, 키워드, 3줄 요약)를 생성한다.

    Args:
        video_info: {"title", "channel_name", "video_id"}
        summary: {"summary": str, "keywords": list[str]}

    Returns:
        HTML 포맷 헤더 문자열
    """
    title = video_info.get("title", "제목 없음")
    channel = video_info.get("channel_name", "채널 없음")
    summary_text = summary.get("summary", "요약 없음")
    keywords = summary.get("keywords", [])

    keyword_tags = " ".join(f"#{kw}" for kw in keywords) if keywords else ""

    header = f"🎬 <b>{_escape_html(title)}</b>\n"
    header += f"📺 {_escape_html(channel)}\n"

    if keyword_tags:
        header += f"🏷 키워드: {_escape_html(keyword_tags)}\n"

    header += f"\n📌 <b>3줄 요약</b>\n"
    header += f"{_escape_html(summary_text)}"

    return header


def format_footer(video_id: str) -> str:
    """메시지 하단부(원본 링크)를 생성한다."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    return f'🔗 <a href="{url}">원본 보기</a>'


def build_messages(video_info: dict, summary: dict) -> list[str]:
    """영상 정보와 요약 결과를 텔레그램 메시지 리스트로 변환한다.

    메시지가 4096자 이하이면 단일 메시지로, 초과하면 섹션 단위로
    분할하여 여러 메시지로 나눈다.

    Args:
        video_info: {"title", "channel_name", "video_id"}
        summary: {"summary", "keywords", "formatted_script"}

    Returns:
        전송할 메시지 문자열 리스트
    """
    video_id = video_info.get("video_id", "")
    formatted_script = summary.get("formatted_script", "")

    header = format_header(video_info, summary)
    footer = format_footer(video_id)

    # 전체 스크립트가 없으면 헤더 + 푸터만 전송
    if not formatted_script:
        return [f"{header}\n\n{footer}"]

    # 단일 메시지 시도
    full = f"{header}\n\n📝 <b>전체 내용</b>\n{formatted_script}\n\n{footer}"
    if len(full) <= TELEGRAM_MAX_LENGTH:
        return [full]

    # === 분할 전송 ===
    messages = []

    # 첫 메시지: 헤더 + "전체 내용은 아래에 계속"
    first_msg = f"{header}\n\n📝 <b>전체 내용</b> (아래 계속)"
    messages.append(first_msg)

    # 전체 스크립트를 ▶ 섹션 단위로 분할
    sections = _split_by_sections(formatted_script)

    current_chunk = ""
    for section in sections:
        # 현재 청크에 섹션 추가 시도
        test = f"{current_chunk}\n\n{section}" if current_chunk else section
        if len(test) <= TELEGRAM_MAX_LENGTH:
            current_chunk = test
        else:
            # 현재 청크가 있으면 저장
            if current_chunk:
                messages.append(current_chunk)
            # 섹션 자체가 한 메시지를 초과하면 줄 단위로 분할
            if len(section) > TELEGRAM_MAX_LENGTH:
                sub_messages = _split_by_lines(section)
                messages.extend(sub_messages)
                current_chunk = ""
            else:
                current_chunk = section

    # 마지막 청크 + 푸터
    if current_chunk:
        test = f"{current_chunk}\n\n{footer}"
        if len(test) <= TELEGRAM_MAX_LENGTH:
            messages.append(test)
        else:
            messages.append(current_chunk)
            messages.append(footer)
    else:
        messages.append(footer)

    return messages


def _split_by_sections(text: str) -> list[str]:
    """텍스트를 ▶ 소제목 기준으로 섹션 리스트로 분할한다."""
    # ▶ 앞의 줄바꿈에서 분할 (lookahead로 ▶를 유지)
    parts = re.split(r"(?=\n▶ )", text)

    # 첫 번째 파트 앞에 \n이 없을 수 있으므로 별도 처리
    if parts and not parts[0].strip().startswith("▶"):
        first = parts[0]
        rest = parts[1:]
        result = [first.strip()] if first.strip() else []
        result.extend(p.strip() for p in rest if p.strip())
        return result

    return [p.strip() for p in parts if p.strip()]


def _split_by_lines(text: str) -> list[str]:
    """텍스트를 줄 단위로 최대 길이에 맞게 분할한다."""
    lines = text.split("\n")
    chunks = []
    current = ""

    for line in lines:
        test = f"{current}\n{line}" if current else line
        if len(test) <= TELEGRAM_MAX_LENGTH:
            current = test
        else:
            if current:
                chunks.append(current)
            current = line

    if current:
        chunks.append(current)

    return chunks


async def send_summary(
    bot_token: str, chat_id: str, video_info: dict, summary: dict
) -> bool:
    """요약 결과를 텔레그램으로 전송한다.

    메시지를 섹션 단위로 분할하여 순차 전송한다.
    Rate limit(429) 발생 시 최대 3회 재시도한다.

    Args:
        bot_token: 텔레그램 봇 토큰
        chat_id: 메시지를 보낼 채팅방 ID
        video_info: 영상 정보 딕셔너리
        summary: 요약 결과 딕셔너리

    Returns:
        전송 성공 여부
    """
    messages = build_messages(video_info, summary)
    bot = telegram.Bot(token=bot_token)

    video_id = video_info.get("video_id", "unknown")
    logger.info(f"메시지 {len(messages)}개로 분할 전송 시작 (영상: {video_id})")

    for i, msg in enumerate(messages, 1):
        success = await _send_single_message(bot, chat_id, msg, i, len(messages))
        if not success:
            return False
        # 분할 전송 시 Rate limit 방지를 위한 딜레이
        if len(messages) > 1 and i < len(messages):
            time.sleep(0.5)

    logger.info(
        f"메시지 전송 성공 (chat_id: {chat_id}, "
        f"영상: {video_id}, {len(messages)}개 메시지)"
    )
    return True


async def _send_single_message(
    bot: telegram.Bot, chat_id: str, text: str, idx: int, total: int
) -> bool:
    """단일 메시지를 전송한다. 실패 시 재시도한다."""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=telegram.constants.ParseMode.HTML,
                disable_web_page_preview=(idx < total),  # 마지막 메시지만 미리보기
            )
            return True

        except telegram.error.RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(
                f"Rate limit - {wait_time}초 후 재시도 "
                f"(메시지 {idx}/{total}, 시도 {attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)

        except telegram.error.Forbidden:
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

    logger.error(f"최대 재시도 횟수 초과 - 메시지 {idx}/{total} 전송 실패")
    return False
