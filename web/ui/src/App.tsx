import { useCallback, useEffect, useRef, useState } from "react";

import { Status, api } from "./api";
import { Chat } from "./components/Chat";
import { Clusters, IndexPanel } from "./components/Metrics";
import { Report } from "./components/Report";
import { Rules } from "./components/Rules";
import { Section } from "./components/Section";
import { StatusBar } from "./components/StatusBar";
import { Traffic } from "./components/Traffic";
import { mem, num, usePoll } from "./ui";

function useSplitter() {
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const saved = mem.get("ui:chatw");
    if (saved) document.body.style.setProperty("--chatw", saved);
    const el = bar.current;
    if (!el) return;
    const down = (e: MouseEvent) => {
      e.preventDefault();
      el.classList.add("on");
      const move = (ev: MouseEvent) => {
        const w = `${Math.min(900, Math.max(260, innerWidth - ev.clientX - 14))}px`;
        document.body.style.setProperty("--chatw", w);
        mem.set("ui:chatw", w);
      };
      const up = () => {
        el.classList.remove("on");
        removeEventListener("mousemove", move);
        removeEventListener("mouseup", up);
      };
      addEventListener("mousemove", move);
      addEventListener("mouseup", up);
    };
    const reset = () => {
      document.body.style.setProperty("--chatw", "420px");
      mem.set("ui:chatw", "420px");
    };
    el.addEventListener("mousedown", down);
    el.addEventListener("dblclick", reset);
    return () => {
      el.removeEventListener("mousedown", down);
      el.removeEventListener("dblclick", reset);
    };
  }, []);
  return bar;
}

export default function App() {
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  const status = usePoll<Status>(() => api.status(), 10_000);
  const report = usePoll(() => api.report(), 10_000);
  const settings = usePoll(() => api.settings(), 10_000);
  const splitter = useSplitter();

  const [plan, setPlan] = useState<string[]>([]);
  const addPlan = useCallback((name: string) => setPlan((p) => [...p, `→ ${name}`]), []);

  useEffect(() => {
    if (tick) api.status().catch(() => undefined);
  }, [tick]);

  const toggleAuto = async (on: boolean) => {
    await api.setSettings({ auto_check: on ? "on" : "off" });
    refresh();
  };

  return (
    <>
      <div className="left">
        <StatusBar report={report} settings={settings} onToggleAuto={toggleAuto} />

        <div className="panel sec-wrap">
          <Section id="rep" title="켜 둔 동안 있었던 일" height={190}>
            <Report data={report} />
          </Section>
        </div>

        {status && !status.ready && <div className="panel foot">{status.reason}</div>}

        {status?.ready && (
          <>
            <div className="panel">
              <Section id="cl" title="클러스터">
                <Clusters status={status} />
              </Section>
              <Section id="ix" title="색인">
                <IndexPanel status={status} />
              </Section>
              <Section id="tf" title="트래픽 · 지연">
                <Traffic status={status} />
              </Section>
            </div>

            <div className="panel">
              <Section id="rules" title="규칙 판정" height={240}>
                <Rules status={status} onChanged={refresh} />
              </Section>
            </div>
          </>
        )}

        <div className="panel">
          <Section id="plan" title="Plan — 에이전트가 하는 일" height={120}>
            {plan.length === 0 ? (
              <div className="foot">대기 중</div>
            ) : (
              plan.map((line, i) => <div key={i}>{line}</div>)
            )}
          </Section>
        </div>

        {status && (
          <div className="foot" style={{ padding: "0 4px 4px" }}>
            표본 {num(status.samples, 0)}행 · 마지막 수집{" "}
            {Math.max(0, status.now - status.last_collect)}초 전
          </div>
        )}
      </div>

      <div className="split" ref={splitter} title="끌어서 폭 조절" />

      <Chat onTool={addPlan} onRuleSaved={refresh} />
    </>
  );
}
