import { type ReactNode, useEffect, useRef, useState } from "react";

/**
 * Desplegable anclado a un botón: se abre y se cierra con el botón, al pulsar fuera o con Esc.
 * Esc lo atiende antes que los atajos de la planta, que así no cierran además otra cosa.
 */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setOpen(false);
    };
    window.addEventListener("pointerdown", onDown, true);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("pointerdown", onDown, true);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);
  return { open, setOpen, toggle: () => setOpen((o) => !o), close: () => setOpen(false), ref };
}

export function Popover({ pop, button, children, align = "right", up = false, className = "", anchorClassName = "" }: {
  pop: ReturnType<typeof usePopover>;
  button: ReactNode;
  children: ReactNode;
  align?: "left" | "right" | "center";
  up?: boolean; // se abre hacia arriba (en la barra de abajo)
  className?: string;
  anchorClassName?: string;
}) {
  return (
    <div className={`pop-anchor ${anchorClassName}`} ref={pop.ref}>
      {button}
      {pop.open ? <div className={`pop ${align}${up ? " up" : ""} ${className}`} role="dialog">{children}</div> : null}
    </div>
  );
}
