import { useEffect, useMemo, useState } from "react";
import { dayLong, num, parseDay } from "../domain/format";
import { pieces } from "../sim/inputs";
import { useT } from "../i18n";
import { useUI } from "../state/ui";
import { useDash } from "./ctx";
import { IconCalendar, IconDown, IconLeft, IconRight } from "./icons";
import { Popover, usePopover } from "./Popover";

const iso = (y: number, m: number, d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const monthOf = (day: string) => day.slice(0, 7);

/**
 * Calendario para elegir el día. Solo se pueden pulsar los días con datos; cada uno lleva los
 * motores que salieron. Los días que la limpieza descartó salen tachados.
 */
export function DayPicker() {
  const T = useT();
  const MONTHS = T.cal.months;
  const { model, day, run } = useDash();
  const setDay = useUI((s) => s.setDay);
  const pop = usePopover();
  const { days, excluded_days } = model.state.meta;
  const have = useMemo(() => new Set(days), [days]);
  const excluded = useMemo(() => new Set(excluded_days ?? []), [excluded_days]);
  const made = useMemo(() => {
    const sink = model.g.nodes[run.sink]?.station;
    return new Map(sink?.daily.map((d) => [d.day, pieces(d)]) ?? []);
  }, [model, run.sink]);
  const months = useMemo(() => [...new Set(days.map(monthOf))].sort(), [days]);
  const last = days[days.length - 1];
  const [month, setMonth] = useState(() => monthOf(day));
  useEffect(() => {
    if (pop.open) setMonth(monthOf(day));
  }, [pop.open, day]);

  const [y, m] = month.split("-").map(Number);
  const first = parseDay(iso(y, m - 1, 1));
  const lead = (first.getDay() + 6) % 7; // lunes primero
  const count = new Date(y, m, 0).getDate();
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: count }, (_, k) => iso(y, m - 1, k + 1))];
  const mi = months.indexOf(month);

  const pick = (d: string) => {
    setDay(d);
    pop.close();
  };

  return (
    <Popover
      pop={pop}
      up
      className="cal-pop"
      button={
        <button className={`day-btn${pop.open ? " on" : ""}`} onClick={pop.toggle} aria-expanded={pop.open} aria-label={T.cal.choose(dayLong(day))}>
          <IconCalendar />
          <span>{dayLong(day)}</span>
          <small>{T.cal.motors(num(made.get(day), 0))}</small>
          <IconDown />
        </button>
      }
    >
      <header className="cal-head">
        <button className="icon-btn ghost" onClick={() => setMonth(months[mi - 1])} disabled={mi <= 0} aria-label={T.cal.prevMonth}><IconLeft /></button>
        <b>{MONTHS[m - 1]} {y}</b>
        <button className="icon-btn ghost" onClick={() => setMonth(months[mi + 1])} disabled={mi < 0 || mi >= months.length - 1} aria-label={T.cal.nextMonth}><IconRight /></button>
      </header>
      <div className="cal-grid" role="grid" aria-label={`${MONTHS[m - 1]} ${y}`}>
        {T.cal.week.map((w, k) => <span key={k} className="cal-wd">{w}</span>)}
        {cells.map((d, k) => {
          if (!d) return <span key={`b${k}`} />;
          const n = Number(d.slice(8));
          if (!have.has(d)) {
            const off = excluded.has(d);
            return (
              <span key={d} className={`cal-day off${off ? " excluded" : ""}`} title={off ? T.cal.excluded : T.cal.noData}>
                <b>{n}</b>
              </span>
            );
          }
          return (
            <button key={d} className={`cal-day${d === day ? " on" : ""}${d === last ? " last" : ""}`} onClick={() => pick(d)}
              aria-pressed={d === day} title={`${dayLong(d)} · ${T.cal.motors(num(made.get(d), 0))}${d === last ? ` · ${T.cal.last}` : ""}`}>
              <b>{n}</b>
              <small>{num(made.get(d), 0)}</small>
            </button>
          );
        })}
      </div>
      <p className="cal-foot">{T.cal.foot}</p>
    </Popover>
  );
}
