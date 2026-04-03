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
- SQLAlchemy (async) + SQLite (기본) / PostgreSQL
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
| `DATABASE_URL` | | `sqlite+aiosqlite:///./data/ctfbot.db` | DB 연결 문자열 |
| `ADMIN_ROLE_NAME` | | `CTF Admin` | 관리자 역할 이름 |
| `LOG_LEVEL` | | `INFO` | 로깅 레벨 |
| `TIMEZONE` | | `UTC` | 타임존 |
| `CTFTIME_CACHE_TTL` | | `1800` | CTFTime 캐시 TTL (초) |
| `SCHEDULER_INTERVAL_MINUTES` | | `5` | 스케줄러 실행 간격 (분) |
| `ANNOUNCEMENT_CHANNEL` | | `ctf-일정` | 주간 CTFTime 요약 채널 |

### 3. 실행

**로컬:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

**Docker:**
```bash
docker compose up --build -d
```

### 4. 테스트

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Commands

### Admin (Manage Guild 권한 또는 CTF Admin 역할 필요)

| Command | Description |
|---------|-------------|
| `/create_ctf` | CTF 생성 (카테고리 + 채널 자동 생성) |
| `/delete_ctf` | CTF 삭제 (soft delete, 채널 선택 삭제) |
| `/reload_ctfbot` | 봇 확장 모듈 리로드 |

### User

| Command | Description |
|---------|-------------|
| `/join_ctf` | CTF 참가 |
| `/leave_ctf` | CTF 탈퇴 |
| `/add_challenge` | 문제 추가 |
| `/solve_challenge` | 문제 풀이 기록 |
| `/list_ctfs` | 서버 CTF 목록 |
| `/list_challenges` | CTF별 문제 목록 |
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

## Database

- **기본**: SQLite (zero-config)
- **프로덕션**: PostgreSQL 전환 가능
  ```
  DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/ctfbot
  ```
- 테이블은 시작 시 자동 생성 (`create_all`)
- Alembic 마이그레이션:
  ```bash
  alembic revision --autogenerate -m "description"
  alembic upgrade head
  ```

## Deployment

### EC2 + Docker

```bash
# t3.micro 이상 권장
sudo yum install -y docker
sudo systemctl enable --now docker
git clone <repo-url> ctfbot && cd ctfbot
cp .env.example .env && vim .env
docker compose up --build -d
```

- `ctfbot-data` 볼륨으로 SQLite DB 영속화
- `restart: unless-stopped`으로 자동 재시작
- 로그 확인: `docker compose logs -f ctfbot`

### ECS Fargate (대규모)

1. ECR에 이미지 푸시
2. ECS 태스크 정의 (환경 변수 + EFS or RDS)
3. desired count = 1 (싱글 인스턴스)

> **Secrets**: `DISCORD_TOKEN`은 AWS Secrets Manager 또는 Parameter Store 사용 권장

## License

MIT
