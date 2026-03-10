"""
summarizer.py - AI 요약 모듈

Anthropic Claude API를 사용하여 자막 텍스트를 3~5문장으로 핵심 요약하고,
주요 키워드를 추출한다.
"""

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)

# Claude에 전달할 시스템 프롬프트
SYSTEM_PROMPT = "당신은 YouTube 영상 내용을 간결하게 요약하는 전문가입니다."


def build_prompt(transcript: str) -> str:
    """Claude에 전달할 사용자 프롬프트를 생성한다.

    Args:
        transcript: 자막 텍스트

    Returns:
        프롬프트 문자열
    """
    return f"""다음은 YouTube 영상의 자막 스크립트입니다.

1. 핵심 내용을 3~5문장으로 요약해주세요.
2. 주요 키워드를 5개 이내로 추출해주세요.

아래 JSON 형식으로만 응답해주세요 (다른 텍스트 없이):
{{
  "summary": "요약 내용",
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}

---
{transcript}"""


def parse_response(response_text: str) -> dict:
    """Claude 응답을 파싱하여 summary와 keywords를 추출한다.

    JSON 파싱에 실패하면 원본 응답을 summary로 사용한다.

    Args:
        response_text: Claude 응답 원문

    Returns:
        {"summary": str, "keywords": list[str]}
    """
    # 응답에서 JSON 부분 추출 시도
    text = response_text.strip()

    # ```json ... ``` 코드블록 안에 있을 수 있으므로 제거
    if text.startswith("```"):
        lines = text.split("\n")
        # 첫 줄(```json)과 마지막 줄(```) 제거
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        # 필수 키 검증
        if "summary" in result and "keywords" in result:
            return {
                "summary": str(result["summary"]),
                "keywords": list(result["keywords"]),
            }
        raise ValueError("응답에 summary 또는 keywords 키가 없음")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Claude 응답 파싱 실패 - 원본 사용: {e}")
        return {
            "summary": response_text.strip(),
            "keywords": [],
        }


def summarize(
    transcript: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
) -> dict:
    """자막 텍스트를 Claude API로 요약하고 키워드를 추출한다.

    Rate limit(429) 발생 시 지수 백오프로 최대 3회 재시도한다.

    Args:
        transcript: 자막 텍스트
        api_key: Anthropic API 키
        model: 사용할 Claude 모델명
        max_tokens: 최대 응답 토큰 수

    Returns:
        {"summary": str, "keywords": list[str]}
    """
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(transcript)

    max_retries = 3

    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            # 응답 텍스트 추출
            response_text = message.content[0].text
            result = parse_response(response_text)

            logger.info(
                f"요약 완료 ({len(result['summary'])}자, "
                f"키워드 {len(result['keywords'])}개)"
            )
            return result

        except anthropic.RateLimitError:
            # 지수 백오프: 2초, 4초, 8초
            wait_time = 2 ** (attempt + 1)
            logger.warning(
                f"Rate limit 초과 - {wait_time}초 후 재시도 "
                f"({attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)

        except anthropic.AuthenticationError:
            logger.error("Anthropic API 인증 실패 - API 키를 확인하세요")
            return {"summary": "", "keywords": []}

        except Exception as e:
            logger.error(f"요약 중 예외 발생: {e}")
            return {"summary": "", "keywords": []}

    # 모든 재시도 실패
    logger.error("최대 재시도 횟수 초과 - 요약 실패")
    return {"summary": "", "keywords": []}
