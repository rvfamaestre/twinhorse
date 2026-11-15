import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { BUFFER_CAP, type Layout, PALLET_PITCH, SPEED, WAIT, pointAt } from "../domain/layout";
import { DAY_STATE, STATES } from "../domain/status";
import { rowOf } from "../sim/day";
import type { DayRun } from "../sim/day";
import {
  S_BLOCKED, S_GAP, S_NODATA, S_OFF, S_OWN, S_STARVED, S_WORK, type SimState,
  newEdgeSample, newStationSample, sampleEdge, sampleStation, upper,
} from "../sim/engine";
import { advanceClock, clock } from "../state/clock";
import type { LineModel } from "../state/line";
import { useUI } from "../state/ui";
import {
  BELT_Y, ENGINE_STAGES, GAUGE_H, GAUGE_Y0, GAUGE_Z, PART_VARIANT, type Plant, TOOL_KINDS, TOOL_OPERATOR, TOOL_PRESS, TOOL_ROBOT,
  TOOL_SPINDLE, palletGeometry, stageOf, toolGeometry,
} from "./models";
import { ENV, type Theme } from "./palette";

/**
 * Todo lo que se mueve: palés con su motor, cabezales, robots, operarios, balizas y el halo de
 * estado en el suelo. En cada fotograma se pregunta a la simulación cómo está la línea en el
 * instante del reloj y se colocan las piezas; no hay estado propio, así que saltar en el tiempo es gratis.
 */
const PALLET_MAX = 640;
const VARIANTS = ENGINE_STAGES + 1;

const M = new THREE.Matrix4();
const Q = new THREE.Quaternion();
const E = new THREE.Euler(0, 0, 0, "YXZ");
const P = new THREE.Vector3();
const ONE = new THREE.Vector3(1, 1, 1);
const SCALE = new THREE.Vector3();
const COLOR = new THREE.Color();
const stateColor = (Object.keys(STATES) as unknown as SimState[]).map((s) => new THREE.Color(STATES[s].hex));
const LAMP_DIM = new THREE.Color(0x4a1518);
const GAUGE_COLOR = new THREE.Color(0x3d6877);

/**
 * Posición en la cinta que se dibuja a partir de la de la simulación. Casi todas las cintas miden
 * lo mismo en las dos plantas; la curva de la línea serpenteada es más larga: la cola sigue igual
 * de apretada al final y el resto del recorrido se estira (allí los palés van más deprisa).
 */
const QUEUE_ZONE = 1.5 * PALLET_PITCH;
function warp(s: number, simHead: number, head: number): number {
  if (Math.abs(head - simHead) < 1e-3) return s;
  const q = Math.min(QUEUE_ZONE, simHead);
  if (s >= simHead - q || simHead - q <= 1e-6) return s + (head - simHead);
  return (s * (head - q)) / (simHead - q);
}

const smooth = (a: number, b: number, x: number) => {
  const u = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return u * u * (3 - 2 * u);
};

function glowTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d")!;
  const grad = ctx.createRadialGradient(64, 64, 6, 64, 64, 64);
  grad.addColorStop(0, "rgba(255,255,255,0.95)");
  grad.addColorStop(0.55, "rgba(255,255,255,0.6)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export function Dynamic({ model, lay, theme, plant, run }: { model: LineModel; lay: Layout; theme: Theme; plant: Plant; run: DayRun }) {
  const { g } = model;
  const simLay = model.lay; // la simulación se hizo con la planta recta
  const pallets = useRef<(THREE.InstancedMesh | null)[]>([]);
  const tools = useRef<(THREE.InstancedMesh | null)[]>([]);
  const lamps = useRef<THREE.InstancedMesh>(null);
  const halos = useRef<THREE.InstancedMesh>(null);
  const gauges = useRef<THREE.InstancedMesh>(null);
  const ring = useRef<THREE.Mesh>(null);

  const res = useMemo(() => {
    const paint = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.08 });
    return {
      paint,
      pallets: Array.from({ length: VARIANTS }, (_, v) => palletGeometry(v)),
      tools: Array.from({ length: TOOL_KINDS }, (_, k) => toolGeometry(k)),
      lamp: new THREE.CylinderGeometry(0.085, 0.085, 0.26, 12),
      lampMat: new THREE.MeshBasicMaterial({ toneMapped: false }),
      halo: new THREE.PlaneGeometry(5.6, 5.6).rotateX(-Math.PI / 2),
      haloMat: new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, opacity: 0.8, depthWrite: false, toneMapped: false }),
      gauge: new THREE.BoxGeometry(1, 1, 1),
      gaugeMat: new THREE.MeshBasicMaterial({ toneMapped: false }),
      ring: new THREE.RingGeometry(1.95, 2.12, 56).rotateX(-Math.PI / 2),
      ringMat: new THREE.MeshBasicMaterial({ color: 0x1c1f23, transparent: true, opacity: 0.85, depthWrite: false }),
    };
  }, []);
  useEffect(() => () => {
    for (const x of Object.values(res).flat()) (x as { dispose?: () => void }).dispose?.();
  }, [res]);
  useEffect(() => {
    res.ringMat.color.setHex(ENV[theme].ring);
  }, [res, theme]);

  // Hueco de cada estación dentro de la malla de su tipo de pieza móvil.
  const slots = useMemo(() => {
    const count = new Array(TOOL_KINDS).fill(0);
    return { slot: plant.rigs.map((r) => count[r.tool]++), count };
  }, [plant]);
  const towerOf = useMemo(() => new Map(lay.towers.map((t, k) => [t.edge, k])), [lay]);
  // Los manipuladores no entran en la simulación: su baliza solo dice si su dato del día vale.
  const auxColor = useMemo(
    () => g.aux.map((a) => {
      const st = rowOf(a, run.day)?.status;
      return stateColor[st === "fuera_servicio" || st === "dato_no_fiable" ? DAY_STATE[st] : S_GAP];
    }),
    [g, run.day],
  );

  const st = useMemo(newStationSample, []);
  const es = useMemo(() => newEdgeSample(72), []);
  const pt = useMemo(() => ({ x: 0, z: 0, rot: 0 }), []);
  const cnt = useMemo(() => new Int32Array(VARIANTS), []);

  useFrame((frame, dt) => {
    advanceClock(dt);
    const t = clock.t;
    const sim = run.sim;
    const time = frame.clock.elapsedTime;
    const ui = useUI.getState();
    cnt.fill(0);

    const put = (variant: number, x: number, z: number, rot: number) => {
      const mesh = pallets.current[variant];
      if (!mesh || cnt[variant] >= PALLET_MAX) return;
      M.makeRotationY(rot).setPosition(x, BELT_Y + 0.004, z);
      mesh.setMatrixAt(cnt[variant]++, M);
    };

    // Palés sobre las cintas (los que esperan dentro de un pulmón no se ven: cuentan para su nivel).
    for (const e of g.edges) {
      const simPath = simLay.paths[e.i];
      const path = lay.paths[e.i];
      sampleEdge(sim, e.i, t, SPEED, PALLET_PITCH, simPath.head, es, simPath.slots, simPath.hold);
      const variant = g.nodes[e.from].role === "main" ? stageOf(g.nodes[e.from].rank) : PART_VARIANT;
      let inside = 0;
      for (let c = 0; c < es.count; c++) {
        const s = es.pos[c];
        if (simPath.hidden && s > simPath.hidden[0] && s < simPath.hidden[1]) {
          inside++;
          continue;
        }
        pointAt(path, warp(s, simPath.head, path.head), pt);
        put(variant, pt.x, pt.z, pt.rot);
      }
      const tw = towerOf.get(e.i);
      if (tw != null && gauges.current) {
        const h = Math.max(0.02, GAUGE_H * Math.min(1, inside / BUFFER_CAP));
        const tower = lay.towers[tw];
        M.compose(P.set(tower.x, GAUGE_Y0 + h / 2, tower.z + GAUGE_Z), Q.identity(), SCALE.set(0.24, h, 0.02));
        gauges.current.setMatrixAt(tw, M);
        gauges.current.setColorAt(tw, GAUGE_COLOR);
      }
    }

    // Estaciones: el palé que tienen dentro, su pieza móvil, la baliza y el halo.
    for (const n of g.nodes) {
      const i = n.i;
      const rig = plant.rigs[i];
      const pose = lay.poses[i];
      sampleStation(sim, i, t, st);
      const state = st.state;
      const variant = n.role === "main" ? stageOf(n.rank) : PART_VARIANT;
      if (st.has) {
        const d = Math.min(0, st.entered * SPEED - WAIT);
        put(variant, pose.x + Math.cos(pose.rot) * d, pose.z - Math.sin(pose.rot) * d, pose.rot);
      }

      // Lo que entra por un extremo de la línea espera en cola fuera de la primera estación.
      const stub = lay.inStub[i];
      if (stub) {
        const last = st.piece >= 0 ? sim.start[i][st.piece] : -1e9;
        const slide = Math.min(1, Math.max(0, 1 - ((t - last) * SPEED) / PALLET_PITCH));
        for (let q = 0; q < 3; q++) {
          const s = stub.head - (q + slide) * PALLET_PITCH;
          if (s < 0.1) break;
          pointAt(stub, s, pt);
          put(variant, pt.x, pt.z, pt.rot);
        }
      }
      // Y lo que sale por el final se aleja por la cinta.
      const out = lay.outStub[i];
      if (out) {
        for (let l = upper(sim.dep[i], sim.n[i], t) - 1; l >= 0; l--) {
          const s = (t - sim.dep[i][l]) * SPEED;
          if (s > out.len) break;
          pointAt(out, s, pt);
          put(variant, pt.x, pt.z, pt.rot);
        }
      }

      const busy = st.has && (state === S_WORK || state === S_OWN || state === S_NODATA);
      const p = st.progress;
      const mesh = tools.current[rig.tool];
      if (mesh) {
        let y = rig.pivot.y;
        let yaw = rig.rot;
        let lean = 0;
        if (rig.tool === TOOL_PRESS) {
          if (busy) y -= 0.38 * (smooth(0, 0.18, p) - smooth(0.82, 1, p));
        } else if (rig.tool === TOOL_SPINDLE) {
          if (busy) y -= 0.3 * Math.abs(Math.sin(p * Math.PI * 3));
        } else if (rig.tool === TOOL_ROBOT) {
          yaw += busy ? 0.55 * Math.sin(p * Math.PI * 4) : 0.95;
        } else if (rig.tool === TOOL_OPERATOR) {
          if (busy) {
            lean = -0.2 - 0.06 * Math.sin(p * Math.PI * 10);
            yaw += 0.12 * Math.sin(p * Math.PI * 5);
          }
        }
        M.compose(P.set(rig.pivot.x, y, rig.pivot.z), Q.setFromEuler(E.set(lean, yaw, 0)), ONE);
        mesh.setMatrixAt(slots.slot[i], M);
      }

      if (lamps.current) {
        const blink = state === S_OWN && Math.sin(time * 9) < -0.2;
        M.makeTranslation(rig.lamp.x, rig.lamp.y, rig.lamp.z);
        lamps.current.setMatrixAt(i, M);
        lamps.current.setColorAt(i, blink ? LAMP_DIM : stateColor[state]);
      }
      if (halos.current) {
        // Regla de la escena: lo normal no lleva color. Con un estado de la leyenda pulsado, solo se ve ese.
        let s = 0;
        if (ui.legend != null) s = state === ui.legend ? 1.15 : 0;
        else if (state === S_OWN) s = 1 + 0.07 * Math.sin(time * 5);
        else if (state === S_STARVED || state === S_BLOCKED) s = 0.9;
        else if (state === S_NODATA || state === S_OFF) s = 0.62;
        M.compose(P.set(rig.center.x, 0.04, rig.center.z), Q.identity(), SCALE.set(s, 1, s));
        halos.current.setMatrixAt(i, M);
        halos.current.setColorAt(i, COLOR.copy(stateColor[state]));
      }
    }

    if (lamps.current) {
      plant.auxRigs.forEach((rig, k) => {
        M.makeTranslation(rig.lamp.x, rig.lamp.y, rig.lamp.z);
        lamps.current!.setMatrixAt(g.nodes.length + k, M);
        lamps.current!.setColorAt(g.nodes.length + k, auxColor[k]);
      });
    }

    pallets.current.forEach((mesh, v) => {
      if (!mesh) return;
      mesh.count = cnt[v];
      mesh.instanceMatrix.needsUpdate = true;
    });
    for (const mesh of [...tools.current, lamps.current, halos.current, gauges.current]) {
      if (!mesh) continue;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    }

    // Anillo de la estación elegida.
    if (ring.current) {
      const sel = ui.selected;
      const node = sel ? g.index.get(sel) : undefined;
      const aux = sel && node == null ? g.auxIndex.get(sel) : undefined;
      const c = node != null ? plant.rigs[node].center : aux != null ? plant.auxRigs[aux].center : null;
      ring.current.visible = !!c;
      if (c) {
        const k = (aux != null ? 0.5 : 1) * (1 + 0.025 * Math.sin(time * 3));
        ring.current.position.set(c.x, 0.05, c.z);
        ring.current.scale.set(k, 1, k);
      }
    }
  });

  return (
    <group>
      {res.pallets.map((geo, v) => (
        <instancedMesh key={v} ref={(m) => void (pallets.current[v] = m)} args={[geo, res.paint, PALLET_MAX]} frustumCulled={false} castShadow />
      ))}
      {res.tools.map((geo, k) =>
        slots.count[k] ? (
          <instancedMesh key={`${k}-${slots.count[k]}`} ref={(m) => void (tools.current[k] = m)} args={[geo, res.paint, slots.count[k]]} frustumCulled={false} castShadow />
        ) : null,
      )}
      <instancedMesh key={`l${g.nodes.length + g.aux.length}`} ref={lamps} args={[res.lamp, res.lampMat, g.nodes.length + g.aux.length]} frustumCulled={false} />
      <instancedMesh key={`h${g.nodes.length}`} ref={halos} args={[res.halo, res.haloMat, g.nodes.length]} frustumCulled={false} renderOrder={1} />
      {lay.towers.length ? (
        <instancedMesh key={`g${lay.towers.length}`} ref={gauges} args={[res.gauge, res.gaugeMat, lay.towers.length]} frustumCulled={false} />
      ) : null}
      <mesh ref={ring} geometry={res.ring} material={res.ringMat} visible={false} renderOrder={2} />
    </group>
  );
}
