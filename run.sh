#!/usr/bin/env bash
# 수집기(Docker)와 대시보드(호스트)를 한 번에 띄운다.
#
# 대시보드는 Docker 에 넣지 않는다. 에이전트가 쓰는 구독 인증이
# 호스트의 Claude Code 로그인에 묶여 있기 때문이다.
set -euo pipefail

cd "$(dirname "$0")"
PORT="${PORT:-8787}"
PY=".venv/bin/python"

die() { echo "error: $*" >&2; exit 1; }

# 소스가 바뀌었거나 산출물이 없을 때만 다시 빌드한다.
build_ui() {
  local newest
  newest=$(find web/ui/src web/ui/index.html web/ui/package.json -newer web/static/index.html 2>/dev/null | head -1 || true)
  if [ -f web/static/index.html ] && [ -z "$newest" ]; then
    echo "      이미 최신"
    return
  fi
  command -v npm >/dev/null 2>&1 || die "npm 이 없다. 화면을 빌드하려면 Node 가 필요하다"
  [ -d web/ui/node_modules ] || (cd web/ui && npm install --no-audit --no-fund)
  (cd web/ui && npm run build >/dev/null) || die "화면 빌드 실패 — cd web/ui && npm run build 로 확인"
  echo "      빌드 완료"
}

start() {
  [ -x "$PY" ] || die "가상환경이 없다. python3 -m venv .venv && .venv/bin/pip install -r requirements-agent.txt"
  docker info >/dev/null 2>&1 || die "Docker 가 떠 있지 않다"
  if lsof -ti:"$PORT" >/dev/null 2>&1; then
    die "$PORT 포트를 이미 쓰고 있다. ./run.sh stop 먼저"
  fi

  [ -f policy.json ] || die "policy.json 이 없다. cp policy.example.json policy.json 로 만들고 값을 채운다"

  echo "[1/3] Postgres + 수집기 + 평가기"
  docker compose up -d --build
  echo
  echo "[2/3] 화면"
  build_ui
  echo
  echo "[3/3] 대시보드  ->  http://127.0.0.1:$PORT"
  echo "      Ctrl+C 로 대시보드만 멈춘다. DB·수집기는 계속 돈다 (./run.sh stop 으로 정리)"
  echo
  exec "$PY" -m uvicorn web.server:app --host 127.0.0.1 --port "$PORT"
}

stop() {
  docker compose down 2>/dev/null || true
  pkill -f "uvicorn web.server" 2>/dev/null && echo "대시보드 종료" || true
  echo "정리 완료. DB 볼륨(pgdata)은 남겨 둔다"
}

status() {
  printf "DB       : "
  docker exec monitor-postgres pg_isready -U monitor -d monitor 2>/dev/null || echo "내려감"
  printf "수집기   : "
  docker ps --filter name=monitor-collector --format '{{.Status}}' 2>/dev/null | grep . || echo "내려감"
  printf "대시보드 : "
  lsof -ti:"$PORT" >/dev/null 2>&1 && echo "http://127.0.0.1:$PORT" || echo "내려감"
  printf "수집 행수: "
  docker exec monitor-postgres psql -U monitor -d monitor -tAc \
    "SELECT COUNT(*) || '행, 마지막 수집 ' || (EXTRACT(EPOCH FROM now())::bigint - COALESCE(MAX(ts),0)) || '초 전' FROM samples" \
    2>/dev/null || echo "조회 실패"
}

case "${1:-start}" in
  start)  start ;;
  stop)   stop ;;
  status) status ;;
  *)      echo "usage: ./run.sh [start|stop|status]" ;;
esac
