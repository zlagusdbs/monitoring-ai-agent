import { Report as ReportData } from "../api";
import { hm } from "../ui";

type Row =
  | { kind: "finding"; ts: number; ruleId: string; detail: string }
  | {
      kind: "action";
      ts: number;
      actionId: string;
      verdict: string;
      outcome: string | null;
      reason: string;
      detail: string | null;
    };

export function Report({ data }: { data: ReportData | null }) {
  if (!data) return <div className="foot">불러오는 중</div>;

  const rows: Row[] = [
    ...data.findings
      .filter((f) => f.state === "firing")
      .map((f) => ({ kind: "finding" as const, ts: f.ts, ruleId: f.rule_id, detail: f.detail })),
    ...data.items.map((a) => ({
      kind: "action" as const,
      ts: a.ts,
      actionId: a.action_id || "-",
      verdict: a.verdict,
      outcome: a.outcome,
      reason: a.reason,
      detail: a.detail,
    })),
  ].sort((a, b) => a.ts - b.ts);

  if (rows.length === 0) return <div className="foot">기록 없음</div>;

  return (
    <>
      {rows.map((row, i) => (
        <div className="ev" key={i}>
          <span className="w">{hm(row.ts)}</span>{" "}
          {row.kind === "finding" ? (
            <>
              <b>{row.ruleId}</b> 발동
              <div className="sub r">{row.detail}</div>
            </>
          ) : (
            <>
              <b>{row.actionId}</b> <span className={`v-${row.verdict}`}>{row.verdict}</span>{" "}
              {row.outcome && <span className="w">({row.outcome})</span>}
              <div className="sub r">
                {row.reason}
                {row.detail ? ` · ${row.detail}` : ""}
              </div>
            </>
          )}
        </div>
      ))}
      {data.todo.length > 0 && (
        <div className="todo">
          <b>지금 할 일</b>
          {data.todo.map((t, i) => (
            <div className="r" key={i}>
              · {t}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
