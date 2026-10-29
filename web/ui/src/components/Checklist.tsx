import { useEffect, useState } from "react";

import { Check, Settings, api } from "../api";
import { hhmmss } from "../ui";

const EVERY = [10, 30, 60];

const BADGE: Record<string, { label: string; cls: string }> = {
  ok: { label: "정상", cls: "ok" },
  fail: { label: "이상", cls: "firing" },
  unknown: { label: "미확인", cls: "skipped" },
  pending: { label: "확인 중", cls: "skipped" },
};

type Props = {
  tick: number;
  settings: Settings | null;
  onSettings: (values: Record<string, string>) => void;
};

export function Checklist({ tick, settings, onSettings }: Props) {
  const [rows, setRows] = useState<Check[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      setRows((await api.checks()).checks);
    } catch {
      /* 다음 주기에 다시 */
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [tick]);

  const run = async (name: string) => {
    setBusy(name);
    await api.runCheck(name);
    setBusy(null);
    load();
  };

  const rename = async (name: string) => {
    const next = prompt("새 이름", name)?.trim();
    if (!next || next === name) return;
    const res = await api.renameCheck(name, next);
    if (!res.ok) alert(res.error);
    load();
  };

  const remove = async (name: string) => {
    if (!confirm(`체크리스트에서 ${name} 을 지웁니다. 진행할까요?`)) return;
    await api.deleteCheck(name);
    load();
  };

  const auto = settings?.checklist_auto === "on";

  return (
    <>
      <div className="chartbar">
        <span className="who">{rows.length}개</span>
        <span className="ranges">
          <button
            className={`rbtn${auto ? " sel" : ""}`}
            onClick={() => onSettings({ checklist_auto: auto ? "off" : "on" })}
            title="켜면 주기마다 한 건씩 다시 확인한다"
          >
            자동 {auto ? "켬" : "끔"}
          </button>
          {auto &&
            EVERY.map((m) => (
              <button
                key={m}
                className={`rbtn${String(m) === settings?.checklist_every_min ? " sel" : ""}`}
                onClick={() => onSettings({ checklist_every_min: String(m) })}
              >
                {m}분
              </button>
            ))}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="foot">
          채팅에 <code>/check 이름 무엇을 확인할지</code> 로 항목을 만든다.
          <br />
          예: <code>/check indexer-coupon-all 상태확인</code>
          <br />
          이름에 공백이 있으면 따옴표로: <code>/check "coupon index alias" 상태확인</code>
        </div>
      ) : (
        rows.map((c) => (
          <div className="chk" key={c.name}>
            <div className="chk-h">
              <b className="chk-name" title="눌러서 이름을 바꾼다" onClick={() => rename(c.name)}>
                {c.name}
              </b>
              <span className={`badge ${BADGE[c.state]?.cls ?? "skipped"}`}>
                {BADGE[c.state]?.label ?? c.state}
              </span>
              <span className="w">{c.checked_at ? `${hhmmss(c.checked_at)} 확인` : "확인 전"}</span>
              <span className="chk-btns">
                <button className="rbtn" disabled={busy === c.name} onClick={() => run(c.name)}>
                  {busy === c.name ? "확인 중…" : "다시"}
                </button>
                <button className="rbtn" onClick={() => remove(c.name)}>
                  ×
                </button>
              </span>
            </div>
            <div className="chk-b">{c.result ?? c.question}</div>
          </div>
        ))
      )}
    </>
  );
}
