/* Testes do motor de prova de vida da versão web (cofre-academico.html).
   Executar:  node --test tests/
   O motor é extraído do bloco <script id="liveness-engine"> do HTML. */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "..", "cofre-academico.html"), "utf8");
const code = html.match(/<script id="liveness-engine">([\s\S]*?)<\/script>/)[1];
const sandbox = { globalThis: {} };
sandbox.globalThis = sandbox;
vm.runInNewContext(code, sandbox);
const LE = sandbox.LivenessEngine;

/* gerador pseudoaleatório determinístico */
function rng(seed) { return () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }; }

const FRONT = { faces: 1, yaw: 0.5, blink: 0.05, mouth: 0.03, center: { x: 0.5, y: 0.5 }, size: 0.35 };
const pose = (patch) => Object.assign({}, FRONT, patch);
const ACTION = {
  blink: pose({ blink: 0.85 }),
  left: pose({ yaw: 0.75 }),
  right: pose({ yaw: 0.25 }),
  mouth: pose({ mouth: 0.7 }),
};

function run(state, frames, t0, dt = 80) {
  let s = state, t = t0;
  for (const f of frames) { t += dt; s = LE.step(s, f, t); }
  return { s, t };
}

function liveSession(seq) {
  const frames = [FRONT, FRONT, FRONT];
  for (const ch of seq) frames.push(ACTION[ch], ACTION[ch], FRONT, FRONT);
  return frames;
}

test("pessoa real que segue o desafio é aprovada", () => {
  const s0 = LE.initialState(0, rng(1));
  const { s } = run(s0, liveSession(s0.seq), 0);
  assert.strictEqual(s.status, "aprovado");
});

test("sequência sempre contém piscar + 2 desafios distintos", () => {
  for (let i = 1; i < 50; i++) {
    const seq = LE.newSequence(rng(i));
    assert.strictEqual(seq.length, 3);
    assert.ok(seq.includes("blink"));
    assert.strictEqual(new Set(seq).size, 3);
  }
});

test("foto parada na frente da câmera NUNCA é aprovada", () => {
  const s0 = LE.initialState(0, rng(2));
  const frames = Array.from({ length: 300 }, () => FRONT);  /* 24 s */
  let s = s0, t = 0, approved = false;
  for (const f of frames) { t += 80; s = LE.step(s, f, t); if (s.status === "aprovado") approved = true; }
  assert.strictEqual(approved, false);
});

test("foto balançada/inclinada (celular na mão) NUNCA é aprovada", () => {
  /* Mover/inclinar um plano 2D desloca o rosto e muda a escala, mas o nariz
     continua no meio dos olhos (giro ~0.5), os olhos não fecham e a boca não abre. */
  const r = rng(3);
  let s = LE.initialState(0, r), t = 0, approved = false;
  for (let i = 0; i < 400; i++) {
    t += 80;
    const f = pose({
      yaw: 0.5 + (r() - 0.5) * 0.08,
      blink: 0.05 + r() * 0.1,
      mouth: 0.02 + r() * 0.08,
      center: { x: 0.5 + Math.sin(i / 5) * 0.08, y: 0.5 + Math.cos(i / 7) * 0.05 },
      size: 0.3 + Math.sin(i / 9) * 0.06,
    });
    s = LE.step(s, f, t);
    if (s.status === "aprovado") approved = true;
  }
  assert.strictEqual(approved, false);
});

test("girar para o lado errado reprova", () => {
  const s0 = LE.initialState(0, rng(4));
  const seq = s0.seq;
  const idxTurn = seq.findIndex(c => c === "left" || c === "right");
  if (idxTurn < 0) return;
  const frames = [FRONT, FRONT];
  for (let i = 0; i < idxTurn; i++) frames.push(ACTION[seq[i]], FRONT);
  frames.push(seq[idxTurn] === "left" ? ACTION.right : ACTION.left);
  const { s } = run(s0, frames, 0);
  assert.strictEqual(s.status, "reprovado");
  assert.strictEqual(s.reason, "desafio_incorreto");
});

test("tempo esgotado reprova e gera desafio novo depois", () => {
  const s0 = LE.initialState(0, rng(5));
  let { s, t } = run(s0, Array.from({ length: 120 }, () => FRONT), 0);
  assert.ok(s.status === "reprovado" || s.reason === "tempo_esgotado");
  ({ s } = run(s, Array.from({ length: 40 }, () => FRONT), t));
  assert.notStrictEqual(s.id, s0.id);
});

test("rosto sai do quadro após aprovação → precisa refazer", () => {
  const s0 = LE.initialState(0, rng(6));
  let { s, t } = run(s0, liveSession(s0.seq), 0);
  assert.strictEqual(s.status, "aprovado");
  ({ s, t } = run(s, Array.from({ length: 15 }, () => ({ faces: 0 })), t));
  ({ s } = run(s, [FRONT], t));
  assert.notStrictEqual(s.status, "aprovado");
  assert.notStrictEqual(s.id, s0.id);
});

test("troca brusca de rosto (colocar foto no lugar) → recomeça", () => {
  const s0 = LE.initialState(0, rng(7));
  let { s, t } = run(s0, liveSession(s0.seq), 0);
  assert.strictEqual(s.status, "aprovado");
  ({ s } = run(s, [pose({ center: { x: 0.85, y: 0.5 } })], t));
  assert.notStrictEqual(s.status, "aprovado");
  assert.strictEqual(s.reason, "rosto_trocado");
});

test("dois rostos no quadro → recomeça", () => {
  const s0 = LE.initialState(0, rng(8));
  let { s, t } = run(s0, liveSession(s0.seq), 0);
  ({ s } = run(s, [{ faces: 2 }], t));
  assert.notStrictEqual(s.status, "aprovado");
  assert.strictEqual(s.reason, "multiplos_rostos");
});

test("aprovação expira após SESSION_TTL_MS", () => {
  const s0 = LE.initialState(0, rng(9));
  let { s, t } = run(s0, liveSession(s0.seq), 0);
  const n = Math.ceil(LE.CONFIG.SESSION_TTL_MS / 80) + 5;
  ({ s } = run(s, Array.from({ length: n }, () => FRONT), t));
  assert.notStrictEqual(s.status, "aprovado");
});

test("metricsFromResult: giro do nariz em relação aos olhos", () => {
  const lm = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
  lm[33] = { x: 0.4, y: 0.45 }; lm[263] = { x: 0.6, y: 0.45 }; lm[1] = { x: 0.55, y: 0.55 };
  lm[10] = { x: 0.5, y: 0.2 }; lm[152] = { x: 0.5, y: 0.8 }; lm[234] = { x: 0.35, y: 0.5 }; lm[454] = { x: 0.65, y: 0.5 };
  const m = LE.metricsFromResult({
    faceLandmarks: [lm],
    faceBlendshapes: [{ categories: [
      { categoryName: "eyeBlinkLeft", score: 0.9 }, { categoryName: "eyeBlinkRight", score: 0.7 },
      { categoryName: "jawOpen", score: 0.3 } ] }],
  });
  assert.strictEqual(m.faces, 1);
  assert.ok(Math.abs(m.yaw - 0.75) < 1e-9);
  assert.ok(Math.abs(m.blink - 0.8) < 1e-9);
  assert.strictEqual(m.mouth, 0.3);
  assert.strictEqual(LE.metricsFromResult({ faceLandmarks: [lm, lm] }).faces, 2);
});

test("giro imune a girar a foto no plano (roll)", () => {
  for (const deg of [-40, -20, 0, 20, 40]) {
    const a = deg * Math.PI / 180;
    const lm = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 }));
    const rot = ([x, y]) => ({ x: 0.5 + x * Math.cos(a) - y * Math.sin(a), y: 0.5 + x * Math.sin(a) + y * Math.cos(a), z: 0 });
    lm[33] = rot([-0.1, 0]); lm[263] = rot([0.1, 0]); lm[1] = rot([0, 0.08]);
    const m = LE.metricsFromResult({ faceLandmarks: [lm], faceBlendshapes: [{ categories: [] }] });
    assert.ok(Math.abs(m.yaw - 0.5) < 1e-9, `roll ${deg}°: ${m.yaw}`);
  }
});
