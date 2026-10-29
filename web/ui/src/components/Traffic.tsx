import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Status, api } from "../api";
import { hhmmss, ms, num } from "../ui";

const LATENCY = ["api_latency_p50_ms", "api_latency_p99_ms", "api_latency_max_ms"] as const;
const WINDOW_MIN = 120;

type Point = Record<string, number>;

/** 여러 지표의 시계열을 같은 ts 로 묶어 한 표로 만든다. */
function useSeries(metrics: readonly string[], minutes: number) {
  const [rows, setRows] = useState<Point[]>([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const results = await Promise.all(metrics.map((m) => api.series(m, minutes)));
        const merged = new Map<number, Point>();
        results.forEach((res, i) => {
          const line = res.lines[0];
          if (!line) return;
          for (const p of line.points) {
            const row = merged.get(p.ts) ?? { ts: p.ts };
            row[metrics[i]] = p.value;
            merged.set(p.ts, row);
          }
        });
        if (alive) setRows([...merged.values()].sort((a, b) => a.ts - b.ts));
      } catch {
        /* 다음 주기에 다시 */
      }
    };
    load();
    const id = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [metrics.join(","), minutes]);
  return rows;
}

function Chart({
  title,
  rows,
  lines,
  unit,
  log,
}: {
  title: string;
  rows: Point[];
  lines: { key: string; name: string; color: string }[];
  unit: string;
  log?: boolean;
}) {
  return (
    <div className="chart">
      <h3>{title}</h3>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={rows} margin={{ top: 4, right: 6, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="ts"
            tickFormatter={(t) => hhmmss(t).slice(0, 5)}
            stroke="var(--dim)"
            fontSize={10}
            minTickGap={40}
          />
          {/* p50 과 max 는 자릿수가 달라서 선형 축이면 p50 이 바닥에 눌린다. */}
          <YAxis
            stroke="var(--dim)"
            fontSize={10}
            width={46}
            scale={log ? "log" : "auto"}
            domain={log ? [(min: number) => Math.max(1, min * 0.8), "auto"] : undefined}
            allowDataOverflow={false}
            tickFormatter={(v) => num(Number(v), 0)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--line)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(t) => hhmmss(Number(t))}
            formatter={(v, n) => [`${num(Number(v))} ${unit}`, String(n)]}
          />
          {lines.map((l) => (
            <Line
              key={l.key}
              type="monotone"
              dataKey={l.key}
              name={l.name}
              stroke={l.color}
              strokeWidth={1.6}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Traffic({ status }: { status: Status }) {
  const latency = useSeries(LATENCY, WINDOW_MIN);
  const rps = useSeries(["api_rps"], WINDOW_MIN);

  const one = (metric: string) => (status.metrics[metric] ?? [])[0];
  const connected = (status.metrics.api_rps ?? status.metrics.api_latency_p99_ms ?? []).length > 0;

  if (!connected) {
    return (
      <div className="card">
        <div className="k">Datadog</div>
        <div className="v">미연결 (DD_API_KEY 필요)</div>
      </div>
    );
  }

  const endpoints: Record<string, { rps?: number; p99?: number; max?: number; e5xx?: number }> = {};
  const put = (metric: string, key: "rps" | "p99" | "max") => {
    for (const s of status.metrics[metric] ?? []) {
      const name = s.labels.resource_name;
      if (!name || s.value == null) continue;
      (endpoints[name] ??= {})[key] = s.value;
    }
  };
  put("endpoint_rps", "rps");
  put("endpoint_latency_p99_ms", "p99");
  put("endpoint_latency_max_ms", "max");
  for (const s of status.metrics.endpoint_status_rps ?? []) {
    const name = s.labels.resource_name;
    const code = String(s.labels["http.status_code"] ?? "");
    if (!name || !code.startsWith("5")) continue;
    const row = (endpoints[name] ??= {});
    row.e5xx = (row.e5xx ?? 0) + (s.value ?? 0);
  }
  const rows = Object.entries(endpoints).sort((a, b) => (b[1].rps ?? 0) - (a[1].rps ?? 0));

  return (
    <>
      <div className="charts">
        <Chart
          title={`지연 (최근 ${WINDOW_MIN / 60}시간 · 로그 축)`}
          rows={latency}
          unit="ms"
          log
          lines={[
            { key: "api_latency_p50_ms", name: "p50", color: "var(--accent)" },
            { key: "api_latency_p99_ms", name: "p99", color: "var(--amber)" },
            { key: "api_latency_max_ms", name: "max", color: "var(--red)" },
          ]}
        />
        <Chart
          title={`요청 (최근 ${WINDOW_MIN / 60}시간)`}
          rows={rps}
          unit="req/s"
          lines={[{ key: "api_rps", name: "req/s", color: "var(--green)" }]}
        />
      </div>

      <div className="cards" style={{ marginBottom: 9 }}>
        <div className="card">
          <div className="k">요청</div>
          <div className="v">{num(one("api_rps")?.value)} req/s</div>
        </div>
        <div className="card">
          <div className="k">p50</div>
          <div className="v">{ms(one("api_latency_p50_ms")?.value)}</div>
        </div>
        <div className="card">
          <div className="k">p99</div>
          <div className="v">{ms(one("api_latency_p99_ms")?.value)}</div>
        </div>
        <div className="card">
          <div className="k">max</div>
          <div className="v">{ms(one("api_latency_max_ms")?.value)}</div>
        </div>
      </div>

      {rows.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>엔드포인트</th>
              <th>요청/s</th>
              <th>p99</th>
              <th>max</th>
              <th>5xx</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, e]) => (
              <tr key={name}>
                <td className="ep">{name}</td>
                <td>{num(e.rps)}</td>
                <td>{ms(e.p99)}</td>
                <td>{ms(e.max)}</td>
                <td className={e.e5xx ? "bad" : undefined}>{num(e.e5xx ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
