import { Sample, Status } from "../api";
import { num } from "../ui";

const by = (rows: Sample[] | undefined, key: (l: Record<string, string>) => string) =>
  Object.fromEntries((rows ?? []).map((s) => [key(s.labels), s]));

function Card({ k, v }: { k: string; v: string }) {
  return (
    <div className="card">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}

function Row({ label, cards }: { label: string; cards: [string, string][] }) {
  return (
    <div className="row">
      <div className="rowlab">{label}</div>
      {cards.map(([k, v]) => (
        <Card key={k} k={k} v={v} />
      ))}
    </div>
  );
}

export function Clusters({ status }: { status: Status }) {
  const names = [...new Set((status.metrics.cluster_status ?? []).map((s) => s.labels.cluster))].sort();
  const state = by(status.metrics.cluster_status, (l) => l.cluster);
  const cpu = by(status.metrics.es_cpu_percent, (l) => l.cluster);
  const heap = by(status.metrics.es_heap_percent, (l) => l.cluster);
  const qps = by(status.metrics.es_search_qps, (l) => l.cluster);

  if (names.length === 0) return <div className="foot">수집된 클러스터가 없다</div>;

  return (
    <>
      {names.map((c) => (
        <Row
          key={c}
          label={c}
          cards={[
            ["상태", state[c]?.text ?? "-"],
            ["CPU", `${num(cpu[c]?.value)} %`],
            ["Heap", `${num(heap[c]?.value)} %`],
            ["검색", qps[c]?.value != null ? `${num(qps[c].value, 0)} q/s` : "-"],
          ]}
        />
      ))}
    </>
  );
}

export function IndexPanel({ status }: { status: Status }) {
  const clusters = [...new Set((status.metrics.cluster_status ?? []).map((s) => s.labels.cluster))].sort();
  const aliases = [...new Set((status.metrics.alias_index ?? []).map((s) => s.labels.alias))].sort();
  const alias = by(status.metrics.alias_index, (l) => `${l.cluster}|${l.alias}`);
  const docs = by(status.metrics.index_docs, (l) => `${l.cluster}|${l.index}`);

  const topics: [string, string][] = (status.metrics.topic_offset_latest ?? []).map((s) => [
    s.labels.topic.replace(/^indexed\d+_/, ""),
    num(s.value ?? 0, 0),
  ]);

  return (
    <>
      {clusters.map((c) => (
        <Row
          key={c}
          label={c}
          cards={aliases.map((a) => {
            const index = alias[`${c}|${a}`];
            const count = index?.text ? docs[`${c}|${index.text}`] : undefined;
            const value = index?.text
              ? `${index.text}${count?.value != null ? `  (${num(count.value, 0)})` : ""}`
              : "-";
            return [a, value];
          })}
        />
      ))}
      {topics.length > 0 && <Row label="토픽" cards={topics} />}
    </>
  );
}
