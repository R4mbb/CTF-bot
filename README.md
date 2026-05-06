# CTF Bot

CTF 대회 참여를 관리하는 Discord 봇. 팀 단위 CTF 운영에 필요한 채널 관리, 문제 트래킹, CTFTime 연동을 제공합니다.

## Features

- **CTF 라이프사이클 관리** - 생성, 참가, 탈퇴, 아카이브, 삭제
- **자동 채널 생성** - CTF별 카테고리 + 기본 채널 (announcements, general, writeups, scoreboard, challenge-log)
- **가시성 제어** - 참가자만 채널 접근 가능, CTF 종료 시 자동 공개
- **문제 트래킹** - 문제 추가, 풀이 기록, CTF별 진행 상황 확인
- **CTFTime 연동** - 이번 주/이번 달 예정 대회 조회
- **백그라운드 스케줄러** - 종료된 CTF 자동 아카이브
- **감사 로깅** - 주요 액션 DB 기록

## Tech Stack

- Python 3.12+, discord.py 2.x
- SQLAlchemy (async) + **PostgreSQL** (기본) / SQLite (로컬 개발용)
- APScheduler, httpx, Alembic
- Docker / Docker Compose

## Quick Start

### 1. Discord Bot 생성

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 앱 생성
2. **Bot** 탭 → 토큰 복사, **Server Members Intent** 활성화
3. **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Manage Channels`, `Manage Roles`, `Send Messages`, `Embed Links`, `Use Slash Commands`
4. 생성된 URL로 서버에 봇 초대

### 2. 환경 변수

```bash
cp .env.example .env
# .env 파일에 DISCORD_TOKEN, DISCORD_APP_ID 입력
```

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `DISCORD_TOKEN` | O | - | Bot token |
| `DISCORD_APP_ID` | O | - | Application ID |
| `DEV_GUILD_ID` | | - | 개발용 Guild ID (즉시 커맨드 동기화) |
| `DATABASE_URL` | | `postgresql+asyncpg://ctfbot:ctfbot@db:5432/ctfbot` (compose) / `sqlite+aiosqlite:///./data/ctfbot.db` (local) | DB 연결 문자열 |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | | `ctfbot` | docker-compose Postgres 컨테이너 자격 정보 (DATABASE_URL과 일치 필요) |
| `ADMIN_ROLE_NAME` | | `CTF Admin` | 관리자 역할 이름 |
| `TEAM_ROLE_NAME` | | `팀원` | 팀원 역할 이름 |
| `LOG_LEVEL` | | `INFO` | 로깅 레벨 |
| `TIMEZONE` | | `UTC` | 내부 타임존 (표시는 항상 KST) |
| `CTFTIME_CACHE_TTL` | | `1800` | CTFTime 캐시 TTL (초) |
| `SCHEDULER_INTERVAL_MINUTES` | | `5` | 스케줄러 실행 간격 (분) |

### 3. 실행

**로컬:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

**Docker (Postgres 포함):**
```bash
# 첫 기동: db 서비스가 healthy 가 되면 봇이 자동으로 init_db() + create_all 수행
docker compose up --build -d

# 마이그레이션 적용 (스키마 진화 시):
docker compose exec ctfbot alembic upgrade head
```

**SQLite로 로컬 실행하려면** `.env` 의 `DATABASE_URL` 을 `sqlite+aiosqlite:///./data/ctfbot.db` 로 두고 `python -m bot.main` 을 직접 실행하세요.

### 4. 테스트

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Commands

### Admin (Manage Guild 권한 또는 CTF Admin 역할 필요)

| Command | Description |
|---------|-------------|
| `/create_ctf` | CTF 생성 (카테고리 + 채널 + 참가자 역할 자동 생성) |
| `/end_ctf` | CTF 수동 종료 (리더보드 게시 → 종료 리포트 → 역할 회수 → 채널 read-only) |
| `/delete_ctf` | CTF 삭제 (soft delete, 채널 + 역할 제거) |
| `/delete_challenge` | 문제 삭제 (DB + 채널) |
| `/reload_ctfbot` | 봇 확장 모듈 리로드 + 슬래시 명령 재동기화 |
| `/sync_commands` | 슬래시 명령만 강제 재동기화 |

### User

| Command | Description |
|---------|-------------|
| `/join_ctf` | CTF 참가 |
| `/leave_ctf` | CTF 탈퇴 |
| `/add_challenge` | 문제 추가 |
| `/solve_challenge` | 문제 풀이 기록 |
| `/list_ctfs` | 서버 CTF 목록 |
| `/list_challenges` | CTF별 문제 목록 |
| `/leaderboard` | CTF별 사용자 랭킹 (점수/풀이수) — `#scoreboard` 채널에 공개 게시 |
| `/ctf_info` | CTF 상세 정보 |
| `/upcoming_ctfs_week` | 이번 주 예정 CTF (CTFTime) |
| `/upcoming_ctfs_month` | 이번 달 예정 CTF (CTFTime) |

## Architecture

```
bot/
├── main.py                # 엔트리포인트
├── config.py              # 환경 변수 설정
├── db.py                  # Async SQLAlchemy 세션
├── scheduler.py           # APScheduler 백그라운드 작업
├── models/                # ORM 모델
├── services/              # 비즈니스 로직
├── cogs/                  # Slash command 그룹
├── integrations/          # 외부 API (CTFTime)
└── utils/                 # 권한 체크, Embed 빌더
```