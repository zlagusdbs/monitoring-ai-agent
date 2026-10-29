import { useState } from "react";

import { Rule, Status, api } from "../api";

type Throttle = { type?: string; uri?: string; rate?: number; ttl_minutes?: number };

function ThrottleAction({ rule }: { rule: Rule }) {
  const action = rule.action as Throttle;
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<string>("");

  if (action?.type !== "throttle") return null;

  const label = `${action.uri} ${action.rate}% ${action.ttl_minutes}분`;
  if (rule.state !== "firing") {
    return (
      <div className="act">
        <code>발동 시: {label}</code>
      </div>
    );
  }

  const run = async () => {
    if (!confirm(`${action.uri} 를 ${action.rate}% 로 ${action.ttl_minutes}분간 차단합니다. 진행할까요?`))
      return;
    setBusy(true);
    const res = await api.throttle(action);
    setOut(JSON.stringify(res, null, 1));
    setBusy(false);
  };

  return (
    <>
      <div className="act">
        <code>{label}</code>
        <button disabled={busy} onClick={run}>
          차단 실행
        </button>
      </div>
      {out && <div className="out">{out}</div>}
    </>
  );
}

const ORDER: Record<string, number> = { firing: 0, skipped: 1, ok: 2 };

export function Rules({ status, onChanged }: { status: Status; onChanged: () => void }) {
  const rules = [...status.rules].sort((a, b) => (ORDER[a.state] ?? 9) - (ORDER[b.state] ?? 9));
  if (rules.length === 0) return <div className="foot">켜진 규칙이 없다</div>;

  return (
    <>
      {rules.map((r) => (
        <div className="rule" key={r.id}>
          <span className={`badge ${r.state}`}>{r.state}</span>
          <span style={{ flex: 1 }}>
            <span className="t">{r.title}</span> <span className="d">· {r.severity}</span>
            <button
              className="rbtn"
              onClick={async () => {
                await api.setRuleEnabled(r.id, false);
                onChanged();
              }}
            >
              끄기
            </button>
            <button
              className="rbtn"
              onClick={async () => {
                if (!confirm(`규칙 ${r.id} 을 지웁니다. 진행할까요?`)) return;
                await api.deleteRule(r.id);
                onChanged();
              }}
            >
              지우기
            </button>
            <div className="d">{r.detail}</div>
            <ThrottleAction rule={r} />
          </span>
        </div>
      ))}
    </>
  );
}
