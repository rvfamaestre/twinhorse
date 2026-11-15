import { useId } from "react";
import type { FlagId } from "../i18n/langs";

/**
 * Banderas dibujadas en SVG: Windows no pinta los emojis de bandera. Todas en una caja de 3:2;
 * la del Reino Unido (2:1) se recorta por los lados. España va sin escudo (bandera civil).
 */
const W = 21;
const H = 14;

function Spain() {
  return (
    <>
      <rect width="30" height="20" fill="#AA151B" />
      <rect y="5" width="30" height="10" fill="#F1BF00" />
    </>
  );
}

function France() {
  return (
    <>
      <rect width="30" height="20" fill="#fff" />
      <rect width="10" height="20" fill="#002654" />
      <rect x="20" width="10" height="20" fill="#CE1126" />
    </>
  );
}

function Usa() {
  const stripe = 20 / 13;
  const stars: [number, number][] = [];
  for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) stars.push([1.3 + c * 2.6 + (r % 2) * 1.3, 1.25 + r * 2.2]);
  return (
    <>
      <rect width="30" height="20" fill="#fff" />
      {Array.from({ length: 7 }, (_, k) => <rect key={k} y={k * 2 * stripe} width="30" height={stripe} fill="#B22234" />)}
      <rect width="13" height={stripe * 7} fill="#3C3B6E" />
      {stars.map(([x, y], k) => (x < 12.6 ? <circle key={k} cx={x} cy={y} r="0.45" fill="#fff" /> : null))}
    </>
  );
}

function Uk({ clip }: { clip: string }) {
  // Construcción estándar sobre 60 × 30, centrada en la caja de 30 × 20.
  return (
    <g transform="translate(-5 0) scale(0.6667)">
      <clipPath id={clip}>
        <path d="M30,15 h30 v15 z v15 h-30 z h-30 v-15 z v-15 h30 z" />
      </clipPath>
      <rect width="60" height="30" fill="#012169" />
      <path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" strokeWidth="6" />
      <path d="M0,0 L60,30 M60,0 L0,30" clipPath={`url(#${clip})`} stroke="#C8102E" strokeWidth="4" />
      <path d="M30,0 v30 M0,15 h60" stroke="#fff" strokeWidth="10" />
      <path d="M30,0 v30 M0,15 h60" stroke="#C8102E" strokeWidth="6" />
    </g>
  );
}

export function Flag({ id }: { id: FlagId }) {
  const clip = `uk${useId().replace(/:/g, "")}`;
  return (
    <svg className="flag" width={W} height={H} viewBox="0 0 30 20" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
      <svg viewBox="0 0 30 20" width="30" height="20" overflow="hidden">
        {id === "es" ? <Spain /> : id === "fr" ? <France /> : id === "us" ? <Usa /> : <Uk clip={clip} />}
      </svg>
    </svg>
  );
}

export function Flags({ ids }: { ids: FlagId[] }) {
  return (
    <span className="flags">
      {ids.map((f) => <Flag key={f} id={f} />)}
    </span>
  );
}
