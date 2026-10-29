import { useEffect, useState } from "react";

import { SkillGroup, SkillLog, api } from "../api";
import { hm } from "../ui";

const SAMPLE: Record<string, string> = {
  rules: `# 늘 지킬 것

예)
- 숫자는 근거가 되는 값을 그대로 적는다.
- 확인 못 한 것은 미확인이라고 쓴다.
`,
  skills: `# 무엇을 먼저 보는지

예)
- 쿠폰 색인을 먼저 본다.
- 별칭 나이부터 확인하고 그다음 문서 수를 본다.
`,
};

const HELP: Record<string, string> = {
  root: "에이전트에 늘 들어가는 기본 지시다.\n여기서는 보기만 한다 — 고치려면 코드를 바꿔야 한다.",
  rules: "늘 지킬 것을 적는다.\n말투, 금지, 보고 형식 같은 것.",
  skills: "무엇을 어떻게 보는지 적는다.\n조사 순서, 런북 같은 것.",
};

type Open = { group: string; name: string; fixed: boolean };

export function Settings() {
  const [groups, setGroups] = useState<SkillGroup[]>([]);
  const [log, setLog] = useState<SkillLog[]>([]);
  const [open, setOpen] = useState<Open | null>(null);
  const [body, setBody] = useState("");
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [armed, setArmed] = useState("");  // 한 번 더 눌러야 지운다

  const load = async () => {
    const r = await api.skills();
    setGroups(r.groups);
    setLog(r.log);
    return r.groups;
  };

  useEffect(() => {
    load().then(() => pick("root", "base"));
  }, []);

  const pick = async (group: string, name: string) => {
    const r = await api.readSkill(group, name);
    setOpen({ group, name, fixed: r.fixed === true });
    setBody(r.body ?? "");
    setDirty(false);
    setNote("");
  };

  const create = async (group: string) => {
    const name = draft.trim();
    if (!name) return setAdding(null);
    const res = await api.writeSkill(group, name, SAMPLE[group] ?? "");
    if (!res.ok) return setNote(res.error);
    setAdding(null);
    setDraft("");
    await load();
    pick(group, name);
  };

  const save = async () => {
    if (!open || open.fixed) return;
    const res = await api.writeSkill(open.group, open.name, body);
    setNote(res.ok ? "저장했다" : res.error);
    if (res.ok) {
      setDirty(false);
      load();
    }
  };

  const remove = async (group: string, name: string) => {
    const key = `${group}/${name}`;
    if (armed !== key) {
      setArmed(key);
      return;
    }
    setArmed("");
    await api.deleteSkill(group, name);
    await load();
    if (open?.group === group && open?.name === name) pick("root", "base");
  };

  return (
    <div className="setting">
      <div className="setting-list">
        {groups.map((g) => (
          <div key={g.id} className="sgroup">
            <div className="sgroup-h">
              <span className="sgroup-n">{g.id}</span>
              <span className="qmark" title={HELP[g.id] ?? g.head}>
                ?
              </span>
              {!g.fixed && (
                <button
                  className="iconb add"
                  onClick={() => {
                    setAdding(adding === g.id ? null : g.id);
                    setDraft("");
                    setNote("");
                  }}
                  title="새 글"
                >
                  +
                </button>
              )}
            </div>
            {adding === g.id && (
              <input
                className="sadd"
                autoFocus
                placeholder="이름 (영소문자·숫자·하이픈)"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => create(g.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") create(g.id);
                  if (e.key === "Escape") setAdding(null);
                }}
              />
            )}
            {g.files.length === 0 ? (
              <div className="sgroup-empty">없음</div>
            ) : (
              g.files.map((n) => {
                const sel = open?.group === g.id && open?.name === n;
                return (
                  <div
                    key={n}
                    className={`setting-item${sel ? " sel" : ""}`}
                    onClick={() => pick(g.id, n)}
                  >
                    <span className="sfile">
                      {g.fixed ? "기본 지시" : `${n}.md`}
                    </span>
                    {!g.fixed && (
                      <button
                        className={`iconb del${armed === `${g.id}/${n}` ? " armed" : ""}`}
                        title="지우기 — 한 번 더 누르면 지워진다"
                        onClick={(e) => {
                          e.stopPropagation();
                          remove(g.id, n);
                        }}
                        onMouseLeave={() => setArmed("")}
                      >
                        {armed === `${g.id}/${n}` ? "지울까?" : "✕"}
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        ))}
        <div className="foot setting-foot">
          고친 내용은 다음 질문부터 바로 적용된다.
          <br />
          <b>도구와 권한은 바뀌지 않는다.</b>
        </div>
      </div>

      <div className="setting-edit">
        {open === null ? (
          <div className="foot">왼쪽에서 고르거나 새로 만든다</div>
        ) : (
          <>
            <div className="setting-h">
              <code>
                {open.group}/{open.name}
                {open.fixed ? "" : ".md"}
              </code>
              <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                {open.fixed ? (
                  <span className="foot">읽기 전용</span>
                ) : (
                  <button onClick={save} disabled={!dirty}>
                    저장
                  </button>
                )}
              </span>
            </div>
            <textarea
              value={body}
              readOnly={open.fixed}
              onChange={(e) => {
                setBody(e.target.value);
                setDirty(true);
                setNote("");
              }}
              spellCheck={false}
            />
            {note && <div className="foot">{note}</div>}
          </>
        )}

        {log.length > 0 && (
          <div className="setting-log">
            <b>최근 변경</b>
            {log.slice(0, 6).map((r, i) => (
              <div key={i} className="foot">
                {hm(r.ts)} · {r.name} · {r.what}
                {r.bytes != null ? ` (${r.bytes}B)` : ""}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
