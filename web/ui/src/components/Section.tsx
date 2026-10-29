import { ReactNode, useEffect, useRef, useState } from "react";

import { mem } from "../ui";

type Props = {
  id: string;
  title: string;
  height?: number;
  resizable?: boolean;
  bodyClass?: string;
  children: ReactNode;
};

/** 제목을 누르면 접히고, 아래 모서리를 끌면 높이가 바뀐다. 둘 다 기억한다. */
export function Section({ id, title, height, resizable = true, bodyClass, children }: Props) {
  const key = `ui:${id}`;
  const [closed, setClosed] = useState(() => mem.get(`${key}:closed`) === "1");
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = body.current;
    if (!el || !resizable) return;
    const saved = mem.get(`${key}:h`);
    if (saved) el.style.height = saved;
    else if (height) el.style.height = `${height}px`;
    const observer = new ResizeObserver(() => {
      if (el.style.height) mem.set(`${key}:h`, el.style.height);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [key, height, resizable]);

  const toggle = () => {
    setClosed((was) => {
      mem.set(`${key}:closed`, was ? "0" : "1");
      return !was;
    });
  };

  return (
    <div className={`sec${closed ? " closed" : ""}`}>
      <h2 className="hd" onClick={toggle}>
        {title}
      </h2>
      <div
        ref={body}
        className={`bd${bodyClass ? ` ${bodyClass}` : ""}`}
        style={resizable ? undefined : { resize: "none" }}
      >
        {children}
      </div>
    </div>
  );
}
