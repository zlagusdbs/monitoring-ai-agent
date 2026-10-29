import { ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { mem } from "../ui";

type Props = {
  /** 창마다 크기를 따로 기억한다. */
  id?: string;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
};

/** 바깥을 누르거나 Esc 를 눌러도 닫힌다. 오른쪽 아래 모서리를 끌면 크기가 바뀐다. */
export function Modal({ id = "modal", title, onClose, children }: Props) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const saved = mem.get(`ui:modal:${id}`);
    if (saved) {
      const [w, h] = saved.split("x");
      if (w && h) {
        el.style.width = w;
        el.style.height = h;
      }
    }
    // 끌어서 바꾼 크기만 기억한다. 기본값은 화면 크기를 따라가게 둔다.
    const ro = new ResizeObserver(() => {
      if (el.style.width && el.style.height) {
        mem.set(`ui:modal:${id}`, `${el.style.width}x${el.style.height}`);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [id]);

  const reset = () => {
    const el = box.current;
    if (!el) return;
    el.style.width = "";
    el.style.height = "";
    mem.set(`ui:modal:${id}`, "");
  };

  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div className="modal" ref={box} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-h" onDoubleClick={reset} title="두 번 누르면 크기가 처음으로">
          <div className="modal-t">{title}</div>
          <button className="rbtn" onClick={onClose} title="닫기 (Esc)">
            ×
          </button>
        </div>
        <div className="modal-b">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
