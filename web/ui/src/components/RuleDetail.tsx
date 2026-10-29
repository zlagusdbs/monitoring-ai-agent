import { Rule, Settings } from "../api";
import { hm } from "../ui";

type Check = Record<string, unknown> & { type?: string };
type Guard = Record<string, unknown> & { type?: string };

const labelOf: Record<string, string> = {
  topic_offset_zero: "오늘자 토픽에 produce 가 0건인가",
  alias_age_days: "Active alias 가 며칠 지났는가",
  offset_stalled: "토픽 offset 이 멈췄는가",
  metric_threshold: "지표가 임계값을 넘었는가",
};

function describeCheck(check: Check): string {
  const v = (k: string) => String(check[k] ?? "");
  switch (check.type) {
    case "topic_offset_zero":
      return `${v("topic_prefix")}<오늘날짜> 의 produce 가 0건`;
    case "alias_age_days":
      return check.max_days == null
        ? `${v("alias")} alias — 기준 일수가 비어 있어 켤 수 없다`
        : `${v("alias")} alias 가 ${v("max_days")}일보다 오래됨`;
    case "offset_stalled":
      return `${v("topic")} 가 ${v("window_min")}분간 증가 없음`;
    case "metric_threshold":
      return `${v("metric")} ${v("op")} ${v("value")}${
        check.labels ? ` (${Object.entries(check.labels as object).map(([k, x]) => `${k}=${x}`).join(", ")})` : ""
      }`;
    default:
      return JSON.stringify(check);
  }
}

function describeGuard(guards: Guard[]): string {
  if (!guards?.length) return "없음 — 항상 평가한다";
  return guards
    .map((g) => {
      if (g.type === "after_hour") return `${g.hour}시 이전에는 건너뛴다`;
      if (g.type === "active_cluster_known") return "Active 클러스터를 모르면 건너뛴다";
      if (g.type === "paused_until")
        return `${new Date(Number(g.ts) * 1000).toLocaleString("ko-KR")} 까지 조치를 막는다`;
      return String(g.type);
    })
    .join(" · ");
}

export function RuleDetail({ rule, settings }: { rule: Rule; settings: Settings | null }) {
  const spec = rule.spec as { check?: Check; guard?: Guard[]; action?: Record<string, unknown> };
  const action = (rule.action ?? {}) as Record<string, unknown>;
  const hasAction = Object.keys(action).length > 0;
  const autoOn = settings?.auto_check === "on";
  const runOn = settings?.action_enabled === true;
  const severityOk = settings?.wake_severity !== "high" || rule.severity === "high";

  return (
    <div className="detail">
      <dl>
        <dt>보는 것</dt>
        <dd>
          {labelOf[String(spec.check?.type)] ?? spec.check?.type}
          <br />
          <code>{describeCheck(spec.check ?? {})}</code>
        </dd>

        <dt>건너뛰기</dt>
        <dd>{describeGuard(spec.guard ?? [])}</dd>

        <dt>지금 근거</dt>
        <dd>
          {rule.detail || "-"}
          <div className="d" style={{ fontSize: 11.5 }}>
            {rule.updated > rule.ts
              ? "규칙이 바뀐 뒤 아직 평가 전 — 다음 수집 주기(5분)에 다시 본다"
              : `${hm(rule.ts)} 판정`}
          </div>
        </dd>

        <dt>발동하면</dt>
        <dd>
          <ol>
            <li>화면에 firing 으로 표시된다</li>
            <li className={autoOn && hasAction && severityOk ? undefined : "off"}>
              {autoOn
                ? hasAction
                  ? severityOk
                    ? "에이전트가 1회 조사하고 실행/보류/사람호출 중 하나를 고른다"
                    : `심각도가 ${settings?.wake_severity} 기준보다 낮아 깨우지 않는다`
                  : "달린 조치가 없어 에이전트를 깨우지 않는다"
                : "자동 점검이 꺼져 있어 에이전트를 깨우지 않는다"}
            </li>
            <li className={hasAction ? undefined : "off"}>
              {!hasAction
                ? "조치가 없다 — 알림만 남는다"
                : runOn
                  ? "에이전트가 실행으로 판단하면 실제로 나간다"
                  : "실행이 꺼져 있어 기록만 남는다 (outcome=disabled)"}
            </li>
          </ol>
        </dd>

        {hasAction && (
          <>
            <dt>조치</dt>
            <dd>
              {action.type === "throttle" ? (
                <>
                  <code>
                    {String(action.uri)} {String(action.rate)}% · {String(action.ttl_minutes)}분
                  </code>
                  <br />
                  화면의 <b>차단 실행</b> 을 사람이 눌러야 나간다. {String(action.ttl_minutes)}분이
                  지나면 자동으로 풀린다.
                </>
              ) : (
                <code>{JSON.stringify(action)}</code>
              )}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}
