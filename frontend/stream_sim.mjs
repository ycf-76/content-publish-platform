// 复刻 useChatSSE.ts 中 pushStreamDelta 的释放算法（cps=60）
// 目的：证明即使后端一次给 200 字大块（reader.read 同步批灌的最坏情况），
//       显示内容也逐帧增长，而非整段蹦出。
const CPS = 60;
let raw = '';
let shown = 0;
let raf = null;
let last = 0;
let displayed = '';
let peakPerFrame = 0;
let prevLen = 0;

function tick(now) {
  const dt = (now - last) / 1000;
  last = now;
  shown = Math.min(raw.length, shown + dt * CPS);
  displayed = raw.slice(0, Math.floor(shown));
  const gained = displayed.length - prevLen;
  if (gained > peakPerFrame) peakPerFrame = gained;
  prevLen = displayed.length;
  if (shown < raw.length) {
    raf = setTimeout(() => tick(performance.now()), 16);
  }
}
function push(delta, now) {
  raw += delta;
  if (raf == null) { last = now; raf = setTimeout(() => tick(performance.now()), 16); }
}

const t0 = performance.now();
// 最坏情况：一次 reader.read() 返回 200 字大块
push('字'.repeat(200), t0);

console.log('=== 模拟: 一次到达 200 字大块 (cps=60) ===');
console.log('首帧前若直接 content+= 会瞬间显示 200 字（旧行为=整段打印）');
const iv = setInterval(() => {
  const el = performance.now() - t0;
  console.log(`t=${String(Math.round(el)).padStart(4)}ms  已显示 ${String(displayed.length).padStart(3)}/${raw.length} 字`);
  if (el >= 3600 || shown >= raw.length) {
    clearInterval(iv);
    console.log('---');
    console.log(`峰值单帧增长: ${peakPerFrame} 字 (若=200 则等于旧"整段"；若≈1 则逐字流式)`);
    console.log(shown >= raw.length ? '结论: 大块被匀速拆成逐帧释放，整段打印已消除 ✅' : '结论: 仍在区间内');
    process.exit(0);
  }
}, 120);
