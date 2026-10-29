# monitoring-ai-agent

색인 파이프라인 모니터링. 판단은 결정론적 규칙이 하고, LLM 은 설명과 제안을 맡는다.

## 구조

```
   Docker                                 Host
   +------------------------+             +--------------------------+
   | postgres  :5433        |  <--------  | web/server.py :8787      |
   | collector 5분 주기     |   읽고 씀   |   dashboard / chat / plan |
   | evaluator 규칙평가     |             |   자동 점검 · 조치 실행   |
   +------------------------+             +--------------------------+
```

- **postgres** — 관측값·규칙·판정·조치를 담는다. 호스트에는 `127.0.0.1:5433` 으로만 열린다.
- **collector** — Prometheus 에 없는 값(alias, 문서 수, 토픽 offset)을 긁어 쌓는다.
  CPU·heap·검색량은 Prometheus 현재값을 찍고, Datadog 지표는 키가 있을 때만 수집한다.
- **evaluator** — LLM 을 쓰지 않는다. 같은 데이터면 항상 같은 결론이 나와야 감사가 된다.
- **agent** — 읽기 전용 도구만 쥔다. DB 도 `monitor_ro` 역할로 붙어 쓰기가 불가능하다.
  내장 도구와 `~/.claude` 설정은 전부 차단한다 (`tools=[]`, `setting_sources=[]`, `skills=[]`).
- **web** — 호스트에서 돈다. 에이전트가 구독 인증을 쓰려면 호스트에 있어야 하기 때문이다.
- **화면** — React + Vite (`web/ui`). 빌드 결과는 `web/static` 으로 나가고 FastAPI 가 서빙한다.
  `run.sh` 가 소스가 바뀌었을 때만 다시 빌드한다. 산출물은 `.gitignore` 에 있다.

## 설정

주소·대상·정책은 레포에 두지 않는다. `policy.example.json` 을 `policy.json` 으로 복사해
채운다. `policy.json` 은 `.gitignore` 에 있고, 컨테이너에는 읽기 전용으로 붙는다.

```bash
cp policy.example.json policy.json   # 그다음 값을 채운다
cp .env.example .env                 # 선택 — 비밀번호·Datadog 키
```

`policy.json` 이 비어 있으면 수집과 차단이 모두 동작하지 않는다 — 조회를 건너뛰고 차단은 거부한다.

## 실행

```bash
./run.sh start      # postgres + 수집기 + 화면 빌드 + 대시보드
./run.sh status
./run.sh stop       # DB 볼륨(pgdata)은 남는다
```

화면만 고칠 때는 Vite 개발 서버가 빠르다. `/api` 와 `/ws` 는 8787 로 넘어간다.

```bash
cd web/ui && npm run dev     # http://127.0.0.1:5173
```

대시보드만 따로 띄우려면:

```bash
.venv/bin/python -m uvicorn web.server:app --host 127.0.0.1 --port 8787
```

## 저장소

| 역할 | 쓰는 쪽 | 접속 |
|---|---|---|
| `monitor` | collector · web | `postgresql://monitor@127.0.0.1:5433/monitor` |
| `monitor_ro` | agent (읽기만) | 같은 DB, `SELECT` 만 가능 |

테이블: `samples` · `rules` · `findings` · `actions` · `settings`

SQLite 에서 옮겨 왔다면 한 번만 돌린다.

```bash
.venv/bin/python tools/migrate_sqlite.py data/monitor.db
```

## 테스트

Postgres 가 떠 있어야 한다. 테스트마다 임시 스키마를 만들고 끝나면 지운다.

```bash
docker compose up -d postgres
.venv/bin/python -m pytest tests -v
```

## 규칙

`rules` 테이블에 있다. 채팅으로 만들고 화면에서 승인하면 저장된다.
기본 규칙은 꺼진 채로 들어가며, 임계값을 정해야 켤 수 있다.

check 타입: `topic_offset_zero` · `alias_age_days` · `offset_stalled` · `metric_threshold`
guard 타입: `after_hour` · `active_cluster_known` · `paused_until`

## 조치

카탈로그에 등록된 것만 실행된다. 에이전트는 후보를 만들 수 없고 `execute` / `hold` /
`escalate` 중 하나만 돌려준다. 실행과 기록은 서버가 한다.

기본으로 꺼져 있다. `MON_ACTION_ENABLED` 를 켜야 실제로 나가고, 꺼진 동안에는
`outcome=disabled` 로 "실행했을 것" 기록만 남는다.

## throttling

켤 수 있는 URI 와 켜면 안 되는 URI 는 `policy.json` 에서 읽는다. 목록에 없는 URI 는
에이전트·서버 양쪽에서 막는다. 실행은 기본으로 꺼져 있고, 켜도 사람이 화면에서 눌러야 나간다.
