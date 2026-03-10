# YouTube → Telegram 자동 요약 봇

YouTube 채널의 신규 영상을 자동 감지하여 자막을 추출하고, AI(Claude)로 요약한 뒤 텔레그램으로 전송하는 자동화 프로그램입니다.

## 주요 기능

- YouTube 채널 신규 영상 자동 감지
- 한국어/영어 자막 자동 추출
- Claude AI를 활용한 3~5문장 핵심 요약 + 키워드 추출
- 텔레그램 자동 전송
- 중복 처리 방지 (processed_videos.json)
- 주기적 자동 실행 (스케줄러)

## 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/your-username/youtube-telegram-bot.git
cd youtube-telegram-bot
```

### 2. Python 가상환경 생성 (권장)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

## API 키 발급 가이드

### YouTube Data API v3 키

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)
3. **API 및 서비스 > 라이브러리**에서 "YouTube Data API v3" 검색 후 사용 설정
4. **API 및 서비스 > 사용자 인증 정보**에서 **API 키** 생성
5. 생성된 키를 `.env` 파일의 `YOUTUBE_API_KEY`에 입력

### Anthropic Claude API 키

1. [Anthropic Console](https://console.anthropic.com/)에 접속
2. 회원가입 및 로그인
3. **API Keys** 메뉴에서 새 키 생성
4. 생성된 키를 `.env` 파일의 `ANTHROPIC_API_KEY`에 입력

### Telegram Bot 토큰

1. 텔레그램에서 [@BotFather](https://t.me/BotFather)에 메시지 전송
2. `/newbot` 명령어 입력
3. 봇 이름과 사용자명 설정
4. 발급된 토큰을 `.env` 파일의 `TELEGRAM_BOT_TOKEN`에 입력

### Telegram Chat ID 확인

1. 봇에게 아무 메시지나 전송
2. 브라우저에서 `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` 접속
3. 응답에서 `chat.id` 값을 `config.yaml`의 `chat_id`에 입력

## 설정 방법

### 1. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 발급받은 API 키를 입력합니다:

```
YOUTUBE_API_KEY=실제_YouTube_API_키
ANTHROPIC_API_KEY=실제_Anthropic_API_키
TELEGRAM_BOT_TOKEN=실제_텔레그램_봇_토큰
```

### 2. config.yaml 설정

`config.yaml` 파일을 열어 모니터링할 YouTube 채널과 텔레그램 설정을 입력합니다:

```yaml
youtube:
  channels:
    - id: "UC_x5XG1OV2P6uZZ5FSM9Ttw"  # 채널 ID
      name: "Google Developers"          # 표시용 이름
  max_results: 5

schedule:
  interval_minutes: 30  # 체크 주기 (분)

telegram:
  chat_id: "123456789"  # 실제 Chat ID
```

YouTube 채널 ID 확인 방법:
- 채널 페이지 URL에서 `youtube.com/channel/UCxxxxxx`의 `UCxxxxxx` 부분

## 실행 방법

```bash
python main.py
```

실행하면:
1. 즉시 1회 파이프라인 실행 (모든 채널의 신규 영상 확인)
2. 이후 설정된 주기(기본 30분)마다 자동 반복 실행
3. `Ctrl+C`로 종료

## 프로젝트 구조

```
youtube-telegram-bot/
├── main.py                  # 진입점 + 스케줄러
├── youtube_monitor.py       # YouTube 신규 영상 감지
├── transcript.py            # 자막 추출
├── summarizer.py            # Claude AI 요약
├── telegram_sender.py       # 텔레그램 전송
├── config.yaml              # 설정 파일
├── .env.example             # 환경변수 템플릿
├── requirements.txt         # Python 의존성
├── README.md                # 이 문서
├── DESIGN.md                # 기술 설계서
├── data/
│   └── processed_videos.json  # 처리 완료 영상 기록 (자동 생성)
└── logs/
    └── bot.log              # 로그 파일 (자동 생성)
```

## 로그 확인

```bash
# 실시간 로그 확인
tail -f logs/bot.log

# Windows의 경우
Get-Content logs/bot.log -Wait
```
