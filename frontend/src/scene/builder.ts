import * as THREE from "three";

/**
 * Constructor de geometría: va acumulando cajas, cilindros y esferas con su color en un único
 * búfer por material. Toda la planta fija sale en muy pocas llamadas de dibujo y sin un solo
 * modelo ni textura externos.
 */
export const PAINT = 0;
export const METAL = 1;
export const GLASS = 2;

interface Proto {
  pos: Float32Array;
  nor: Float32Array;
  idx: ArrayLike<number>;
}

function proto(g: THREE.BufferGeometry): Proto {
  const p = { pos: g.attributes.position.array as Float32Array, nor: g.attributes.normal.array as Float32Array, idx: g.index!.array };
  return p;
}

const BOX = proto(new THREE.BoxGeometry(1, 1, 1));
const SPHERE = proto(new THREE.SphereGeometry(1, 12, 8));
const CYL = new Map<number, Proto>();
const cylProto = (seg: number) => {
  if (!CYL.has(seg)) CYL.set(seg, proto(new THREE.CylinderGeometry(1, 1, 1, seg)));
  return CYL.get(seg)!;
};

class Buffer {
  pos: number[] = [];
  nor: number[] = [];
  col: number[] = [];
  idx: number[] = [];
}

const color = new THREE.Color();
const m = new THREE.Matrix4();
const r = new THREE.Matrix4();
const v = new THREE.Vector3();
const q = new THREE.Quaternion();
const e = new THREE.Euler();
const s = new THREE.Vector3();
const t = new THREE.Vector3();

export class Builder {
  private bufs = [new Buffer(), new Buffer(), new Buffer()];
  private frame = new THREE.Matrix4();

  /** Sitúa lo que se añada después: origen en (x, y, z) y girado `rot` en Y. */
  at(x: number, z: number, rot = 0, y = 0): this {
    this.frame.makeRotationY(rot).setPosition(x, y, z);
    return this;
  }

  private add(p: Proto, mat: number, hex: number, tx: number, ty: number, tz: number, sx: number, sy: number, sz: number, rx = 0, ry = 0, rz = 0): void {
    const b = this.bufs[mat];
    e.set(rx, ry, rz);
    q.setFromEuler(e);
    m.compose(t.set(tx, ty, tz), q, s.set(sx, sy, sz)).premultiply(this.frame);
    r.makeRotationFromQuaternion(q).premultiply(new THREE.Matrix4().extractRotation(this.frame));
    color.setHex(hex);
    const base = b.pos.length / 3;
    for (let i = 0; i < p.pos.length; i += 3) {
      v.set(p.pos[i], p.pos[i + 1], p.pos[i + 2]).applyMatrix4(m);
      b.pos.push(v.x, v.y, v.z);
      v.set(p.nor[i], p.nor[i + 1], p.nor[i + 2]).applyMatrix4(r);
      b.nor.push(v.x, v.y, v.z);
      b.col.push(color.r, color.g, color.b);
    }
    for (let i = 0; i < p.idx.length; i++) b.idx.push(base + p.idx[i]);
  }

  /** Caja centrada en (x, y, z). */
  box(x: number, y: number, z: number, w: number, h: number, d: number, hex: number, mat = PAINT, ry = 0): this {
    this.add(BOX, mat, hex, x, y, z, w, h, d, 0, ry, 0);
    return this;
  }

  /** Cilindro centrado en (x, y, z), de radio `rad` y largo `len` a lo largo de `axis`. */
  cyl(x: number, y: number, z: number, rad: number, len: number, hex: number, mat = PAINT, axis: "x" | "y" | "z" = "y", seg = 10): this {
    this.add(cylProto(seg), mat, hex, x, y, z, rad, len, rad, axis === "z" ? Math.PI / 2 : 0, 0, axis === "x" ? Math.PI / 2 : 0);
    return this;
  }

  ball(x: number, y: number, z: number, rad: number, hex: number, mat = PAINT): this {
    this.add(SPHERE, mat, hex, x, y, z, rad, rad, rad);
    return this;
  }

  /** Una geometría por material (null si ese material no se usó). */
  build(): (THREE.BufferGeometry | null)[] {
    return this.bufs.map((b) => {
      if (!b.pos.length) return null;
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(b.pos, 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(b.nor, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(b.col, 3));
      g.setIndex(b.idx);
      g.computeBoundingSphere();
      return g;
    });
  }

  /** Todo en una sola geometría (para piezas que se instancian). */
  single(): THREE.BufferGeometry {
    const all = new Buffer();
    for (const b of this.bufs) {
      const base = all.pos.length / 3;
      all.pos.push(...b.pos);
      all.nor.push(...b.nor);
      all.col.push(...b.col);
      for (const i of b.idx) all.idx.push(base + i);
    }
    this.bufs = [all, new Buffer(), new Buffer()];
    return this.build()[0] ?? new THREE.BufferGeometry();
  }
}
