"""
summarizer.py - AI 요약 + 전체 스크립트 정리 모듈

Anthropic Claude API를 사용하여:
1. 자막 텍스트를 3줄 핵심 요약
2. 주요 키워드 추출
3. 전체 스크립트를 소제목/강조/문단 정리하여 반환
"""

import logging
import time

import anthropic

logger = logging.getLogger(__name__)

# Claude 시스템 프롬프트
SYSTEM_PROMPT = (
    "당신은 YouTube 영상 스크립트를 전문적으로 정리하는 편집자입니다. "
    "원문의 의미와 뉘앙스를 절대 훼손하지 않으면서, 읽기 쉽게 형식을 정리합니다."
)


def build_prompt(transcript: str) -> str:
    """Claude에 전달할 프롬프트를 생성한다.

    Args:
        transcript: 자막 텍스트

    Returns:
        프롬프트 문자열
    """
    # 1만자 이상이면 축약 허용 지시 추가
    length_note = ""
    if len(transcript) > 10000:
        length_note = (
            "\n- 스크립트가 매우 깁니다. 각 소제목 아래 핵심 내용 위주로 "
            "적절히 축약하되, 최대한 원문을 유지하세요."
        )

    return f"""다음은 YouTube 영상의 자막 스크립트입니다.
아래 3가지 작업을 수행해주세요.

[작업 1] 핵심 요약
- 영상의 핵심 내용을 정확히 3줄로 요약 (각 줄은 한 문장)

[작업 2] 키워드
- 주요 키워드를 5개 이내로 추출

[작업 3] 전체 스크립트 정리
- 원문 내용은 절대 바꾸지 않되, 형식만 정리
- 주제가 바뀌는 부분마다 소제목을 삽입 (형식: ▶ 소제목)
- 핵심 문장은 <b>굵은 글씨</b>로 강조 (HTML b 태그 사용)
- "어...", "그래서 뭐냐면", "아 그리고", "네", "자" 같은 불필요한 필러 제거
- 문단을 적절히 나누고 문장 부호 정리
- 원문의 의미나 뉘앙스는 훼손하지 말 것
- 텍스트 내의 & < > 문자는 &amp; &lt; &gt; 로 이스케이프하되, <b>와 </b> 태그는 그대로 유지{length_note}

반드시 아래 구분자 형식으로 응답해주세요 (구분자 줄은 정확히 지켜주세요):

===SUMMARY===
요약 첫째 줄
요약 둘째 줄
요약 셋째 줄
===KEYWORDS===
키워드1, 키워드2, 키워드3, 키워드4, 키워드5
===FORMATTED===
▶ 소제목1
정리된 내용...

▶ 소제목2
정리된 내용...

---
{transcript}"""


def parse_response(response_text: str) -> dict:
    """Claude 응답을 구분자 기반으로 파싱한다.

    ===SUMMARY===, ===KEYWORDS===, ===FORMATTED=== 구분자로 분리하여
    summary, keywords, formatted_script를 추출한다.

    Args:
        response_text: Claude 응답 원문

    Returns:
        {"summary": str, "keywords": list[str], "formatted_script": str}
    """
    text = response_text.strip()
    result = {"summary": "", "keywords": [], "formatted_script": ""}

    try:
        if (
            "===SUMMARY===" in text
            and "===KEYWORDS===" in text
            and "===FORMATTED===" in text
        ):
            # 구분자로 3개 섹션 분리
            after_summary = text.split("===SUMMARY===", 1)[1]
            summary_part, after_keywords = after_summary.split("===KEYWORDS===", 1)
            keywords_part, formatted_part = after_keywords.split("===FORMATTED===", 1)

            # 요약: 줄 단위로 파싱하여 "- " 접두사 붙이기
            summary_lines = [
                l.strip().lstrip("- ").strip()
                for l in summary_part.strip().split("\n")
                if l.strip()
            ]
            result["summary"] = "\n".join(
                f"- {line}" for line in summary_lines[:3]
            )

            # 키워드: 콤마 구분
            keywords = [
                kw.strip() for kw in keywords_part.strip().split(",") if kw.strip()
            ]
            result["keywords"] = keywords[:5]

            # 정리된 전체 스크립트 (HTML 포함, 그대로 유지)
            result["formatted_script"] = formatted_part.strip()

        else:
            # 구분자 형식 불일치 - 원본 텍스트를 요약으로 사용
            logger.warning("구분자 형식 불일치 - 원본 사용")
            result["summary"] = text[:500]

    except Exception as e:
        logger.warning(f"응답 파싱 실패 - 원본 사용: {e}")
        result["summary"] = text[:500]

    return result


def summarize(
    transcript: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 16000,
) -> dict:
    """자막 텍스트를 Claude API로 요약 + 전체 스크립트 정리한다.

    Rate limit(429) 발생 시 지수 백오프로 최대 3회 재시도한다.

    Args:
        transcript: 자막 텍스트
        api_key: Anthropic API 키
        model: 사용할 Claude 모델명
        max_tokens: 최대 응답 토큰 수

    Returns:
        {"summary": str, "keywords": list[str], "formatted_script": str}
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
                f"요약 완료 (요약 {len(result['summary'])}자, "
                f"키워드 {len(result['keywords'])}개, "
                f"스크립트 {len(result['formatted_script'])}자)"
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
            return {"summary": "", "keywords": [], "formatted_script": ""}

        except Exception as e:
            logger.error(f"요약 중 예외 발생: {e}")
            return {"summary": "", "keywords": [], "formatted_script": ""}

    # 모든 재시도 실패
    logger.error("최대 재시도 횟수 초과 - 요약 실패")
    return {"summary": "", "keywords": [], "formatted_script": ""}
