import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Line as Series, Status, api } from "../api";
import { hm, ms, num } from "../ui";

const WINDOW_MIN = 120;

const METRICS = [
  "api_latency_p50_ms",
  "api_latency_p99_ms",
  "api_latency_max_ms",
  "api_rps",
  "endpoint_latency_p99_ms",
  "endpoint_latency_max_ms",
  "endpoint_rps",
];

type Point = Record<string, number>;

/** 지표별 시계열을 한 번에 받아 둔다. 그래프는 여기서 골라 쓴다. */
function useLines(minutes: number) {
  const [lines, setLines] = useState<Record<string, Series[]>>({});
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const results = await Promise.all(METRICS.map((m) => api.series(m, minutes)));
        if (!alive) return;
        setLines(Object.fromEntries(METRICS.map((m, i) => [m, results[i].lines])));
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
  }, [minutes]);
  return lines;
}

/** 여러 선을 같은 ts 로 묶어 한 표로 만든다. */
function merge(entries: { key: string; points: { ts: number; value: number }[] }[]): Point[] {
  const rows = new Map<number, Point>();
  for (const { key, points } of entries) {
    for (const p of points) {
      const row = rows.get(p.ts) ?? { ts: p.ts };
      row[key] = p.value;
      rows.set(p.ts, row);
    }
  }
  return [...rows.values()].sort((a, b) => a.ts - b.ts);
}

const pick = (lines: Series[] | undefined, resource?: string) =>
  (lines ?? []).find((l) => (resource ? l.labels.resource_name === resource : true))?.points ?? [];

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
  const empty = rows.length === 0;
  return (
    <div className="chart">
      <h3>{title}</h3>
      {empty ? (
        <div className="foot" style={{ height: 150, display: "grid", placeItems: "center" }}>
          이 구간에 수집된 값이 없다
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="ts"
              tickFormatter={(t) => hm(t)}
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
              tickFormatter={(v) => num(Number(v), 0)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--panel)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelFormatter={(t) => hm(Number(t))}
              formatter={(v, n) => [`${num(Number(v))} ${unit}`, String(n)]}
            />
            <Legend verticalAlign="top" height={18} iconSize={8} wrapperStyle={{ fontSize: 11 }} />
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
      )}
    </div>
  );
}

export function Traffic({ status }: { status: Status }) {
  const [focus, setFocus] = useState<string | null>(null);
  const lines = useLines(WINDOW_MIN);

  const latency = useMemo(
    () =>
      focus
        ? merge([
            { key: "p99", points: pick(lines.endpoint_latency_p99_ms, focus) },
            { key: "max", points: pick(lines.endpoint_latency_max_ms, focus) },
          ])
        : merge([
            { key: "p50", points: pick(lines.api_latency_p50_ms) },
            { key: "p99", points: pick(lines.api_latency_p99_ms) },
            { key: "max", points: pick(lines.api_latency_max_ms) },
          ]),
    [lines, focus],
  );
  const traffic = useMemo(
    () =>
      merge([
        {
          key: "rps",
          points: focus ? pick(lines.endpoint_rps, focus) : pick(lines.api_rps),
        },
      ]),
    [lines, focus],
  );

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
      <div className="chartbar">
        <span className="who">{focus ?? "전체"}</span>
        {focus && (
          <button className="rbtn" onClick={() => setFocus(null)}>
            전체로
          </button>
        )}
      </div>

      <div className="charts">
        <Chart
          title={`지연 — 최근 ${WINDOW_MIN / 60}시간 (로그 축)`}
          rows={latency}
          unit="ms"
          log
          lines={[
            ...(focus ? [] : [{ key: "p50", name: "p50", color: "var(--accent)" }]),
            { key: "p99", name: "p99", color: "var(--amber)" },
            { key: "max", name: "max", color: "var(--red)" },
          ]}
        />
        <Chart
          title={`요청 — 최근 ${WINDOW_MIN / 60}시간`}
          rows={traffic}
          unit="req/s"
          lines={[{ key: "rps", name: "req/s", color: "var(--green)" }]}
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
              <tr
                key={name}
                className={`clickable${name === focus ? " sel" : ""}`}
                onClick={() => setFocus(name === focus ? null : name)}
                title="눌러서 이 엔드포인트만 그래프로 본다"
              >
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
