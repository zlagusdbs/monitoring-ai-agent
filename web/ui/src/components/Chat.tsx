import { FormEvent, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { Section } from "./Section";

type Msg = { who: "me" | "bot" | "tool"; text: string };
type Proposal = Record<string, string>;

type Props = {
  plan: string[];
  onTool: (name: string) => void;
  onRuleSaved: () => void;
};

export function Chat({ plan, onTool, onRuleSaved }: Props) {
  const [log, setLog] = useState<Msg[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const ws = useRef<WebSocket | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let closed = false;
    const connect = () => {
      const socket = new WebSocket(`ws://${location.host}/ws/chat`);
      ws.current = socket;
      socket.onclose = () => {
        if (!closed) setTimeout(connect, 2000);
      };
      socket.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "text") setLog((l) => [...l, { who: "bot", text: m.text }]);
        else if (m.type === "tool") {
          const name = String(m.name).replace("mcp__ops__", "");
          onTool(name);
          setLog((l) => [...l, { who: "tool", text: `↳ ${name}` }]);
        } else if (m.type === "proposal") setProposals((p) => [...p, m.rule]);
        else if (m.type === "checks") onRuleSaved();
        else if (m.type === "error") {
          setLog((l) => [...l, { who: "bot", text: `오류: ${m.text}` }]);
          setBusy(false);
        } else if (m.type === "done") setBusy(false);
      };
    };
    connect();
    return () => {
      closed = true;
      ws.current?.close();
    };
  }, [onTool]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [log, proposals]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || busy || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(q);
    setLog((l) => [...l, { who: "me", text: q }]);
    setText("");
    setBusy(true);
  };

  const approve = async (rule: Proposal, i: number) => {
    await api.addRule(rule);
    setProposals((p) => p.filter((_, k) => k !== i));
    onRuleSaved();
  };

  return (
    <div className="panel chat">
      <h2>채팅</h2>
      <div id="log">
        {log.map((m, i) => (
          <div key={i} className={m.who === "me" ? "me msg" : m.who === "tool" ? "tool" : "bot msg"}>
            {m.text}
          </div>
        ))}
        {proposals.map((rule, i) => (
          <div className="prop" key={`p${i}`}>
            <div className="h">규칙 제안 — {rule.rule_id}</div>
            <pre>{JSON.stringify(rule, null, 1)}</pre>
            <button onClick={() => approve(rule, i)}>승인</button>
            <button className="no" onClick={() => setProposals((p) => p.filter((_, k) => k !== i))}>
              거절
            </button>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="무엇이든 물어보세요"
          autoComplete="off"
        />
        <button disabled={busy}>보내기</button>
      </form>
      <Section id="plan" title="Plan — 에이전트가 하는 일" height={90}>
        {plan.length === 0 ? (
          <div className="foot">대기 중 — 채팅으로 물어보면 어떤 도구를 쓰는지 여기 쌓인다</div>
        ) : (
          plan.map((line, i) => <div key={i}>{line}</div>)
        )}
      </Section>
    </div>
  );
}
