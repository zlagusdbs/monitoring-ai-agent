import { Report, Settings } from "../api";
import { hhmmss } from "../ui";

const EVERY = [1, 5, 10, 30];

type Props = {
  report: Report | null;
  settings: Settings | null;
  onToggleAuto: (on: boolean) => void;
  onSettings: (values: Record<string, string>) => void;
};

export function StatusBar({ report, settings, onToggleAuto, onSettings }: Props) {
  if (!report || !settings) return <div className="bar">불러오는 중</div>;

  const on = settings.auto_check === "on";
  const acted = report.items.filter((a) => a.outcome === "sent").length;
  const escalated = report.items.filter((a) => a.verdict === "escalate").length;
  const minutes = Math.floor((report.now - report.started) / 60);

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
      <span>
        {hhmmss(report.started)} 켬 · {minutes}분
      </span>
    </div>
  );
}
