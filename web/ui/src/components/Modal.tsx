import { ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";

type Props = {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
};

/** 바깥을 누르거나 Esc 를 눌러도 닫힌다. */
export function Modal({ title, onClose, children }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="overlay" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-h">
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
