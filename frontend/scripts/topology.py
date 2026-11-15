"""Hipotesis de topologia de la linea, deducida de los datos.

El config solo trae `Orden_OP`. Aqui se deduce que no va en serie a partir de dos
senales que si estan en los datos, sin usar nombres de estacion:

- Recuento diario de piezas (NPR): dos estaciones por las que pasan las mismas
  piezas cuentan casi lo mismo cada dia. Se mide con la diferencia cuadratica
  media entre sus series diarias («salto», en piezas/dia).
- Horas inducidas (DES/SAT): en serie y sin pulmon, el bloqueo se propaga hacia
  atras y la falta de piezas hacia delante. Si no se propaga, no estan acopladas.

Reglas (cada una deja su evidencia y una confianza; todo se puede forzar en
`line_hints.json`, seccion `topology`):

 R1 fuera de flujo   las que marca la configuracion de linea (Rol 1). Se asocian a la
                     estacion con el mismo recuento diario, si lo hay.
 R2 paralelo         grupos que detecta el pipeline (cada una hace una fraccion y juntas
                     el total). Lo que el config mete entre ellas va despues de la union.
 R3 lateral          una estacion que no se bloquea ni se queda sin piezas cuando sus dos
                     vecinas de orden si: no esta entre ellas, entra de lado en la siguiente.
 R4 fuera de sitio   una estacion cuyo recuento no cuadra con sus vecinas y si con una zona
                     lejana. No se mueve: se anota como duda para la planta.
 R5 subconjuntos     bloques del final del config cuyo recuento encaja con una zona lejana
                     aguas arriba: entran alli.
 R6 pulmon           dos consecutivas desacopladas: una se bloquea o se queda sin piezas y la
                     otra no, o una se para mucho y la de al lado no lo nota. Hay acumulacion
                     entre ellas.

Es una hipotesis: la planta tiene la ultima palabra.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def es1(x: float) -> str:
    """Un decimal con coma, como se escribe en castellano: 11.6 -> '11,6'."""
    return f"{x:.1f}".replace(".", ",")


FAR = 6            # puestos de distancia a partir de los cuales una coincidencia es «lejana»
MAX_BLOCK = 12     # tamano maximo de un subconjunto
INDUCED_H = 2.0    # h/dia a partir de las cuales una perdida inducida es relevante
OWN_H = 1.5        # h/dia de parada propia a partir de las cuales deberia notarse en la vecina
ABSORBED = 0.6     # si la vecina nota menos de esta fraccion de la parada, algo la absorbe
DECOUPLED = 0.25   # fraccion por debajo de la cual se considera que no se propaga
BAD = ["contador_roto", "contador_doble", "sin_datos", "fuera_servicio", "sensor_sospechoso"]


def _conf(best: float, ratio: float) -> str:
    if best <= 6 and ratio <= 0.35:
        return "alta"
    return "media" if ratio <= 0.45 else "baja"


def infer(prod: pd.DataFrame, hints: dict | None = None) -> dict:
    """Devuelve {hypothesis, links, assists, notes}. `prod` son las filas limpias de dias productivos."""
    hints = hints or {}
    off_rules = set(hints.get("disable", []))
    first = prod.drop_duplicates("Operacion").set_index("Operacion")
    order = first["Orden_OP"].sort_values()
    flow = [op for op in order.index if first.at[op, "grupo"] == "linea"]
    off = [op for op in order.index if first.at[op, "grupo"] != "linea"]

    npr = prod.pivot(index="fecha", columns="Operacion", values="NPR").astype(float)
    des = prod.groupby("Operacion")["des_h"].mean()
    tap = prod.groupby("Operacion")["tap_h"].mean()
    sat = prod.groupby("Operacion")["sat_h"].mean()
    bad = prod.groupby("Operacion")[BAD].mean().max(axis=1)
    par = first["paralelo"]
    in_group = {op: par[op] for op in order.index if isinstance(par[op], str)}
    ok = {op: bool(bad[op] < 0.5) and op not in in_group for op in order.index}

    def gap(a: str, b: str) -> float:
        """Salto de recuento entre dos estaciones, en piezas/dia (sin el peor dia: un mal conteo no decide)."""
        d2 = np.sort(((npr[a] - npr[b]) ** 2).to_numpy())
        return float(np.sqrt(d2[: len(d2) - max(1, len(d2) // 16)].mean()))

    links: list[dict] = []
    notes: list[dict] = []

    def link(a, b, kind="serie", **kw):
        links.append({"from": a, "to": b, "kind": kind, **kw})

    def note(title, detail, ops, confidence):
        notes.append({"title": title, "detail": detail, "ops": ops, "confidence": confidence})

    # R2 · paralelo: el grupo ocupa un hueco de la cadena; lo que quede entre sus miembros va detras.
    chain: list[str | tuple[str, ...]] = []
    groups: dict[str, tuple[str, ...]] = {}
    for op in flow:
        g = in_group.get(op)
        if g and g not in groups:
            groups[g] = tuple(m for m in flow if in_group.get(m) == g)
            chain.append(groups[g])
        elif not g:
            chain.append(op)
    for members in groups.values():
        pos = [flow.index(m) for m in members]
        between = [x for x in flow[min(pos): max(pos) + 1] if x not in members]
        share = ", ".join(f"{m} {100 * npr[m].median() / prod['npr_linea'].median():.0f} %" for m in members)
        detail = f"Cada una hace una parte de las piezas de la línea ({share}) y juntas hacen el total."
        if between:
            detail += f" {', '.join(between)} aparece entre ellas en el config: se coloca después de la unión."
        note(f"{' y '.join(members)} trabajan en paralelo", detail, [*members, *between], "alta")

    singles = lambda: [x for x in chain if isinstance(x, str)]  # noqa: E731

    # R3 · lateral
    laterals: dict[str, str] = dict(hints.get("laterals", {}))
    lateral_conf: dict[str, str] = {x: "config" for x in laterals}
    if "lateral" not in off_rules:
        s = singles()
        for a, x, b in zip(s, s[1:], s[2:]):
            if x in laterals:
                continue
            for name, h in (("se bloquea", sat), ("se queda sin piezas", des)):
                around = min(h[a], h[b])
                if around >= INDUCED_H and h[x] < DECOUPLED * around:
                    laterals[x] = b
                    detail = (f"{a} y {b} pasan {es1(h[a])} y {es1(h[b])} h/día en «{name}», pero {x} solo "
                              f"{es1(h[x])} h: no puede estar entre las dos.")
                    if ok[x] and ok[a] and ok[b]:
                        detail += (f" Además su recuento salta {gap(a, x):.0f} piezas/día respecto a {a}, "
                                   f"frente a {gap(a, b):.0f} entre {a} y {b}.")
                    else:
                        detail += f" Su contador de piezas no es fiable, así que no hay recuento que lo confirme."
                    lateral_conf[x] = "media" if ok[x] else "baja"
                    note(f"{x} entra de lado en {b}", detail, [x, b], lateral_conf[x])
                    break
    for x in laterals:
        if x in chain:
            chain.remove(x)

    # R4 · fuera de sitio: se anota, no se mueve (el orden del config manda mientras no haya mas evidencia).
    if "fuera_de_sitio" not in off_rules:
        s = [x for x in singles() if ok[x]]
        for i in range(1, len(s) - 1):
            x = s[i]
            near = min(gap(s[i - 1], x), gap(x, s[i + 1]))
            far = [y for j, y in enumerate(s) if abs(j - i) > FAR]
            target = min(far, key=lambda y: gap(x, y))
            if near >= 30 and gap(x, target) <= 0.2 * near:
                note(
                    f"{x}: su recuento no cuadra con sus vecinas",
                    f"Cuenta como {target} (salto de {gap(x, target):.0f} piezas/día) y no como {s[i - 1]} "
                    f"({gap(s[i - 1], x):.0f}) ni {s[i + 1]} ({gap(x, s[i + 1]):.0f}). Se deja en el orden del config "
                    f"hasta que la planta diga dónde está.",
                    [x, target], "baja",
                )

    # R5 · subconjuntos: bloques del final cuyo recuento encaja lejos, aguas arriba.
    branches: list[dict] = [dict(b) for b in hints.get("branches", [])]
    forced = {op for b in branches for op in b["ops"]}
    chain = [x for x in chain if not (isinstance(x, str) and x in forced)]
    if "subconjunto" not in off_rules:
        while True:
            s = singles()
            rel = [x for x in s if ok[x]]
            found = None
            for head in reversed(rel):
                hi = s.index(head)
                if len(s) - hi > MAX_BLOCK or rel.index(head) == 0:
                    break
                before = rel[max(0, rel.index(head) - 3): rel.index(head)]
                pred = min(before, key=lambda y: gap(head, y))
                block = s[hi:]
                tail = [x for x in block if ok[x]][-1]
                far = [y for y in rel if s.index(y) < hi - FAR]
                if not far:
                    break
                target = min(far, key=lambda y: gap(tail, y))
                best, near = gap(tail, target), gap(head, pred)
                if near >= 20 and best <= 0.5 * near:
                    found = {"ops": block, "joins": target, "confidence": _conf(best, best / near),
                             "ev_tail": f"El recuento de {tail} sigue al de {target} (salto de {best:.0f} piezas/día)",
                             "ev_head": f"el de {head} no sigue al de {pred}, la anterior en el config ({near:.0f})"}
                    break
            if not found:
                break
            branches.insert(0, found)
            chain = [x for x in chain if x not in found["ops"]]
    # Dos bloques seguidos que entran en el mismo punto son uno solo (los parte un contador ruidoso).
    main_pos = {x: i for i, x in enumerate(singles())}
    merged: list[dict] = []
    for b in branches:
        prev = merged[-1] if merged else None
        if prev and abs(main_pos.get(prev["joins"], -99) - main_pos.get(b["joins"], 99)) <= 2:
            rank = ["baja", "media", "alta", "config"]
            best = max(prev, b, key=lambda x: rank.index(x.get("confidence", "config")))
            merged[-1] = {**best, "ops": [*prev["ops"], *b["ops"]], "ev_head": prev.get("ev_head")}
        else:
            merged.append(b)
    branches = merged
    for i, b in enumerate(branches):
        b["id"] = chr(65 + i)
        note(
            f"{b['ops'][0]}{' … ' + b['ops'][-1] if len(b['ops']) > 1 else ''} es un subconjunto que entra en {b['joins']}",
            f"{b['ev_tail']} y {b['ev_head']}." if b.get("ev_tail") else "Fijado en la configuración de la línea.",
            [*b["ops"], b["joins"]], b.get("confidence", "config"),
        )

    # R6 · pulmon entre dos consecutivas desacopladas.
    buffers = {tuple(x) for x in hints.get("buffers", [])}
    if "pulmon" not in off_rules:
        s = singles()
        for a, b in zip(s, s[1:]):
            blocked = sat[b] >= INDUCED_H and sat[a] < DECOUPLED * sat[b]
            starved = des[a] >= INDUCED_H and des[b] < DECOUPLED * des[a]
            jump = ok[a] and ok[b] and gap(a, b) >= 20
            # Una que se para mucho y cuya vecina no lo nota: sus paradas se quedan en un pulmon.
            absorbs_up = ok[b] and tap[b] >= OWN_H and sat[a] < ABSORBED * tap[b]
            absorbs_down = ok[a] and tap[a] >= OWN_H and des[b] < ABSORBED * tap[a]
            if (blocked and starved) or ((blocked or starved) and jump) or absorbs_up or absorbs_down:
                buffers.add((a, b))
                why = []
                if blocked:
                    why.append(f"{b} pasa {es1(sat[b])} h/día bloqueada y {a} solo {es1(sat[a])}")
                if starved:
                    why.append(f"{a} pasa {es1(des[a])} h/día sin piezas y {b} solo {es1(des[b])}")
                if absorbs_up:
                    why.append(f"{b} se para {es1(tap[b])} h/día y {a} solo pasa {es1(sat[a])} h bloqueada")
                if absorbs_down:
                    why.append(f"{a} se para {es1(tap[a])} h/día y {b} solo pasa {es1(des[b])} h sin piezas")
                note(f"Hay un pulmón entre {a} y {b}",
                     "Las paradas no pasan de una a otra: " + "; ".join(why) + ".", [a, b],
                     "alta" if blocked and starved else "media")

    # Enlaces del flujo principal.
    def ends(x):
        return list(x) if isinstance(x, tuple) else [x]

    for a, b in zip(chain, chain[1:]):
        for u in ends(a):
            for v in ends(b):
                kind = "paralelo" if isinstance(a, tuple) or isinstance(b, tuple) else "serie"
                extra = {"buffer": True} if (u, v) in buffers else {}
                link(u, v, kind, **extra)
    for x, target in laterals.items():
        link(x, target, "lateral", confidence=lateral_conf.get(x, "media"))
    for b in branches:
        for u, v in zip(b["ops"], b["ops"][1:]):
            link(u, v, "serie", branch=b["id"])
        link(b["ops"][-1], b["joins"], "subconjunto", branch=b["id"], confidence=b.get("confidence", "config"))

    # R1 · fuera de flujo: a que estacion asisten, si el recuento lo dice.
    assists = []
    forced_assist = hints.get("assists", {})
    rel = [x for x in flow if ok[x]]
    for op in off:
        if op in forced_assist:
            assists.append({"op": op, "to": forced_assist[op], "confidence": "config"})
            continue
        entry = {"op": op, "to": None}
        if bad[op] < 0.5 and npr[op].median() > 0:
            ranked = sorted(rel, key=lambda y: gap(op, y))
            best, second = gap(op, ranked[0]), gap(op, ranked[1])
            if best <= 6 and best <= 0.6 * second:
                entry = {"op": op, "to": ranked[0], "confidence": "media",
                         "evidence": f"Mismo recuento diario que {ranked[0]} (salto de {best:.0f} piezas/día)."}
        assists.append(entry)
    placed = [a for a in assists if a["to"]]
    if off:
        detail = "No cuentan en el flujo de piezas (configuración de la línea)."
        if placed:
            detail += " Por recuento: " + "; ".join(f"{a['op']} acompaña a {a['to']}" for a in placed) + "."
        if len(placed) < len(off):
            detail += " El resto no tiene un contador que permita situarlas."
        note(f"{len(off)} manipuladores fuera del flujo", detail, off, "media")

    return {
        "hypothesis": True,
        "links": links,
        "assists": assists,
        "notes": notes,
        "branch_of": {**{op: b["id"] for b in branches for op in b["ops"]}, **{x: "L" for x in laterals}},
    }
