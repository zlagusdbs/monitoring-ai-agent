export type Labels = Record<string, string>;

export type Sample = { labels: Labels; value: number | null; text: string | null; ts: number };

export type Rule = {
  id: string;
  severity: string;
  title: string;
  state: string;
  detail: string;
  ts: number;
  spec: Record<string, unknown>;
  action: Record<string, unknown>;
};

export type Status = {
  ready: boolean;
  reason?: string;
  rules: Rule[];
  metrics: Record<string, Sample[]>;
  labels?: Record<string, string>;
  samples: number;
  last_collect: number;
  now: number;
};

export type Action = {
  ts: number;
  rule_id: string;
  action_id: string;
  verdict: string;
  reason: string;
  outcome: string | null;
  detail: string | null;
};

export type Finding = { ts: number; rule_id: string; state: string; detail: string };

export type Report = {
  started: number;
  now: number;
  items: Action[];
  findings: Finding[];
  todo: string[];
};

export type Settings = Record<string, string> & { action_enabled: boolean };

export type Line = { labels: Labels; points: { ts: number; value: number }[] };

export type Check = {
  name: string;
  question: string;
  result: string | null;
  state: string;
  checked_at: number | null;
  created: number;
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json() as Promise<T>;
}

async function send(path: string, body?: unknown, method = "POST") {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return r.json();
}

export const api = {
  status: () => get<Status>("/api/status"),
  report: () => get<Report>("/api/report"),
  settings: () => get<Settings>("/api/settings"),
  series: (metric: string, minutes = 120) =>
    get<{ lines: Line[] }>(`/api/series?metric=${encodeURIComponent(metric)}&minutes=${minutes}`),
  setSettings: (values: Record<string, string>) => send("/api/settings", values),
  setRuleEnabled: (id: string, enabled: boolean) =>
    send(`/api/rules/${encodeURIComponent(id)}/enabled`, { enabled }),
  deleteRule: (id: string) => send(`/api/rules/${encodeURIComponent(id)}`, undefined, "DELETE"),
  addRule: (rule: unknown) => send("/api/rules", rule),
  throttle: (body: unknown) => send("/api/throttle", body),
  checks: () => get<{ checks: Check[] }>("/api/checks"),
  runCheck: (name: string) => send(`/api/checks/${encodeURIComponent(name)}/run`),
  deleteCheck: (name: string) => send(`/api/checks/${encodeURIComponent(name)}`, undefined, "DELETE"),
};
