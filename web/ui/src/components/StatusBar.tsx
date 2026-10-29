import { useEffect, useState } from "react";

import { Report, Settings } from "../api";

/** 서버가 준 남은 초에서 1초씩 깎는다. 새 값이 오면 거기에 맞춘다. */
function useCountdown(seconds: number | undefined) {
  const [left, setLeft] = useState(seconds ?? -1);
  useEffect(() => setLeft(seconds ?? -1), [seconds]);
  useEffect(() => {
    if (left < 0) return;
    const id = setInterval(() => setLeft((v) => (v > 0 ? v - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [left < 0]);
  return left;
}

const EVERY = [1, 5, 10, 30];

type Props = {
  report: Report | null;
  settings: Settings | null;
  onToggleAuto: (on: boolean) => void;
  onSettings: (values: Record<string, string>) => void;
};

export function StatusBar({ report, settings, onToggleAuto, onSettings }: Props) {
  const left = useCountdown(settings?.auto_next_in as number | undefined);
  if (!report || !settings) return <div className="bar">불러오는 중</div>;

  const on = settings.auto_check === "on";
  const acted = report.items.filter((a) => a.outcome === "sent").length;
  const escalated = report.items.filter((a) => a.verdict === "escalate").length;

  return (
    <div className="bar">
      <span>
        자동 점검{" "}
        <button className={`sw${on ? " on" : ""}`} onClick={() => onToggleAuto(!on)}>
          {on ? "켬" : "끔"}
        </button>
      </span>
      {on && (
        <span className="ranges">
          {EVERY.map((m) => (
            <button
              key={m}
              className={`rbtn${String(m) === settings.auto_every_min ? " sel" : ""}`}
              onClick={() => onSettings({ auto_every_min: String(m) })}
              title="규칙 발동을 확인하는 주기"
            >
              {m}분
            </button>
          ))}
          <span className="tick" title="다음 자동 점검까지 남은 시간">
            <span className={left === 0 ? "spin" : undefined}>⟳</span>
            {left >= 0 ? ` ${left}초` : ""}
          </span>
        </span>
      )}
      <span>
        오늘 <b>{report.items.length}</b>/{settings.daily_max}회
      </span>
      <span>
        조치 <b>{acted}</b>
      </span>
      <span>
        사람 호출 <b>{escalated}</b>
      </span>
      <span>실행 {settings.action_enabled ? "켜짐" : "꺼짐 (기록만)"}</span>
    </div>
  );
}
