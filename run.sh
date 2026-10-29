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

start() {
  [ -x "$PY" ] || die "가상환경이 없다. python3 -m venv .venv && .venv/bin/pip install -r requirements-agent.txt"
  docker info >/dev/null 2>&1 || die "Docker 가 떠 있지 않다"
  if lsof -ti:"$PORT" >/dev/null 2>&1; then
    die "$PORT 포트를 이미 쓰고 있다. ./run.sh stop 먼저"
  fi

  echo "[1/2] 수집기 + 평가기"
  docker compose up -d --build
  echo
  echo "[2/2] 대시보드  ->  http://127.0.0.1:$PORT"
  echo "      Ctrl+C 로 대시보드만 멈춘다. 수집기는 계속 돈다 (./run.sh stop 으로 정리)"
  echo
  exec "$PY" -m uvicorn web.server:app --host 127.0.0.1 --port "$PORT"
}

stop() {
  docker compose down 2>/dev/null || true
  pkill -f "uvicorn web.server" 2>/dev/null && echo "대시보드 종료" || true
  echo "정리 완료. data/ 는 남겨 둔다"
}

status() {
  printf "수집기   : "
  docker ps --filter name=monitor-collector --format '{{.Status}}' 2>/dev/null | grep . || echo "내려감"
  printf "대시보드 : "
  lsof -ti:"$PORT" >/dev/null 2>&1 && echo "http://127.0.0.1:$PORT" || echo "내려감"
  printf "수집 DB  : "
  [ -f data/monitor.db ] && "$PY" -c "
import sqlite3,time
c=sqlite3.connect('file:data/monitor.db?mode=ro',uri=True)
n=c.execute('SELECT COUNT(*) FROM samples').fetchone()[0]
t=c.execute('SELECT MAX(ts) FROM samples').fetchone()[0] or 0
print(f'{n:,}행, 마지막 수집 {int(time.time())-t}초 전')" || echo "없음"
}

case "${1:-start}" in
  start)  start ;;
  stop)   stop ;;
  status) status ;;
  *)      echo "usage: ./run.sh [start|stop|status]" ;;
esac
