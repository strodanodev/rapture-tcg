// The sound engine: one AudioContext, a bed bus (music and ambience) and an effects bus under a master with a gentle
// limiter. Effects are decoded once and played as buffer sources. Music and ambience stream from <audio> elements,
// two decks each, and loop by crossfading one deck into the other, so no track sits decoded in memory and no loop
// seam clicks. The library and its manifest (audio/audio.json) are built by scripts/audio in the theforge monorepo.
//
// Browsers start audio only after a gesture: until the first tap or key press, music() and ambience() just remember
// what should play, and play() is dropped. A hidden tab pauses everything.
//
//   const sound = createSound({ base: "./audio/", prefs: { master: 0.8, music: 0.6, sfx: 0.9, muted: false } });
//   sound.play("strike"); sound.music("menu"); sound.ambience("amb-hall"); sound.duck();

const XFADE = 4;   // seconds a looping track overlaps itself

export function createSound({ base = "./audio/", prefs: initial = {} } = {}) {
  const prefs = { master: 0.8, music: 0.6, sfx: 0.9, muted: false, ...initial };
  let meta = {};
  const ready = fetch(`${base}audio.json`).then((r) => (r.ok ? r.json() : { sounds: {} })).then((m) => { meta = m.sounds ?? {}; return meta; }).catch(() => meta);

  let ctx = null, master = null, bed = null, unlocked = false;
  const bus = {};
  const buffers = new Map(), loading = new Map(), lastPlayed = new Map();

  function ensureContext() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { ctx = new AC({ latencyHint: "interactive" }); } catch { try { ctx = new AC(); } catch { return null; } }
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -8; limiter.knee.value = 8; limiter.ratio.value = 6; limiter.attack.value = 0.004; limiter.release.value = 0.3;
    master = ctx.createGain();
    master.connect(limiter).connect(ctx.destination);
    bed = ctx.createGain();   // music and ambience pass through here, so a stinger can duck them together
    bed.connect(master);
    for (const k of ["music", "amb", "sfx"]) { bus[k] = ctx.createGain(); bus[k].connect(k === "sfx" ? master : bed); }
    apply();
    return ctx;
  }

  function apply() {
    if (!ctx) return;
    const t = ctx.currentTime;
    master.gain.setTargetAtTime(prefs.muted ? 0 : prefs.master, t, 0.04);
    bus.music.gain.setTargetAtTime(prefs.music, t, 0.04);
    bus.amb.gain.setTargetAtTime(prefs.music, t, 0.04);   // ambience follows the music level: "effects only" is effects only
    bus.sfx.gain.setTargetAtTime(prefs.sfx, t, 0.04);
    const beds = !prefs.muted && prefs.music > 0;
    music.enable(beds); amb.enable(beds);
  }

  // ------------------------------------------------------------------ unlocking
  function unlock() {
    const c = ensureContext();
    if (!c) return;
    if (c.state !== "running" && !document.hidden) c.resume().catch(() => {});
    music.prime(); amb.prime();   // iOS lets a media element play only after a gesture has touched it
    if (unlocked) return;
    unlocked = true;
    void preload();
    music.kick(); amb.kick();
  }
  for (const ev of ["pointerdown", "keydown", "touchend"]) addEventListener(ev, unlock, { capture: true, passive: true });
  if (navigator.audioSession) try { navigator.audioSession.type = "ambient"; } catch { /* older Safari */ }   // mix with the player's own music

  document.addEventListener("visibilitychange", () => {
    if (!ctx || !unlocked) return;
    if (document.hidden) { music.hold(true); amb.hold(true); void ctx.suspend().catch(() => {}); }
    else { void ctx.resume().catch(() => {}); music.hold(false); amb.hold(false); }
  });

  // ------------------------------------------------------------------ effects
  async function load(name) {
    if (buffers.has(name)) return buffers.get(name);
    if (!loading.has(name)) {
      loading.set(name, (async () => {
        const m = (await ready)[name];
        if (!m || !ctx) return null;
        const bytes = await fetch(base + m.file).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.status))));
        const buf = await new Promise((ok, no) => ctx.decodeAudioData(bytes, ok, no));   // the callback form: older Safari
        buffers.set(name, buf);
        return buf;
      })().catch(() => { loading.delete(name); return null; }));
    }
    return loading.get(name);
  }
  async function preload() {
    const names = Object.entries(await ready).filter(([, m]) => m.kind === "sfx").map(([n]) => n);
    for (let i = 0; i < names.length; i += 3) await Promise.all(names.slice(i, i + 3).map(load));
  }

  /** Play an effect. opts: gain (× the manifest's), delay (s), rate (else a random spread from the manifest), pan. */
  function play(name, { gain = 1, delay = 0, rate, pan = 0 } = {}) {
    if (!ctx || !unlocked || prefs.muted || prefs.sfx <= 0 || document.hidden) return;
    const now = performance.now();
    if (now - (lastPlayed.get(name) ?? -1e9) < 35) return;   // the same sound twice in one frame is one sound
    lastPlayed.set(name, now);
    const buf = buffers.get(name);
    if (buf) { start(name, buf, gain, delay, rate, pan); return; }
    // not decoded yet: play it if it arrives while still timely
    void load(name).then((b) => { if (b && performance.now() - now < 250) start(name, b, gain, delay, rate, pan); });
  }
  function start(name, buf, gain, delay, rate, pan) {
    const m = meta[name] ?? {};
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = rate ?? 1 + (Math.random() * 2 - 1) * (m.vary ?? 0);
    const g = ctx.createGain();
    g.gain.value = (m.gain ?? 1) * gain;
    src.connect(g);
    if (pan && ctx.createStereoPanner) { const p = ctx.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan)); g.connect(p).connect(bus.sfx); }
    else g.connect(bus.sfx);
    src.start(ctx.currentTime + Math.max(0, delay));
  }
  /** Repeat an effect every `period` seconds until stopped (a heartbeat). Returns stop(). */
  function pulse(name, period, opts = {}) {
    play(name, opts);
    const id = setInterval(() => play(name, opts), period * 1000);
    return () => clearInterval(id);
  }

  // ------------------------------------------------------------------ streamed, looping beds
  function stream(kind) {
    const decks = [0, 1].map(() => {
      const el = new Audio();
      el.preload = "auto";
      el.loop = false;
      return { el, node: null, gain: null, live: false, primed: false };
    });
    let want = null, track = null, cur = -1, enabled = true, held = false;
    const wire = (d) => {
      if (!d.node && ctx) {
        d.node = ctx.createMediaElementSource(d.el);
        d.gain = ctx.createGain();
        d.gain.gain.value = 0;
        d.node.connect(d.gain).connect(bus[kind]);
      }
    };
    const ramp = (d, to, sec) => {
      if (!d.gain) return;
      const t = ctx.currentTime;
      d.gain.gain.cancelScheduledValues(t);
      d.gain.gain.setValueAtTime(d.gain.gain.value, t);
      d.gain.gain.linearRampToValueAtTime(to, t + Math.max(0.02, sec));
    };
    const stop = (d, sec) => {
      if (!d.live) return;
      d.live = false;
      ramp(d, 0, sec);
      const el = d.el;
      setTimeout(() => { if (!d.live) el.pause(); }, sec * 1000 + 50);
    };
    const begin = (name, sec) => {
      const m = meta[name];
      if (!m) return;
      const i = cur === 0 ? 1 : 0, d = decks[i];
      wire(d);
      if (!d.el.src.endsWith(`/${m.file}`)) d.el.src = base + m.file;
      try { d.el.currentTime = 0; } catch { /* not seekable yet: starts at 0 anyway */ }
      d.live = true;
      d.el.play().then(() => ramp(d, m.gain ?? 1, sec), () => { d.live = false; });
      if (cur >= 0) stop(decks[cur], sec);
      cur = i; track = name;
    };
    // the loop: start the other deck before this one runs out
    setInterval(() => {
      if (cur < 0 || !track || held) return;
      const d = decks[cur], el = d.el;
      if (d.live && el.duration && el.currentTime > el.duration - XFADE - 0.3) begin(track, XFADE);
    }, 250);
    for (const d of decks) d.el.addEventListener("ended", () => { if (d.live && decks[cur] === d && track) begin(track, 0.5); });
    const sync = (fade) => {
      if (!unlocked || !ctx) return;
      const target = enabled ? want : null;
      if (target === track) return;
      if (!target) { if (cur >= 0) stop(decks[cur], fade); track = null; return; }
      void ready.then(() => begin(target, fade));
    };
    return {
      /** Ask for a track (or null for silence); crossfades over `fade` seconds once audio is unlocked. */
      set(name, fade) { want = name; sync(fade); },
      kick() { sync(1.5); },
      enable(on) { if (enabled === on) return; enabled = on; sync(1); },
      /** Play each deck once, silently, inside the unlocking gesture. */
      prime() {
        const file = meta[want]?.file ?? Object.values(meta).find((m) => m.kind === kind)?.file;
        for (const d of decks) {
          if (d.primed || !file) continue;
          d.primed = true;
          wire(d);
          if (d.live || !d.el.paused) continue;
          if (!d.el.src) d.el.src = base + file;
          d.el.play().then(() => { if (!d.live) d.el.pause(); }, () => { d.primed = false; });
        }
      },
      hold(on) { held = on; for (const d of decks) if (d.live) { if (on) d.el.pause(); else void d.el.play().catch(() => {}); } },
    };
  }
  const music = stream("music"), amb = stream("amb");

  // ------------------------------------------------------------------ the interface
  /** Dip the music and ambience (a stinger is playing), then bring them back. */
  function duck(depth = 0.35, hold = 2.5, release = 2) {
    if (!ctx) return;
    const t = ctx.currentTime, g = bed.gain;
    g.cancelScheduledValues(t);
    g.setValueAtTime(g.value, t);
    g.linearRampToValueAtTime(depth, t + 0.25);
    g.setValueAtTime(depth, t + 0.25 + hold);
    g.linearRampToValueAtTime(1, t + 0.25 + hold + release);
  }

  /** Click and hover sounds for every button under `root`. data-sfx="none" silences one; data-sfx="<name>" picks one. */
  function bindUi(root = document) {
    let over = null;
    const target = (e) => e.target.closest?.("button, a[href], [role=button], [role=switch], .menu-item") ?? null;
    root.addEventListener("click", (e) => {
      const el = target(e);
      if (!el || el.disabled || el.getAttribute("aria-disabled") === "true") return;
      const tag = el.closest("[data-sfx]")?.dataset.sfx;
      if (tag === "none") return;
      play(tag || (el.matches(".back, .close, [aria-label=Back], [aria-label=Resume]") ? "ui-back" : "ui-click"));
    }, true);
    root.addEventListener("pointerover", (e) => {
      if (e.pointerType !== "mouse") return;
      const el = target(e);
      if (el === over) return;
      over = el;
      if (el && !el.disabled && el.closest("[data-sfx]")?.dataset.sfx !== "none") play("ui-hover");
    }, true);
  }

  return {
    ready,
    play, pulse, duck, bindUi,
    music: (name, fade = 2.5) => music.set(name, fade),
    ambience: (name, fade = 3) => amb.set(name, fade),
    get prefs() { return { ...prefs }; },
    /** Change levels (0..1) or mute; persists nothing itself. */
    set(next) { Object.assign(prefs, next); apply(); },
    get unlocked() { return unlocked; },
  };
}
