import { ChangeEvent, ClipboardEvent, FormEvent, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { Section } from "./Section";

type Shot = { name: string; media_type: string; data: string; url: string };
type Msg = { who: "me" | "bot" | "tool"; text: string; shots?: Shot[] };
type Proposal = Record<string, string>;

const TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const MAX_BYTES = 4 * 1024 * 1024;

async function toShot(file: File): Promise<Shot | null> {
  if (!TYPES.includes(file.type) || file.size > MAX_BYTES) return null;
  const data: string = await new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1] ?? "");
    r.onerror = rej;
    r.readAsDataURL(file);
  });
  return {
    name: file.name || "붙여넣은 이미지",
    media_type: file.type,
    data,
    url: `data:${file.type};base64,${data}`,
  };
}

type Props = {
  plan: string[];
  onTool: (name: string) => void;
  onRuleSaved: () => void;
};

export function Chat({ plan, onTool, onRuleSaved }: Props) {
  const [log, setLog] = useState<Msg[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [shots, setShots] = useState<Shot[]>([]);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [round, setRound] = useState(0);
  const ws = useRef<WebSocket | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);

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
  }, [onTool, onRuleSaved, round]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [log, proposals, shots]);

  const add = async (files: FileList | File[] | null) => {
    if (!files) return;
    const next = (await Promise.all([...files].map(toShot))).filter(Boolean) as Shot[];
    if (next.length < [...files].length) alert("png·jpeg·gif·webp 만, 4MB 이하만 붙는다");
    setShots((s) => [...s, ...next].slice(0, 3));
  };

  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const files = [...e.clipboardData.items]
      .filter((i) => i.kind === "file")
      .map((i) => i.getAsFile())
      .filter(Boolean) as File[];
    if (files.length) {
      e.preventDefault();
      add(files);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if ((!q && shots.length === 0) || busy || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(
      JSON.stringify({
        text: q,
        images: shots.map(({ media_type, data }) => ({ media_type, data })),
      }),
    );
    setLog((l) => [...l, { who: "me", text: q, shots }]);
    setText("");
    setShots([]);
    setBusy(true);
  };

  const clear = () => {
    setLog([]);
    setProposals([]);
    setShots([]);
    setBusy(false);
    ws.current?.close();
    setRound((r) => r + 1); // 새로 연결하면 에이전트 대화도 처음부터 시작한다
  };

  const approve = async (rule: Proposal, i: number) => {
    await api.addRule(rule);
    setProposals((p) => p.filter((_, k) => k !== i));
    onRuleSaved();
  };

  return (
    <div className="panel chat">
      <h2 className="chat-h">
        채팅
        <button className="rbtn" onClick={clear} title="화면을 비우고 대화를 처음부터 시작한다">
          지우기
        </button>
      </h2>

      <div id="log">
        {log.map((m, i) => (
          <div key={i} className={m.who === "me" ? "me msg" : m.who === "tool" ? "tool" : "bot msg"}>
            {m.shots?.map((s, k) => (
              <img key={k} className="shot" src={s.url} alt={s.name} />
            ))}
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

      {shots.length > 0 && (
        <div className="shots">
          {shots.map((s, i) => (
            <span className="thumb" key={i}>
              <img src={s.url} alt={s.name} />
              <button onClick={() => setShots((v) => v.filter((_, k) => k !== i))}>×</button>
            </span>
          ))}
        </div>
      )}

      <form onSubmit={submit}>
        <input
          type="file"
          accept={TYPES.join(",")}
          multiple
          ref={picker}
          style={{ display: "none" }}
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          className="rbtn attach"
          onClick={() => picker.current?.click()}
          title="이미지 붙이기 (붙여넣기도 된다)"
        >
          🖼
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={onPaste}
          placeholder="무엇이든 물어보세요 — 이미지는 붙여넣기"
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
