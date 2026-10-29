import { useEffect, useRef, useState } from "react";

export const mem = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* 사생활 보호 모드 등에서 막힐 수 있다. 화면은 그대로 돈다. */
    }
  },
};

/** 일정 주기로 다시 불러온다. 실패하면 직전 값을 그대로 둔다. */
export function usePoll<T>(load: () => Promise<T>, ms: number, bump = 0): T | null {
  const [value, setValue] = useState<T | null>(null);
  const fn = useRef(load);
  fn.current = load;
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await fn.current();
        if (alive) setValue(next);
      } catch {
        /* 다음 주기에 다시 시도한다 */
      }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [ms, bump]);
  return value;
}

export const hhmmss = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString("ko-KR", { hour12: false });

export const num = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : v.toLocaleString(undefined, { maximumFractionDigits: digits });

export const ms = (v: number | null | undefined) => (v == null ? "-" : `${num(v)} ms`);
