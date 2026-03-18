# YouTube-Telegram Bot 운영 가이드

## 1. 시스템 구조

```
YouTube 채널 (6개)          네이버 블로그 (1개)
       │                          │
       ▼                          ▼
  YouTube Data API v3        RSS 피드 조회
  (playlistItems.list)       (naver_monitor.py)
  (youtube_monitor.py)            │
       │                          ▼
       ▼                     본문 크롤링
  자막 추출                  (naver_scraper.py)
  (transcript.py)                 │
  ├─ youtube-transcript-api       │
  └─ yt-dlp (폴백)               │
       │                          │
       ▼                          ▼
  ┌──────────────────────────────────┐
  │   Claude AI 요약 (summarizer.py) │
  │   모델: claude-sonnet-4-20250514 │
  │   - 3줄 핵심 요약                │
  │   - 키워드 5개 추출              │
  │   - 전체 내용 소제목/강조 정리   │
  └──────────────────────────────────┘
                 │
                 ▼
  ┌──────────────────────────────────┐
  │  텔레그램 전송 (telegram_sender) │
  │  - 4096자 초과 시 분할 전송      │
  │  - HTML 포맷 (굵은 글씨, 링크)   │
  └──────────────────────────────────┘
```

### 파일별 역할

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점. 설정 로드, 스케줄러 실행, YouTube/블로그 파이프라인 호출 |
| `youtube_monitor.py` | YouTube API로 최신 영상 조회, processed_videos.json으로 중복 관리 |
| `transcript.py` | 자막 추출 (youtube-transcript-api + yt-dlp 폴백), 프록시 지원 |
| `summarizer.py` | Claude API로 요약/키워드/전체 정리 생성 |
| `telegram_sender.py` | 텔레그램 봇으로 메시지 포맷팅 및 전송 |
| `naver_monitor.py` | 네이버 블로그 RSS로 신규 글 감지 |
| `naver_scraper.py` | 네이버 블로그 본문 크롤링 |
| `config.yaml` | 채널/블로그 목록, 스케줄, 모델 등 설정 |
| `.env` | API 키, 봇 토큰 등 비밀 정보 |

---

## 2. 사용 중인 서비스

### 서버

| 항목 | 정보 |
|---|---|
| 클라우드 | Oracle Cloud Infrastructure (OCI) - Always Free |
| 서버 IP | `144.24.85.237` |
| 사용자 | `ubuntu` |
| OS | Ubuntu 22.04 (Linux 6.8.0-oracle) |
| SSH 키 | `C:\Users\User\Downloads\ssh-key-2026-03-17.key` |
| Python | 3.10.12 |
| 프로젝트 경로 | `/home/ubuntu/youtube-telegram-bot` |

### 외부 서비스

| 서비스 | 용도 | 접속 정보 |
|---|---|---|
| GitHub | 코드 저장소 | `hyacinth8507-arch/youtube-telegram-bot` |
| IPRoyal 프록시 | 자막 추출 시 IP 차단 우회 | `geo.iproyal.com:12321` |
| YouTube Data API v3 | 채널 최신 영상 조회 | API 키 인증 |
| Anthropic Claude API | AI 요약 | API 키 인증 |
| Telegram Bot API | 메시지 전송 | 봇 토큰 인증 |

---

## 3. 모니터링 중인 채널

### YouTube 채널 (6개)

| # | 채널명 | 채널 ID |
|---|---|---|
| 1 | 박종훈의 지식한방 | `UCOB62fKRT7b73X7tRxMuN2g` |
| 2 | 이효석아카데미 | `UCxvdCnvGODDyuvnELnLkQWw` |
| 3 | J UTOPIA | `UCJNK93wrXOA6YP4uBZ5I4Rw` |
| 4 | 월가아재의 과학적 투자 | `UCpqD9_OJNtF6suPpi6mOQCQ` |
| 5 | 미키피디아 | `UCt9m3iBPn0e0z0B_t-Va7sw` |
| 6 | 교양이를 부탁해 | `UChY8VUjXv0aA7RF9hDQ0ISg` |

### 네이버 블로그 (1개)

| # | 블로그명 | 블로그 ID |
|---|---|---|
| 1 | 메르의 블로그 | `ranto28` |

---

## 4. API 키 위치

### Oracle Cloud 서버 (.env)

파일 경로: `/home/ubuntu/youtube-telegram-bot/.env`

```
YOUTUBE_API_KEY=...       # Google Cloud Console에서 발급
ANTHROPIC_API_KEY=...     # Anthropic Console에서 발급
TELEGRAM_BOT_TOKEN=...    # @BotFather에서 발급
PROXY_URL=http://...@geo.iproyal.com:12321  # IPRoyal 프록시
```

### GitHub Actions (현재 비활성화)

GitHub Secrets에도 동일한 키가 등록되어 있으나, 워크플로우를 비활성화(`disabled_manually`)했으므로 사용되지 않음.

| Secret 이름 | 용도 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API |
| `ANTHROPIC_API_KEY` | Claude AI 요약 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅방 ID |

---

## 5. 자동 실행 방식

### Oracle Cloud 서버 crontab

```
*/30 * * * * cd /home/ubuntu/youtube-telegram-bot && PATH=/home/ubuntu/.local/bin:$PATH /usr/bin/python3 main.py >> /home/ubuntu/youtube-telegram-bot/logs/cron.log 2>&1
```

- **주기**: 30분마다 (매시 0분, 30분)
- **로그**: `/home/ubuntu/youtube-telegram-bot/logs/cron.log`
- **PATH**: yt-dlp가 `~/.local/bin`에 있어서 명시적으로 PATH에 추가

### GitHub Actions (비활성화됨)

- 워크플로우 이름: `YouTube Telegram Bot` (ID: 244042323)
- 상태: `disabled_manually`
- Oracle Cloud 서버와 중복 실행/충돌 방지를 위해 비활성화함

---

## 6. 비용 정리

| 서비스 | 비용 | 비고 |
|---|---|---|
| **Oracle Cloud 서버** | 무료 | Always Free Tier (ARM 1 OCPU, 1GB RAM) |
| **YouTube Data API v3** | 무료 | 일일 할당량 10,000 units. playlistItems.list는 1 unit/call로 매우 적게 사용 |
| **Anthropic Claude API** | 종량제 | claude-sonnet-4-20250514 기준. 영상 1개당 약 $0.01~0.03 (입력 토큰량에 따라 변동) |
| **IPRoyal 프록시** | 종량제 | 트래픽 기반 과금. 자막 추출은 소량 트래픽이므로 월 $1 미만 예상 |
| **Telegram Bot API** | 무료 | 제한 없음 |
| **GitHub** | 무료 | Public 저장소 |

### 월간 예상 비용

- 6개 채널 x 평균 주 3개 영상 = 월 약 72개 영상
- Anthropic API: 72개 x $0.02 = 약 **$1.5/월**
- IPRoyal: 약 **$0.5/월**
- **총 예상: $2/월 이내**

---

## 7. 문제 발생 시 대처법

### 7.1 서버 접속

**방법 1: 로컬 PC에서 SSH**

```bash
ssh -i "C:\Users\User\Downloads\ssh-key-2026-03-17.key" ubuntu@144.24.85.237
```

**방법 2: Oracle Cloud Shell (SSH 접속 불가 시)**

1. Oracle Cloud Console (cloud.oracle.com) 로그인
2. 우측 상단 Cloud Shell 아이콘 클릭
3. `ssh ubuntu@144.24.85.237` 실행

**방법 3: 직렬 콘솔 (서버 OS 문제 시)**

1. Oracle Cloud Console > 컴퓨트 > 인스턴스
2. 해당 인스턴스 클릭 > 콘솔 연결 > Cloud Shell 직렬 콘솔

### 7.2 로그 확인

```bash
# cron 실행 로그 (최근 100줄)
tail -100 ~/youtube-telegram-bot/logs/cron.log

# 앱 로그 (RotatingFileHandler, 최대 5MB x 3개)
tail -100 ~/youtube-telegram-bot/logs/bot.log

# 에러만 필터링
grep -i "error\|warning\|실패" ~/youtube-telegram-bot/logs/cron.log | tail -30

# crontab이 실행되고 있는지 확인
grep "youtube" /var/log/syslog | tail -10
```

### 7.3 프로그램 재시작 / 수동 실행

```bash
cd ~/youtube-telegram-bot

# 수동 1회 실행 (결과를 터미널에서 확인)
python3 main.py

# 백그라운드 실행
nohup python3 main.py > logs/manual.log 2>&1 &

# crontab 확인/편집
crontab -l       # 현재 설정 확인
crontab -e       # 편집
```

### 7.4 코드 업데이트

```bash
cd ~/youtube-telegram-bot
git pull origin main
```

### 7.5 채널 추가/삭제

`config.yaml` 파일을 수정:

```yaml
youtube:
  channels:
    - id: "UC새채널ID"        # UC로 시작하는 채널 ID
      name: "새 채널 이름"
    # 삭제할 채널은 해당 줄을 제거
```

채널 ID 찾는 방법:
1. YouTube 채널 페이지 접속
2. URL에서 `/channel/UC...` 부분이 채널 ID
3. URL이 `/@이름` 형태면 페이지 소스에서 `channelId` 검색

### 7.6 processed_videos.json 초기화

특정 영상을 다시 처리하고 싶을 때:

```bash
cd ~/youtube-telegram-bot

# 전체 초기화 (모든 영상 재처리)
echo '{"processed": [], "last_updated": "", "retry_counts": {}}' > data/processed_videos.json

# 특정 영상만 제거 (python3 사용)
python3 -c "
import json
with open('data/processed_videos.json', 'r') as f:
    data = json.load(f)
data['processed'] = [v for v in data['processed'] if v != '제거할_video_id']
with open('data/processed_videos.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
"
```

### 7.7 자주 발생하는 에러와 해결법

| 에러 | 원인 | 해결법 |
|---|---|---|
| `RequestBlocked` | YouTube가 자막 요청 IP 차단 | 프록시 설정 확인 (.env PROXY_URL) |
| `API key not valid` | YouTube API 키 문제 | Google Cloud Console에서 키 확인, API 제한사항 점검 |
| `quota exceeded` | YouTube API 할당량 초과 | 다음 날 자동 리셋 대기 (일일 10,000 units) |
| `Anthropic 520 에러` | Claude API 일시적 서버 에러 | 자동 재시도됨, 조치 불필요 |
| `Rate limit (429)` | API 호출 빈도 초과 | 자동 백오프 재시도됨 |
| `Forbidden (텔레그램)` | 봇 토큰 무효 또는 차단 | @BotFather에서 토큰 재발급 |

---

## 8. 주의사항

### API 키 보안

- `.env` 파일은 `.gitignore`에 포함되어 절대 GitHub에 올라가지 않음
- 서버의 `.env` 파일 권한 확인: `chmod 600 .env`
- API 키가 노출되면 즉시 재발급:
  - YouTube: Google Cloud Console > API 및 서비스 > 사용자 인증 정보
  - Anthropic: console.anthropic.com > API Keys
  - Telegram: @BotFather > /revoke

### IPRoyal 프록시

- 잔액이 소진되면 자막 추출이 실패하고 yt-dlp 폴백도 실패함
- 잔액 확인: https://dashboard.iproyal.com
- 자막 2회 연속 실패 시 요약 없이 알림만 전송됨 (자동 처리)

### 서버 관리

- Oracle Cloud Free Tier는 인스턴스를 장기간 미사용 시 회수될 수 있음
- 서버 시간대: UTC (한국 시간 = UTC + 9)
- 디스크 용량 확인: `df -h /` (현재 9% 사용, 42GB 여유)
- 로그 파일은 RotatingFileHandler로 자동 관리 (최대 5MB x 3개)

### YouTube API 할당량

- 일일 10,000 units
- `playlistItems.list`: 1 unit/call (6채널 x 1 call x 48회/일 = 288 units/일)
- 할당량 여유 충분하나, 채널 수를 대폭 늘리면 모니터링 필요

### 텔레그램

- 채팅방 ID: `-1003891906781` (그룹/채널은 음수 ID)
- 봇이 채팅방의 멤버/관리자여야 메시지 전송 가능
- 메시지 전송 Rate limit: 초당 약 30개 (분할 전송 시 0.5초 딜레이 적용)
