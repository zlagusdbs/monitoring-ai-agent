# monitoring-ai-agent

색인 파이프라인 모니터링. 판단은 결정론적 규칙이 하고, LLM 은 설명과 제안을 맡는다.

## 구조

```
   Docker                              Host
   +--------------------+              +--------------------------+
   | collector 5분 주기 |              | web/server.py :8787      |
   | evaluator 규칙평가 |  --writes->  |   dashboard / chat / plan |
   +--------------------+              +------------+-------------+
            |                                       ^
            v                                       |
       data/monitor.db  <------- reads -------------+
```

- **collector** — Prometheus 에 없는 값(alias, 문서 수, 토픽 offset)을 긁어 SQLite 에 쌓는다.
  CPU·heap·검색량은 Prometheus 현재값을 찍고, Datadog 지표는 키가 있을 때만 수집한다.
- **evaluator** — LLM 을 쓰지 않는다. 같은 데이터면 항상 같은 결론이 나와야 감사가 된다.
- **agent** — 읽기 전용 도구 5개만 쥔다. 내장 도구와 `~/.claude` 설정은 전부 차단한다
  (`tools=[]`, `setting_sources=[]`, `skills=[]`).
- **web** — 호스트에서 돈다. 에이전트가 구독 인증을 쓰려면 호스트에 있어야 하기 때문이다.

## 설정

주소·대상·정책은 레포에 두지 않는다. `policy.example.json` 을 `policy.json` 으로 복사해
채운다. `policy.json` 은 `.gitignore` 에 있고, 컨테이너에는 읽기 전용으로 붙는다.

```bash
cp policy.example.json policy.json   # 그다음 값을 채운다
```

비어 있으면 수집과 차단이 모두 동작하지 않는다 — 조회를 건너뛰고 차단은 거부한다.

## 실행

```bash
docker compose up -d                              # 수집기 + 평가기
.venv/bin/python -m uvicorn web.server:app --port 8787
```

`.env` (선택):

```
DD_API_KEY=...
DD_APP_KEY=...
MON_THROTTLE_ENABLED=   # 비워 두면 throttling 이 실행되지 않고 curl 만 돌려준다
```

## 규칙

`rules` 테이블에 있다. 채팅으로 만들고 화면에서 승인하면 저장된다.
에이전트는 DB 를 읽기 전용으로 열므로 스스로 저장할 수 없다.

check 타입: `topic_offset_zero` · `alias_age_days` · `offset_stalled` · `metric_threshold`
guard 타입: `after_hour` · `active_cluster_known`

## throttling

켤 수 있는 URI 와 켜면 안 되는 URI 는 `policy.json` 에서 읽는다. 목록에 없는 URI 는
에이전트·서버 양쪽에서 막는다.

실행은 기본으로 꺼져 있다. 켜도 사람이 화면에서 눌러야 나간다.
