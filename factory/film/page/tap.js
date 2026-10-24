// Film recorder instrumentation. Loaded with context.add_init_script(path=...) before the
// product page runs; the page itself (factory/web/static/index.html) is not modified.
//
// What it does:
//  - keeps the page's AudioContext as __film.ctx (the page forces 24 kHz);
//  - answers getUserMedia({audio}) with a MediaStream built inside that same context, so a
//    scripted "caller" can speak into the page's microphone path without a real device;
//  - copies everything the page connects to ctx.destination into a tap stream (the take audio);
//  - logs scheduled playback intervals, WebSocket JSON types, DOM status/banner changes.
// Events go to window.__filmEvent(json) (a Playwright binding) and to __film.log.
(() => {
  if (window.__film) return;

  const origConnect = AudioNode.prototype.connect;
  const film = {
    ctx: null,
    micDest: null,
    tapDest: null,
    agentDest: null,
    callers: new Map(),
    log: [],
    queue: [],
    lastBinaryT: 0,
    recorder: null,
    chunks: [],
    agentRecorder: null,
    agentChunks: [],
    takeStart: 0,
  };
  window.__film = film;

  function emit(kind, fields, tOverride) {
    const ev = Object.assign({ kind, t: tOverride === undefined ? performance.now() : tOverride }, fields || {});
    film.log.push(ev);
    const json = JSON.stringify(ev);
    if (typeof window.__filmEvent === "function") {
      while (film.queue.length) window.__filmEvent(film.queue.shift());
      window.__filmEvent(json);
    } else {
      film.queue.push(json);
    }
    return ev;
  }
  film.emit = emit;
  film.blocked = (label) => emit("blocked", { label: String(label) });

  // Context time -> performance.now() ms.
  function ctxToPerf(ctxTime) {
    const ts = film.ctx.getOutputTimestamp();
    if (!ts.performanceTime) {
      return performance.now() + (ctxTime - film.ctx.currentTime) * 1000;
    }
    return ts.performanceTime + (ctxTime - ts.contextTime) * 1000;
  }
  function perfToCtx(perfMs) {
    const ts = film.ctx.getOutputTimestamp();
    if (!ts.performanceTime) {
      return film.ctx.currentTime + (perfMs - performance.now()) / 1000;
    }
    return ts.contextTime + (perfMs - ts.performanceTime) / 1000;
  }

  // --- AudioContext: keep the page's context, build the mic and tap destinations in it ---
  const NativeAudioContext = window.AudioContext;
  function adopt(ctx) {
    if (film.ctx) return;
    film.ctx = ctx;
    film.micDest = ctx.createMediaStreamDestination();
    film.tapDest = ctx.createMediaStreamDestination(); // page output + caller + sync beep
    film.agentDest = ctx.createMediaStreamDestination(); // page output only (spike S-6)
    emit("ctx", { sampleRate: ctx.sampleRate, state: ctx.state });
  }
  class FilmAudioContext extends NativeAudioContext {
    constructor(...args) {
      super(...args);
      adopt(this);
    }
  }
  window.AudioContext = FilmAudioContext;

  // --- microphone: the page gets the caller stream ---
  const md = navigator.mediaDevices;
  if (md) {
    const origGum = md.getUserMedia.bind(md);
    md.getUserMedia = async (constraints) => {
      if (constraints && constraints.audio) {
        if (!film.ctx) adopt(new FilmAudioContext({ sampleRate: 24000 }));
        emit("gum", { sampleRate: film.ctx.sampleRate });
        return film.micDest.stream;
      }
      return origGum(constraints);
    };
  }

  // --- tap: whatever the page connects to its destination is also sent to the tap stream ---
  AudioNode.prototype.connect = function (target, ...rest) {
    const result = origConnect.call(this, target, ...rest);
    if (film.ctx && film.tapDest && this.context === film.ctx && target === film.ctx.destination) {
      origConnect.call(this, film.tapDest);
      origConnect.call(this, film.agentDest);
    }
    return result;
  };

  // --- scheduled playback intervals ---
  const proto = AudioBufferSourceNode.prototype;
  const origStart = proto.start;
  const origStop = proto.stop;
  proto.start = function (when, offset, duration) {
    const r = origStart.apply(this, arguments);
    if (film.ctx && this.context === film.ctx && !this.__film_quiet && this.buffer) {
      const startCtx = when === undefined || when < this.context.currentTime ? this.context.currentTime : when;
      const len = duration !== undefined ? duration : this.buffer.duration - (offset || 0);
      this.__film_span = { startCtx, endCtx: startCtx + len };
      emit("chunk", {
        t_received: film.lastBinaryT,
        start: ctxToPerf(startCtx),
        end: ctxToPerf(startCtx + len),
      });
    }
    return r;
  };
  proto.stop = function (when) {
    const span = this.__film_span;
    const r = origStop.apply(this, arguments);
    if (span && film.ctx) {
      const at = when === undefined || when < film.ctx.currentTime ? film.ctx.currentTime : when;
      emit("stop", {
        start: ctxToPerf(span.startCtx),
        end: ctxToPerf(span.endCtx),
        stop_at: ctxToPerf(at),
      });
    }
    return r;
  };

  // --- WebSocket: log JSON message types and binary arrival times ---
  const NativeWebSocket = window.WebSocket;
  const KINDS = new Set(["ready", "speech_started", "clear", "ttfa", "transcript", "ended"]);
  class FilmWebSocket extends NativeWebSocket {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (ev) => {
        const t = performance.now();
        if (typeof ev.data !== "string") {
          film.lastBinaryT = t;
          return;
        }
        let m;
        try { m = JSON.parse(ev.data); } catch (_) { return; }
        if (!m || !KINDS.has(m.type)) return;
        const fields = {};
        if (m.type === "ttfa") { fields.ms = m.ms; fields.label = m.label; }
        if (m.type === "transcript") { fields.text = m.text; }
        if (m.type === "ended") { fields.reason = m.reason; fields.message = m.message; }
        if (m.type === "ready") { fields.released = m.released; fields.verdict = m.verdict; }
        emit(m.type, fields, t);
      });
    }
  }
  window.WebSocket = FilmWebSocket;

  // --- DOM: #liveStatus text and #notReleased visibility ---
  function watchDom() {
    const status = document.getElementById("liveStatus");
    const banner = document.getElementById("notReleased");
    if (status) {
      emit("status", { text: status.textContent });
      new MutationObserver(() => emit("status", { text: status.textContent }))
        .observe(status, { childList: true, characterData: true, subtree: true });
    }
    if (banner) {
      emit("banner", { hidden: banner.hidden });
      new MutationObserver(() => emit("banner", { hidden: banner.hidden }))
        .observe(banner, { attributes: true, attributeFilter: ["hidden"] });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchDom, { once: true });
  } else {
    watchDom();
  }

  // --- caller audio ---
  function decodePcm16(b64) {
    const bin = atob(b64);
    const n = bin.length >> 1;
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
      if (v & 0x8000) v -= 0x10000;
      out[i] = v / 0x8000;
    }
    return out;
  }

  // Load 24 kHz mono 16-bit little-endian PCM (base64) under an id; resolves to its length in s.
  film.loadCaller = async (id, b64pcm) => {
    const data = decodePcm16(b64pcm);
    const buf = film.ctx.createBuffer(1, data.length, 24000);
    buf.getChannelData(0).set(data);
    film.callers.set(id, buf);
    return buf.duration;
  };

  // Speak a loaded caller line into the page's microphone (and into the tap, so the take
  // recording holds both sides). atPerfMs: performance.now() time to start, or null for now.
  film.playCaller = (id, atPerfMs) => {
    const buf = film.callers.get(id);
    if (!buf) throw new Error("caller not loaded: " + id);
    const src = film.ctx.createBufferSource();
    src.__film_quiet = true;
    src.buffer = buf;
    origConnect.call(src, film.micDest);
    origConnect.call(src, film.tapDest);
    const nowCtx = film.ctx.currentTime;
    const startCtx = atPerfMs === null || atPerfMs === undefined ? nowCtx : Math.max(nowCtx, perfToCtx(atPerfMs));
    origStart.call(src, startCtx);
    const t = ctxToPerf(startCtx);
    emit("caller", { id, duration: buf.duration, emitted: performance.now() }, t);
    return { t, duration: buf.duration };
  };

  // --- sync mark: 100 ms black overlay in the picture, 1 kHz 50 ms beep in the tap only ---
  film.syncMark = () => {
    const beepCtx = film.ctx.currentTime + 0.02;
    const osc = film.ctx.createOscillator();
    osc.frequency.value = 1000;
    const gain = film.ctx.createGain();
    gain.gain.value = 0.5;
    origConnect.call(osc, gain);
    origConnect.call(gain, film.tapDest);
    osc.start(beepCtx);
    osc.stop(beepCtx + 0.05);
    const veil = document.createElement("div");
    veil.style.cssText = "position:fixed;inset:0;background:#000;z-index:2147483647;";
    document.documentElement.appendChild(veil);
    const t = performance.now();
    setTimeout(() => veil.remove(), 100);
    emit("sync", { beep_at: ctxToPerf(beepCtx) }, t);
    return t;
  };

  function startRecorder(stream, sink) {
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    rec.ondataavailable = (e) => { if (e.data && e.data.size) sink.push(e.data); };
    rec.start(100);
    return rec;
  }

  function stopRecorder(rec, sink) {
    return new Promise((resolve, reject) => {
      rec.onstop = () => {
        const reader = new FileReader();
        reader.onloadend = () => {
          const url = String(reader.result);
          resolve(url.slice(url.indexOf(",") + 1));
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(new Blob(sink, { type: rec.mimeType || "audio/webm" }));
      };
      rec.stop();
    });
  }

  film.beginTake = () => {
    film.chunks = [];
    film.agentChunks = [];
    film.recorder = startRecorder(film.tapDest.stream, film.chunks);
    film.agentRecorder = startRecorder(film.agentDest.stream, film.agentChunks);
    film.takeStart = performance.now();
    emit("take", { phase: "begin" }, film.takeStart);
    return film.syncMark();
  };

  film.endTake = async () => {
    if (!film.recorder) throw new Error("no take in progress");
    const rec = film.recorder;
    film.recorder = null;
    const done = stopRecorder(rec, film.chunks);
    emit("take", { phase: "end", began: film.takeStart });
    return done;
  };

  // Page output only, for the same take (spike S-6: agent audio without the caller).
  film.endAgentTake = async () => {
    if (!film.agentRecorder) throw new Error("no take in progress");
    const rec = film.agentRecorder;
    film.agentRecorder = null;
    return stopRecorder(rec, film.agentChunks);
  };
})();
