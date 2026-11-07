(() => {
  // Loading pearl: shown at once, then grows and glides into the stage pearl's place before the app fades in.
  const splash = document.createElement('div');
  splash.id = 'bz-splash'; splash.className = 'idle';
  const placeSplash = (x, y, d) => { splash.style.left = x + 'px'; splash.style.top = y + 'px'; splash.style.width = d + 'px'; splash.style.height = d + 'px'; };
  placeSplash(window.innerWidth / 2 - 60, window.innerHeight / 2 - 60, 120);
  document.documentElement.appendChild(splash);
  // Reveal only when everything is right: the stage is scaled (fitFrames), its first real state is applied, the
  // fonts are ready (max 3 s) and the pearl's place is measured. Until then the stage keeps visibility:hidden
  // (inline in stage.html, so it never depends on when Gradio injects this head).
  let landed = false, fontsOk = false;
  const stageReady = () => { const r = document.getElementById('bayan'); return !!(r && r.__applied && (r.style.transform || '').includes('scale')); };
  const reveal = () => { const r = document.getElementById('bayan'); if (r) r.style.visibility = 'visible'; document.documentElement.classList.add('bz-ready'); };
  const finish = () => { reveal(); splash.style.opacity = '0'; setTimeout(() => splash.remove(), 400); };
  const tryLand = () => { if (!landed && fontsOk && stageReady()) requestAnimationFrame(() => requestAnimationFrame(land)); };
  window.__bzTryLand = tryLand;
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => { fontsOk = true; tryLand(); });
  setTimeout(() => { fontsOk = true; tryLand(); }, 3000);
  function land() {
    if (landed || !stageReady()) return; landed = true;
    const t = document.getElementById('bz-pearl-wrap');
    const r = t && t.getBoundingClientRect();
    if (!r || r.width < 10) { finish(); return; }
    const cs = splash.getBoundingClientRect();  // freeze the current breathing size, then fly
    placeSplash(cs.left, cs.top, cs.width); splash.className = 'fly'; void splash.offsetWidth;
    placeSplash(r.left, r.top, r.width);
    setTimeout(finish, 980);
  }
  // Safety: never leave the page hidden, but never show an unscaled stage either.
  const rescue = (n) => { if (landed) return; if (stageReady() || n > 40) { landed = true; finish(); } else setTimeout(() => rescue(n + 1), 250); };
  setTimeout(() => rescue(0), 8000);
  if (window.__bayanUI) return; window.__bayanUI = true;
  const EASE = 'cubic-bezier(.2,.8,.2,1)';
  const MORE = __LANGS_MORE__;  // the "More…" sheet: {code: {en, ar, native, in_lang, again, slower, yes, no, ...}}
  const LANGS = {
    ne: {name:'Nepali', inLang:'नेपालीमा', again:'फेरि भन्नुहोस्', slower:'बिस्तारै', yes:'हो', no:'होइन'},
    hi: {name:'Hindi', inLang:'हिन्दी में', again:'फिर से कहिए', slower:'धीरे', yes:'हाँ', no:'नहीं'},
    ur: {name:'Urdu', inLang:'اردو میں', again:'دوبارہ کہیے', slower:'آہستہ', yes:'ہاں', no:'نہیں'},
    bn: {name:'Bengali', inLang:'বাংলায়', again:'আবার বলুন', slower:'ধীরে', yes:'হ্যাঁ', no:'না'},
    ml: {name:'Malayalam', inLang:'മലയാളത്തിൽ', again:'വീണ്ടും പറയൂ', slower:'പതുക്കെ', yes:'അതെ', no:'ഇല്ല'},
    tl: {name:'Filipino', inLang:'sa Filipino', again:'Ulitin', slower:'Mas mabagal', yes:'Oo', no:'Hindi'},
    ta: {name:'Tamil', inLang:'தமிழில்', again:'மீண்டும் சொல்லுங்கள்', slower:'மெதுவாக', yes:'ஆம்', no:'இல்லை'},
    sw: {name:'Swahili', inLang:'kwa Kiswahili', again:'Rudia', slower:'Polepole', yes:'Ndiyo', no:'Hapana'},
    ko: {name:'Korean', inLang:'한국어로', again:'다시 말해 주세요', slower:'천천히', yes:'예', no:'아니요'}
  };
  Object.keys(MORE).forEach((c) => { const m = MORE[c]; if (!LANGS[c]) LANGS[c] = {name: m.en, inLang: m.in_lang, again: m.again, slower: m.slower, yes: m.yes, no: m.no}; });
  const ICON = {
    allergy: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16.5h.01"></path></svg>',
    test: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12h4l2-5 4 10 2-5h6"></path></svg>',
    drug: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="8.5" width="18" height="7" rx="3.5" transform="rotate(-45 12 12)"></rect><path d="m8.5 8.5 7 7"></path></svg>',
    held: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C2410C" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6v12"></path><path d="M15 6v12"></path></svg>',
    override: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C2410C" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5z"></path><path d="M15.5 8.5a5 5 0 0 1 0 7"></path></svg>',
    bulb: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18h6"></path><path d="M10 21h4"></path><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"></path></svg>',
    speaker: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5z"></path><path d="M15.5 8.5a5 5 0 0 1 0 7"></path><path d="M18.5 5.5a9 9 0 0 1 0 13"></path></svg>',
    check: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="m5 12.5 4.5 4.5L19 7.5"></path></svg>',
    alert: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C2410C" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.5 2.5 20h19z"></path><path d="M12 10v4.5"></path><path d="M12 17.5h.01"></path></svg>'
  };
  ICON.observation = ICON.bulb; ICON.missed = ICON.bulb; ICON.rule = ICON.allergy;
  const $ = (id) => document.getElementById(id);
  // ---------------------------------------------------------------- doctor's language (English / Arabic, RTL)
  const STR = __STRINGS__;
  let UI = 'en';
  try { const v = localStorage.getItem('bayan.doclang'); if (v === 'ar' || v === 'en') UI = v; } catch (e) { /* storage blocked */ }
  const T = (k, kw) => { let s = (STR[UI] || STR.en)[k] || STR.en[k] || k; if (kw) Object.keys(kw).forEach((x) => { s = s.split('{' + x + '}').join(kw[x]); }); return s; };
  const LN = (code) => T('lang_' + code);
  let docSynced = false, confirmOpen = false, spk = 'doctor', turnSeq = -1;
  function setUI(lang, save) {
    if (lang !== 'ar' && lang !== 'en') return;
    UI = lang;
    if (save) { try { localStorage.setItem('bayan.doclang', lang); } catch (e) { /* storage blocked */ } }
    applyI18n(true);
    if (V) apply(V);
  }
  function applyI18n(force) {
    const root = $('bayan'); if (!root || (!force && root.__i18n === UI)) return;
    root.__i18n = UI;
    root.setAttribute('dir', UI === 'ar' ? 'rtl' : 'ltr'); root.setAttribute('lang', UI);
    root.querySelectorAll('[data-t]').forEach((el) => { el.textContent = T(el.dataset.t); });
    root.querySelectorAll('[data-ta]').forEach((el) => el.setAttribute('aria-label', T(el.dataset.ta)));
    root.querySelectorAll('[data-tp]').forEach((el) => el.setAttribute('placeholder', T(el.dataset.tp)));
    root.querySelectorAll('#bz-doclang .seg').forEach((b) => b.setAttribute('aria-checked', b.dataset.id === UI ? 'true' : 'false'));
    ['bz-doc-en', 'bz-pat-en', 'bz-cap-en', 'bz-consent-en', 'bz-held-h', 'bz-held-dq', 'bz-held-pq', 'bz-noted', 'bz-suglist', 'bz-warn']
      .forEach((id) => { const el = $(id); if (el) el.setAttribute('lang', UI); });
    notesKey = ''; sugKey = ''; stepsKey = ''; moreBuilt = ''; if (moreOpen) buildMore(); paintChips();
  }
  let V = null, lastS = '', appliedEl = null, selLang = 'ne', panelOpen = false, lastCid = '', openWhenFree = false;
  let tokNotice = 0, demoTried = false, tokOpen = 0, tokClose = 0, tokEnd = 0, tokStop = 0, capKey = '', planKey = '', notesKey = '', sugKey = '', stepsKey = '', patKey = '';
  let clockBase = null;

  const fit = (text, max, min, ideal) => { const n = (text || '').length; return n <= ideal ? max + 'px' : Math.max(min, Math.round(max * Math.sqrt(ideal / n))) + 'px'; };
  const css = (el, s) => { if (el && el.__css !== s) { el.style.cssText = s; el.__css = s; } };
  const txt = (el, t) => { if (el && el.textContent !== (t || '')) el.textContent = t || ''; };
  const lay = (on, pos, z, bg) => 'position:absolute;' + pos + ';z-index:' + (z || 3) + ';' + (bg ? 'background:' + bg + ';' : '') +
    'transition:opacity .55s ease ' + (on ? '.3s' : '0s') + ', transform .8s ' + EASE + ' ' + (on ? '.25s' : '0s') + ', right .55s ' + EASE + ', left .55s ' + EASE + ';' +
    'opacity:' + (on ? 1 : 0) + ';transform:' + (on ? 'none' : 'translateY(18px)') + ';pointer-events:' + (on ? 'auto' : 'none');
  const box = (cx, cy, s, z) => 'position:absolute;z-index:' + z + ';pointer-events:none;left:' + (cx - s / 2) + 'px;top:' + (cy - s / 2) + 'px;width:' + s + 'px;height:' + s + 'px;' +
    'transition:left .9s ' + EASE + ', top .9s ' + EASE + ', width .9s ' + EASE + ', height .9s ' + EASE;
  const setLang = (el, lang) => { if (el && el.getAttribute('lang') !== lang) el.setAttribute('lang', lang); };

  // ---------------------------------------------------------------- frame scaling (1280x800 design)
  let OX = 0, OY = 0, FW = 1280;
  function fitFrames() {
    // Fill the whole window: keep the design's scale (fit 1280x800), then stretch the frame so its
    // extra width/height is used by the layout (right-anchored panels stay on the right edge).
    const W = window.innerWidth, H = window.innerHeight, s = Math.min(W / 1280, H / 800);
    const fw = Math.ceil(W / s), fh = Math.ceil(H / s);
    // Content keeps the 1280x800 composition, centred; backgrounds and edge-docked panels use the full frame.
    const ox = Math.max(0, Math.round((fw - 1280) / 2)), oy = Math.max(0, Math.round((fh - 800) / 2));
    document.querySelectorAll('.bz-frame').forEach((f) => {
      const t = 'scale(' + s + ')';
      if (f.style.transform !== t) f.style.transform = t;
      if (f.style.width !== fw + 'px') f.style.width = fw + 'px';
      if (f.style.height !== fh + 'px') f.style.height = fh + 'px';
      f.style.setProperty('--ox', ox + 'px'); f.style.setProperty('--oy', oy + 'px');
    });
    if (ox !== OX || oy !== OY || fw !== FW) { OX = ox; OY = oy; FW = fw; if (typeof V !== 'undefined' && V) apply(V); }
  }
  window.addEventListener('resize', fitFrames);
  document.addEventListener('scroll', (e) => {
    const f = e.target && e.target.classList && e.target.classList.contains('bz-frame') ? e.target : null;
    if (f && (f.scrollLeft || f.scrollTop)) { f.scrollLeft = 0; f.scrollTop = 0; }
  }, true);

  // ---------------------------------------------------------------- tap to talk (browser recording)
  // One utterance per tap: record mono PCM, downsample to 16 kHz int16, send it as {act:"audio"}.
  let micStream = null, actx = null, rec = null, recBusy = false, localProc = 0, audioPlaying = false, lastPlayAt = 0;
  const MAX_REC = 60;
  async function getMic() {
    if (micStream && micStream.getAudioTracks().some((t) => t.readyState === 'live')) return micStream;
    micStream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1}});
    return micStream;
  }
  function releaseMic() {
    if (rec) cancelRec();
    if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
  }
  const stopMic = releaseMic;
  function canTalk() {
    return !!V && V.screen === 'live' && V.live !== 'held' && V.live !== 'confirm' && (V.settle || (V.live !== 'caption' && !V.speak)) && !V.processing && !localProc && !audioPlaying;
  }
  async function toggleRec() {
    if (rec) { stopRec(); return; }
    if (recBusy || !canTalk()) return;
    recBusy = true;
    try { await startRec(); }
    catch (e) { console.warn('bayan mic', e); toast(T('mic_denied')); }
    finally { recBusy = false; }
  }
  async function startRec() {
    const stream = await getMic();
    if (!actx || actx.state === 'closed') actx = new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === 'suspended') await actx.resume();
    const src = actx.createMediaStreamSource(stream);
    const an = actx.createAnalyser(); an.fftSize = 1024;
    const r = {src: src, an: an, sp: null, chunks: [], sr: actx.sampleRate, t0: performance.now(), buf: new Float32Array(an.fftSize), lvl: 0};
    src.connect(an);
    if (await workletReady()) {
      const node = new AudioWorkletNode(actx, 'bz-rec', {numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1});
      node.port.onmessage = (e) => { if (rec === r) r.chunks.push(e.data); };
      src.connect(node); node.connect(actx.destination);  // outputs silence; keeps the node running
      r.sp = node;
    } else {  // older browsers
      const sp = actx.createScriptProcessor(4096, 1, 1);
      sp.onaudioprocess = (e) => { if (rec === r) r.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0))); e.outputBuffer.getChannelData(0).fill(0); };
      src.connect(sp); sp.connect(actx.destination);
      r.sp = sp;
    }
    rec = r;
    r.timer = setInterval(recTick, 80);
    paintLive();
  }
  let workletP = null;
  function workletReady() {
    if (!actx.audioWorklet || typeof AudioWorkletNode === 'undefined') return Promise.resolve(false);
    if (!workletP) {
      const code = "class R extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(new Float32Array(c));return true}}registerProcessor('bz-rec',R);";
      const url = URL.createObjectURL(new Blob([code], {type: 'application/javascript'}));
      workletP = actx.audioWorklet.addModule(url).then(() => true, () => false);
    }
    return workletP;
  }
  function teardown(r) {
    clearInterval(r.timer);
    try { r.src.disconnect(); if (r.sp) { r.sp.disconnect(); if (r.sp.port) r.sp.port.onmessage = null; } r.an.disconnect(); } catch (e) { /* already gone */ }
  }
  function cancelRec() { const r = rec; rec = null; if (r) teardown(r); paintLive(); }
  function recTick() {
    const r = rec; if (!r) return;
    r.an.getFloatTimeDomainData(r.buf);
    let sum = 0; for (let i = 0; i < r.buf.length; i++) sum += r.buf[i] * r.buf[i];
    const rms = Math.sqrt(sum / r.buf.length);
    r.lvl = Math.max(rms, r.lvl * 0.75);  // fast attack, gentle release
    const k = Math.min(1, r.lvl * 9);
    const shape = [0.55, 0.8, 1, 0.8, 0.55];
    document.querySelectorAll('#bz-bars .bar').forEach((b, i) => {
      b.style.animation = 'none';
      b.style.transform = 'scaleY(' + (0.18 + 0.82 * k * shape[i] * (0.85 + 0.3 * Math.random())).toFixed(3) + ')';
    });
    const t = (performance.now() - r.t0) / 1000;
    txt($('bz-st-sub'), Math.floor(t / 60) + ':' + String(Math.floor(t % 60)).padStart(2, '0'));
    if (t >= MAX_REC) stopRec();
  }
  function downsample(x, from, to) {
    if (from === to) return x;
    const ratio = from / to, n = Math.floor(x.length / ratio), out = new Float32Array(n);
    for (let i = 0; i < n; i++) {  // box filter over each output sample's input window (cheap anti-aliasing)
      const a = Math.floor(i * ratio), b = Math.min(x.length, Math.floor((i + 1) * ratio));
      let s = 0; for (let j = a; j < b; j++) s += x[j];
      out[i] = s / Math.max(1, b - a);
    }
    return out;
  }
  function toB64(i16) {
    const u8 = new Uint8Array(i16.buffer); let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function stopRec() {
    const r = rec; if (!r) return;
    rec = null; teardown(r);
    let n = 0; r.chunks.forEach((c) => { n += c.length; });
    const all = new Float32Array(n); let o = 0, peak = 0;
    r.chunks.forEach((c) => { all.set(c, o); o += c.length; });
    for (let i = 0; i < n; i++) { const v = Math.abs(all[i]); if (v > peak) peak = v; }
    if (n / r.sr < 0.4 || peak < 0.015) { paintLive(); toast(T('not_caught')); return; }
    const f = downsample(all, r.sr, 16000), pcm = new Int16Array(f.length);
    for (let i = 0; i < f.length; i++) { const v = Math.max(-1, Math.min(1, f[i])); pcm[i] = v < 0 ? v * 32768 : v * 32767; }
    const audioId = Date.now();
    localProc = audioId;
    paintLive();
    send('audio', {sr: 16000, pcm: toB64(pcm), speaker: spk, n: audioId});
    setTimeout(() => { if (localProc) { localProc = 0; paintLive(); } }, 30000);  // never stay stuck
  }

  // Bayan's voice: PCM chunks appended to a hidden element (.bz-au); scheduled back to back with WebAudio.
  // Captions start at the exact moment the first chunk starts playing. Every item carries its consultation id
  // (data-c): only the consultation on screen speaks; a dropped one (Home, No, new consultation) never plays again,
  // even if its chunks were already on the wire.
  const played = new Map();  // utterance id -> last chunk played; a re-render can never replay a chunk
  const deadC = new Set();   // consultations dropped on this page
  const slowBuf = new Map(); // "Slower" replays: utterance id -> chunks, played once the last one is in
  let pctx = null, pKey = '', pIdx = -1, pEnd = 0, pStart = 0, pTimer = null, pSources = [], pMuted = '', pCid = '';
  let slowEl = null;         // one <audio> element, unlocked on the Slower tap (Safari plays it later without a gesture)
  const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
  function stopVoice(cid) {  // everything, or only one consultation's voice
    const hit = (x) => !cid || x.__c === cid;
    pSources.filter(hit).forEach((x) => { try { x.stop(); } catch (e) { /* already stopped */ } });
    pSources = pSources.filter((x) => !hit(x));
    if (!cid || pCid === cid) { slowBuf.clear(); pMuted = pKey; pEnd = 0; audioPlaying = false; clearTimeout(pTimer); }
  }
  function dropConsult(cid) { if (cid) deadC.add(cid); stopVoice(cid || undefined); }
  const curCid = () => { const el = document.querySelector('.bz-s[data-c]'); return el ? el.dataset.c : ''; };
  function playCtx() {
    if (!pctx) pctx = new (window.AudioContext || window.webkitAudioContext)();
    if (pctx.state === 'suspended') pctx.resume();
    return pctx;
  }
  function primeSlow() {
    try { if (!slowEl) slowEl = new Audio(); slowEl.src = SILENT_WAV; const q = slowEl.play(); if (q && q.catch) q.catch(() => {}); } catch (e) { /* no audio */ }
  }
  function startCaption() { document.querySelectorAll('#bz-cap-native .w').forEach((w) => { w.style.animationPlayState = 'running'; }); }
  function retimeCaption(dur) {  // real clip length is known: spread the words over it
    const ws = [...document.querySelectorAll('#bz-cap-native .w')]; if (!ws.length || !(dur > 0)) return;
    const total = ws.reduce((a, w) => a + w.textContent.length, 0), rate = total / Math.max(0.6, dur - 0.7);
    let chars = 0; ws.forEach((w) => { w.style.animationDelay = (0.35 + chars / rate).toFixed(2) + 's'; chars += w.textContent.length; });
  }
  function b64i16(p) {
    const bin = atob(p), n = bin.length >> 1, out = new Int16Array(n);
    for (let j = 0; j < n; j++) out[j] = bin.charCodeAt(2 * j) | (bin.charCodeAt(2 * j + 1) << 8);  // Int16Array wraps
    return out;
  }
  // Slower: the same clip with longer sentence gaps (gap sample positions from the server), played at `rate` with the
  // pitch preserved (an <audio> element; WebAudio's playbackRate would lower the voice).
  function stretchGaps(pcm, gaps, extra) {
    const at = gaps.filter((g) => g > 0 && g < pcm.length).sort((a, b) => a - b);
    const out = new Int16Array(pcm.length + at.length * extra);
    let src = 0, dst = 0;
    at.forEach((g) => { out.set(pcm.subarray(src, g), dst); dst += g - src + extra; src = g; });
    out.set(pcm.subarray(src), dst);
    return out;
  }
  function wavBlob(pcm, sr) {
    const b = new ArrayBuffer(44 + pcm.length * 2), v = new DataView(b);
    const w = (o, s) => { for (let k = 0; k < s.length; k++) v.setUint8(o + k, s.charCodeAt(k)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true);
    v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, pcm.length * 2, true);
    new Int16Array(b, 44).set(pcm);
    return new Blob([b], {type: 'audio/wav'});
  }
  function slowItem(key, it) {
    let b = slowBuf.get(key); if (!b) { b = {sr: 0, parts: []}; slowBuf.set(key, b); }
    if (!it.dataset.end) { if (!b.sr) b.sr = +it.dataset.sr; if (+it.dataset.sr === b.sr) b.parts.push(b64i16(it.dataset.p)); return; }
    slowBuf.delete(key);
    if (!b.parts.length || !b.sr) return;
    let n = 0; b.parts.forEach((x) => { n += x.length; });
    const pcm = new Int16Array(n); let o = 0; b.parts.forEach((x) => { pcm.set(x, o); o += x.length; });
    const rate = +it.dataset.rate || 1, gaps = (it.dataset.gaps || '').split(',').filter(Boolean).map(Number);
    const out = stretchGaps(pcm, gaps, Math.round((+it.dataset.gapx || 0) * rate * b.sr));
    const dur = out.length / b.sr / rate;
    const a = slowEl || new Audio(); slowEl = a;
    const url = URL.createObjectURL(wavBlob(out, b.sr));
    let live = true;
    const h = {stop() { live = false; try { a.pause(); } catch (e) { /* gone */ } URL.revokeObjectURL(url); }, el: a, rate: rate, dur: dur, __c: it.dataset.c};
    window.__bzSlowLast = h;  // for the static test harness
    const done = () => { if (!live) return; live = false; pSources = pSources.filter((x) => x !== h); URL.revokeObjectURL(url); audioPlaying = false; paintLive(); };
    a.onended = done; a.onerror = done;
    a.onplaying = () => { if (!live) return; lastPlayAt = performance.now(); startCaption(); paintLive(); };
    a.preservesPitch = true; a.mozPreservesPitch = true; a.webkitPreservesPitch = true;
    a.src = url;
    a.defaultPlaybackRate = rate; a.playbackRate = rate;  // after src: loading resets playbackRate to the default
    pSources.push(h); audioPlaying = true; pEnd = 0;
    retimeCaption(dur);
    const q = a.play(); if (q && q.catch) q.catch(done);
    clearTimeout(pTimer);
    pTimer = setTimeout(() => { audioPlaying = false; paintLive(); }, dur * 1000 + 1500);
  }
  function playVoice() {
    const items = document.querySelectorAll('#bayan-voice .bz-au'); if (!items.length) return;
    const key = items[0].dataset.k, cid = items[0].dataset.c || '';
    // Not this consultation's voice: a dropped one never plays; another one waits until the stage shows it.
    if (!cid || deadC.has(cid) || cid !== curCid()) return;
    if (key !== pKey) { if (pKey) played.set(pKey, pIdx); pKey = key; pIdx = played.has(key) ? played.get(key) : -1; }
    if (key === pMuted) return;  // stopped on purpose: never resume this utterance
    pCid = cid;
    const ctx = playCtx();
    items.forEach((it) => {
      const i = +it.dataset.i; if (it.dataset.k !== key || it.dataset.c !== cid || i <= pIdx) return;
      pIdx = i; played.set(key, i);
      if (it.dataset.rate) { slowItem(key, it); return; }
      if (it.dataset.end) { retimeCaption(+it.dataset.dur); return; }
      const pcm = b64i16(it.dataset.p), n = pcm.length, sr = +it.dataset.sr;
      const buf = ctx.createBuffer(1, n, sr), ch = buf.getChannelData(0);
      for (let j = 0; j < n; j++) ch[j] = pcm[j] / 32768;
      const src = ctx.createBufferSource(); src.buffer = buf; src.connect(ctx.destination); src.__c = cid; pSources.push(src);
      src.onended = () => { pSources = pSources.filter((x) => x !== src); };
      const first = i === 0, at = Math.max(ctx.currentTime + (first ? 0.15 : 0.02), pEnd);
      src.start(at); pEnd = at + buf.duration;
      if (first) {
        pStart = at; audioPlaying = true;
        setTimeout(() => { lastPlayAt = performance.now(); startCaption(); paintLive(); }, Math.max(0, (at - ctx.currentTime) * 1000));
      }
      clearTimeout(pTimer);
      pTimer = setTimeout(() => { audioPlaying = false; paintLive(); }, Math.max(0, (pEnd - ctx.currentTime) * 1000) + 120);
    });
  }
  new MutationObserver(playVoice).observe(document.documentElement, {childList: true, subtree: true});

  // ---------------------------------------------------------------- actions -> Python
  function send(act, extra) {
    window.__bzNext = JSON.stringify(Object.assign({act: act, n: Date.now()}, extra || {}));
    const b = $('bz-send'); if (b) b.click();
  }
  window.bayanSend = send;
  function setSpk(who) { if ((who === 'doctor' || who === 'patient') && !rec) { spk = who; if (V) apply(V); } }
  // Home: drop the visit (recording, playback, panels) and start fresh, keeping the doctor's language.
  function goHome() {
    cancelRec(); dropConsult(V && V.cid); releaseMic();
    panelOpen = false; confirmOpen = false; localProc = 0;
    window.__bayanAct = JSON.stringify({act: 'home', lang: UI, n: Date.now()});
  }
  function paintChips() {
    document.querySelectorAll('#bz-chips .chip[data-act=lang]').forEach((c) => c.classList.toggle('sel', c.dataset.id === selLang));
    const mc = $('bz-more-chip'), m = MORE[selLang];
    if (mc) {
      mc.classList.toggle('sel', !!m);
      const n = $('bz-more-n'), e = $('bz-more-e');
      if (m) { n.textContent = m.native; n.setAttribute('lang', selLang); e.textContent = UI === 'ar' ? LN(selLang) : m.en; }
      else { n.textContent = T('more'); n.removeAttribute('lang'); e.textContent = T('more_count', {n: Object.keys(MORE).length}); }
    }
    document.querySelectorAll('#bz-more-list .mlang').forEach((x) => { const on = x.dataset.id === selLang; x.classList.toggle('sel', on); x.setAttribute('aria-selected', on ? 'true' : 'false'); });
  }
  // "More…": a calm searchable list of extra patient languages (native name + name in the doctor's language).
  let moreOpen = false, moreBuilt = '';
  function buildMore() {
    if (moreBuilt === UI) return; moreBuilt = UI;
    const list = $('bz-more-list'); if (!list) return; list.textContent = '';
    Object.keys(MORE).forEach((code) => {
      const m = MORE[code], b = document.createElement('button');
      b.type = 'button'; b.className = 'mlang'; b.dataset.act = 'lang'; b.dataset.id = code; b.setAttribute('role', 'option');
      b.dataset.q = (m.native + ' ' + m.en + ' ' + m.ar + ' ' + code).toLowerCase();
      const n = document.createElement('span'); n.className = 'n'; n.setAttribute('lang', code); n.textContent = m.native;
      const e = document.createElement('span'); e.className = 'e'; e.textContent = LN(code);
      b.appendChild(n); b.appendChild(e); list.appendChild(b);
    });
    filterMore();
  }
  function filterMore() {
    const q = (($('bz-more-q') || {}).value || '').trim().toLowerCase();
    let shown = 0;
    document.querySelectorAll('#bz-more-list .mlang').forEach((x) => { const on = !q || x.dataset.q.includes(q); x.style.display = on ? 'flex' : 'none'; shown += on ? 1 : 0; });
    // No match: the message sits right under the search row and the (empty) list area is hidden.
    const none = $('bz-more-none'); if (none) none.hidden = !!shown;
    const list = $('bz-more-list'); if (list) list.hidden = !shown;
  }
  function setMore(open) {
    moreOpen = open; const mc = $('bz-more-chip'); if (mc) mc.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) { buildMore(); paintChips(); const q = $('bz-more-q'); if (q) { q.value = ''; filterMore(); setTimeout(() => q.focus({preventScroll: true}), 600); } }
    if (V) apply(V);
  }
  document.addEventListener('input', (e) => { if (e.target && e.target.id === 'bz-more-q') filterMore(); }, true);
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-act]');
    if (!b) { window.__bayanAct = ''; return; }
    const act = b.dataset.act;
    if (act !== '__send') { try { playCtx(); } catch (err) { /* no audio */ } }
    if (act === '__send') { window.__bayanAct = window.__bzNext || ''; window.__bzNext = ''; return; }
    const p = {act: act, id: b.dataset.id || '', n: Date.now()};
    if (act === 'lang') { selLang = b.dataset.id; paintChips(); if (moreOpen && b.classList.contains('mlang')) setMore(false); window.__bayanAct = ''; return; }
    if (act === 'more') { setMore(!moreOpen); window.__bayanAct = ''; return; }
    if (act === 'more-close') { setMore(false); const mc = $('bz-more-chip'); if (mc) mc.focus(); window.__bayanAct = ''; return; }
    if (act === 'notes') { panelOpen = !panelOpen; if (V) apply(V); window.__bayanAct = ''; return; }
    if (act === 'notes-close') { panelOpen = false; if (V) apply(V); window.__bayanAct = ''; return; }
    if (act === 'doclang') { if (V && V.screen !== 'start') { window.__bayanAct = ''; return; } setUI(b.dataset.id, true); }
    if (act === 'home') {
      if (V && ['consent', 'live', 'wrap', 'review'].includes(V.screen)) {
        confirmOpen = !confirmOpen; if (V) apply(V); window.__bayanAct = '';
        if (confirmOpen) setTimeout(() => { const y = $('bz-confirm-yes'); if (y) y.focus(); }, 60);
        return;
      }
      goHome(); return;
    }
    if (act === 'home_no') { confirmOpen = false; if (V) apply(V); window.__bayanAct = ''; const w = $('bz-wordmark'); if (w) w.focus(); return; }
    if (act === 'home_yes') { confirmOpen = false; goHome(); return; }
    if (act === 'spk') { setSpk(b.dataset.id); window.__bayanAct = ''; return; }
    if (act === 'talk') { window.__bayanAct = ''; b.blur(); toggleRec(); return; }
    if (act === 'start') { p.lang = selLang; p.doc = UI; getMic().catch(() => {}); }  // ask for the microphone early, during consent
    if (act === 'demo') { p.lang = 'ne'; }
    if (act === 'end' || act === 'consent_no' || act === 'new') stopMic();
    if (act === 'consent_no' || act === 'new') dropConsult(V && V.cid);  // the server drops this visit: so does its voice
    if (act === 'end') stopVoice();
    if (act === 'slower') primeSlow();
    if (act === 'approve') { if (V && V.screen !== 'review') { window.__bayanAct = ''; return; } p.text = ($('careplan') || {}).value || ''; p.force = !!(V.review && V.review.confirm); }
    if (act === 'ask') { panelOpen = false; if (V) apply(V); }
    if (act === 'unlock') { p.code = ($('bz-code') || {}).value || ''; }
    window.__bayanAct = JSON.stringify(p);
  }, true);
  // After Bayan speaks there is a calm 3 s pause (caption stays). Any tap or key ends it at once.
  let settleSent = 0;
  function endSettle() { if (V && V.settle && settleSent !== V.seq) { settleSent = V.seq; send('settle_skip'); } }
  document.addEventListener('pointerdown', (e) => {
    const b = e.target.closest && e.target.closest('[data-act]');
    if (b && (b.dataset.act === 'again' || b.dataset.act === 'slower')) return;  // those act on their own
    endSettle();
  }, true);
  document.addEventListener('keydown', () => endSettle(), true);
  // Space = tap the pearl (doctor convenience), except while typing.
  const typing = (t) => t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && confirmOpen) { confirmOpen = false; if (V) apply(V); return; }
    if (e.key === 'Escape' && moreOpen) { setMore(false); const mc = $('bz-more-chip'); if (mc) mc.focus(); return; }
    if (e.key === 'Enter' && e.target && e.target.id === 'bz-code') { e.preventDefault(); const b = document.querySelector('[data-act=unlock]'); if (b) b.click(); return; }
    if ((e.code === 'KeyD' || e.code === 'KeyP') && !typing(e.target) && !e.metaKey && !e.ctrlKey && !e.altKey && V && V.screen === 'live') {
      setSpk(e.code === 'KeyD' ? 'doctor' : 'patient'); return;
    }
    if ((e.code === 'Space' || e.key === ' ') && !typing(e.target) && V && V.screen === 'live') {
      e.preventDefault(); e.stopPropagation();
      if (!e.repeat) toggleRec();
    }
  }, true);
  document.addEventListener('keyup', (e) => {
    if ((e.code === 'Space' || e.key === ' ') && !typing(e.target) && V && V.screen === 'live') { e.preventDefault(); e.stopPropagation(); }
  }, true);

  // ---------------------------------------------------------------- render
  // Status under the pearl: the server's, unless the browser is recording or has just sent a recording.
  function paintLive() {
    if (!V) return;
    const proc = !!localProc && !rec;
    // A new turn is shown only once Bayan has said the last one (queued voice, speech and the settle pause are over).
    const turnIdle = V.screen === 'live' && ['idle', 'doctor', 'patient'].includes(V.live) && !V.processing && !V.queued && !V.speak && !proc;
    const spkCol = spk === 'doctor' ? '#1F6FB2' : '#0E8A6F';
    const st = rec ? [T('st_listening'), '0:00', spkCol] : proc ? [T('st_translating'), '', '#173430']
      : turnIdle ? [spk === 'doctor' ? T('turn_doc') : T('turn_pat'), T('st_tap'), spkCol] : (V.status || ['', '', '#173430']);
    const sw = $('bz-spk');
    if (sw) {
      sw.style.transition = 'opacity .3s'; sw.style.opacity = (turnIdle || rec) ? 1 : 0; sw.style.pointerEvents = turnIdle ? 'auto' : 'none';
      sw.querySelectorAll('.seg').forEach((x) => x.setAttribute('aria-checked', x.dataset.id === spk ? 'true' : 'false'));
    }
    txt($('bz-st-title'), st[0]); $('bz-st-title').style.color = st[2];
    if (!rec) txt($('bz-st-sub'), st[1]);
    css($('bz-bars'), 'display:flex;align-items:center;gap:6px;height:34px;margin-bottom:14px;transition:opacity .3s;opacity:' + (rec ? 1 : 0));
    document.querySelectorAll('#bz-bars .bar').forEach((b) => {
      b.style.background = st[2];
      if (!rec) { b.style.animation = ''; b.style.transform = ''; }
    });
    const pw = $('bz-pearl-wrap');
    if (pw) {
      const on = canTalk() || !!rec;
      pw.disabled = !on;
      pw.style.cursor = on ? 'pointer' : 'default';
      pw.style.pointerEvents = (V.screen === 'live' && V.live !== 'caption') ? 'auto' : 'none';
      pw.setAttribute('aria-label', rec ? T('tap_done_aria') : T('tap_aria'));
      pw.setAttribute('aria-pressed', rec ? 'true' : 'false');
    }
    const iri = $('s-iri'); if (iri) iri.style.animationDuration = (proc || V.processing) ? '2.5s' : rec ? '9s' : (V.speak ? '7s' : (V.screen === 'wrap' ? '2.5s' : '14s'));
  }
  function words(el, text, rate, key, waitAudio) {
    if (capKey === key) return; capKey = key;
    el.textContent = '';
    let chars = 0;
    const paused = waitAudio && performance.now() - lastPlayAt > 1500;
    if (paused) setTimeout(() => { if (capKey === key) startCaption(); }, 5000);  // never leave the caption unlit
    (text || '').split(/\s+/).filter(Boolean).forEach((w) => {
      const s = document.createElement('span'); s.className = 'w';
      if (paused) s.style.animationPlayState = 'paused';
      s.style.animationDelay = (0.35 + chars / (rate || 11)).toFixed(2) + 's';
      s.textContent = w + ' '; el.appendChild(s); chars += w.length + 1;
    });
  }
  function notesList(notes) {
    const k = JSON.stringify(notes); if (k === notesKey) return; notesKey = k;
    const box = $('bz-noted'); box.textContent = '';
    if (!notes.length) { const p = document.createElement('div'); p.style.cssText = 'font-size:15px;color:#5B6B69;line-height:1.5'; p.textContent = T('notes_empty'); box.appendChild(p); }
    notes.forEach((n) => {
      const d = document.createElement('div'); d.className = 'note-row';
      if (n.kind === 'held' || n.kind === 'override' || n.kind === 'alert') d.style.color = '#9A3412';
      d.innerHTML = ICON[n.kind] || ICON.test; const t = document.createElement('span'); t.textContent = n.text; d.appendChild(t); box.appendChild(d);
    });
  }
  function sugList(sugs, langName) {
    const k = JSON.stringify(sugs) + langName; if (k === sugKey) return; sugKey = k;
    const box = $('bz-suglist'); box.textContent = '';
    sugs.forEach((s, i) => {
      if (i) { const hr = document.createElement('div'); hr.style.cssText = 'height:1px;margin:0 22px;background:#EEF3F3'; box.appendChild(hr); }
      const w = document.createElement('div'); w.style.cssText = 'padding:20px 22px;display:flex;flex-direction:column;gap:12px';
      const h = document.createElement('span'); h.style.cssText = 'display:flex;align-items:center;gap:10px;font-size:14px;color:#0E8A6F;font-weight:500';
      h.innerHTML = '<span style="display:flex;align-items:center">' + ICON.bulb + '</span>'; h.appendChild(document.createTextNode(T('ask_next')));
      const p = document.createElement('p'); p.style.cssText = 'margin:0;font-size:17px;line-height:1.45;font-weight:500;color:#173430'; p.textContent = s.text;
      const b = document.createElement('button'); b.type = 'button'; b.dataset.act = 'ask'; b.dataset.id = s.id;
      b.style.cssText = 'align-self:flex-start;height:44px;padding:0 18px 0 14px;border-radius:999px;border:none;background:#0E8A6F;color:#FFFFFF;font-size:15px;font-weight:500;display:flex;align-items:center;gap:8px';
      b.innerHTML = ICON.speaker; b.appendChild(document.createTextNode(T('ask_btn', {lang: langName})));
      w.appendChild(h); w.appendChild(p); w.appendChild(b); box.appendChild(w);
    });
  }
  function stepsList(steps) {
    const k = JSON.stringify(steps); if (k === stepsKey) return; stepsKey = k;
    const box = $('bz-steps'); box.textContent = '';
    steps.forEach((s) => {
      const d = document.createElement('div'); d.className = 'step ' + s.state;
      d.innerHTML = s.state === 'done' ? ICON.check : s.state === 'doing' ? '<span class="spinner"></span>' : '<span class="dot"></span>';
      d.appendChild(document.createTextNode(s.k === 'safety' ? T('step_safety') : T('step_plan', {lang: LN(s.lang)}))); box.appendChild(d);
    });
  }
  function patientNative(el, native, idiom) {
    const k = native + '|' + idiom; if (k === patKey) return; patKey = k;
    el.textContent = '';
    const i = idiom ? native.indexOf(idiom) : -1;
    if (i < 0) { el.textContent = native; return; }
    el.appendChild(document.createTextNode(native.slice(0, i)));
    const u = document.createElement('span'); u.className = 'idiom'; u.textContent = idiom; el.appendChild(u);
    el.appendChild(document.createTextNode(native.slice(i + idiom.length)));
  }
  let toastT = null;
  function toast(msg) {
    const t = $('bz-toast'); if (!t) return;
    if (!msg) { t.style.opacity = 0; return; }
    txt(t, msg); t.style.opacity = 1; clearTimeout(toastT); toastT = setTimeout(() => { t.style.opacity = 0; }, 6000);
  }

  function apply(v) {
    const root = $('bayan'); if (!root) return; appliedEl = root;
    if (v.screen !== 'start' && v.docLang && v.docLang !== UI) { UI = v.docLang; }  // the visit keeps the language it started in
    if (v.screen === 'start' && v.docLang !== UI && !docSynced) { docSynced = true; send('doclang', {id: UI}); }
    applyI18n(false);
    const RTL = UI === 'ar';
    const M = (s) => RTL ? s.replace(/\b(left|right)\b/g, (m) => (m === 'left' ? 'right' : 'left')).replace('translateX(100%)', 'translateX(-100%)') : s;
    const mx = (cx) => (RTL ? FW - cx : cx);
    root.__applied = true;
    if (v.cid && v.cid !== lastCid) { if (lastCid) dropConsult(lastCid); lastCid = v.cid; playVoice(); }  // a new consultation: the old one's voice stops
    const scr = v.screen, live = scr === 'live';
    const cap = live && v.live === 'caption', rev = scr === 'review' || scr === 'sent';
    const think = scr === 'wrap', held = live && v.live === 'held', done = scr === 'sent';
    const L = LANGS[v.lang] || LANGS.ne, lang = v.lang || 'ne';
    const notesOn = live && !cap;
    if (!notesOn) panelOpen = false;
    if (v.openNotes !== tokOpen) { const fire = v.openNotes > tokOpen; tokOpen = v.openNotes; if (fire) openWhenFree = true; }
    if (openWhenFree && notesOn) { panelOpen = true; openWhenFree = false; }  // a card that arrived while Bayan was speaking opens the panel right after
    if (v.closeNotes !== tokClose) { const fire = v.closeNotes > tokClose; tokClose = v.closeNotes; if (fire) panelOpen = false; }
    const showPanel = panelOpen && notesOn;
    if (v.turnSeq !== turnSeq) { turnSeq = v.turnSeq; if (!rec) spk = v.turn || 'doctor'; }
    const turnIdle = live && ['idle', 'doctor', 'patient'].includes(v.live) && !v.processing && !v.queued && !v.speak && !localProc;
    const tint = turnIdle || (rec && live) ? (spk === 'doctor' ? 'd' : 'p') : (v.tint || 'n');

    // More… open on the start screen: the pearl steps aside (smaller, further out) and the content slides over,
    // so every language box stays visible next to the panel.
    const roomMore = scr === 'start' && moreOpen, MORE_W = 304, PEARL_SHIFT = roomMore ? 110 : 0;
    const geo = cap ? {s: 64, cx: 76, cy: 62} : rev ? {s: 48, cx: FW - 392, cy: 64} : roomMore ? {s: 210, cx: 230 - PEARL_SHIFT + OX, cy: 380 + OY} : think ? {s: 220, cx: 230 + OX, cy: 380 + OY} : {s: 280, cx: 230 + OX, cy: 380 + OY};
    const shadowCol = {n: 'rgba(31,111,178,.32)', d: 'rgba(31,111,178,.45)', p: 'rgba(14,138,111,.42)', h: 'rgba(194,65,12,.38)'}[tint];
    const glowD = cap ? 420 : rev ? 220 : 1000;
    geo.cx = mx(geo.cx);
    css($('bz-glow'), box(geo.cx, geo.cy, glowD, 1));
    css($('bz-rings'), box(geo.cx, geo.cy, geo.s, 2));
    const ringOp = v.speak && !cap ? 1 : 0;
    root.querySelectorAll('#bz-rings .ring').forEach((r) => css(r, 'opacity:' + ringOp + ';transition:opacity .6s'));
    ['n', 'd', 'p', 'h'].forEach((k) => {
      const o = tint === k ? 1 : 0;
      const g = $('s-gl-' + k); if (g) g.style.opacity = o;
      const p = $('s-pt-' + k); if (p) p.style.opacity = o;
    });
    $('s-pause').style.opacity = held ? 1 : 0;
    $('s-check').style.opacity = done ? 1 : 0;
    $('s-iri').style.opacity = held ? .25 : 1;
    const pw = $('bz-pearl-wrap'), pwCss = 'position:absolute;z-index:7;left:' + (geo.cx - geo.s / 2) + 'px;top:' + (geo.cy - geo.s / 2) + 'px;width:' + geo.s + 'px;height:' + geo.s + 'px;' +
      'padding:0;border:none;background:none;border-radius:50%;display:block;-webkit-tap-highlight-color:transparent;' +
      'transition:left .9s ' + EASE + ', top .9s ' + EASE + ', width .9s ' + EASE + ', height .9s ' + EASE;
    if (pw.__css !== pwCss) { pw.__css = pwCss; pw.style.cssText = pwCss; }
    pw.style.setProperty('--halo', {n: 'rgba(120,170,200,.16)', d: 'rgba(31,111,178,.16)', p: 'rgba(14,138,111,.16)', h: 'rgba(194,65,12,.12)'}[tint] || 'rgba(14,138,111,.14)');
    css($('s-pearl'), 'box-shadow:' + (held ? '0 0 0 3px #F5D0B5, ' : '') + '0 40px 90px -30px ' + shadowCol + ', inset 0 -20px 40px rgba(14,138,111,.12), inset 0 10px 26px rgba(255,255,255,.95);' +
      'transition:box-shadow .8s;animation-play-state:' + (held ? 'paused' : 'running'));

    css($('bz-wordmark'), M('position:absolute;left:40px;top:28px;z-index:8;display:flex;align-items:baseline;gap:10px;transition:opacity .4s;opacity:' + (cap ? 0 : 1)) + ';pointer-events:' + (cap ? 'none' : 'auto'));
    const homeAsk = ['consent', 'live', 'wrap', 'review'].includes(scr);
    if (!homeAsk) confirmOpen = false;
    css($('bz-confirm'), M('position:absolute;left:32px;top:80px;z-index:12;width:340px;padding:18px 20px;border-radius:20px;background:#FFFFFF;border:1px solid #E3EAE9;' +
      'box-shadow:0 18px 40px -24px rgba(23,52,48,.45);transition:opacity .25s, transform .3s ' + EASE + ';opacity:' + (confirmOpen ? 1 : 0) +
      ';transform:' + (confirmOpen ? 'none' : 'translateY(-6px)') + ';pointer-events:' + (confirmOpen ? 'auto' : 'none') + ';visibility:' + (confirmOpen ? 'visible' : 'hidden')));
    css($('bz-doclang'), M('position:absolute;right:40px;top:26px;z-index:8;transition:opacity .4s;opacity:' + (scr === 'start' ? 1 : 0) + ';pointer-events:' + (scr === 'start' ? 'auto' : 'none')));
    const hdr = scr === 'consent' || live;
    css($('bz-hright'), M('position:absolute;right:40px;top:26px;z-index:6;display:flex;align-items:center;gap:16px;transition:opacity .5s;opacity:' + (hdr ? 1 : 0) + ';pointer-events:' + (hdr ? 'auto' : 'none')));

    const showStatus = !cap && !rev;
    css($('bz-status'), M('position:absolute;left:' + (OX - PEARL_SHIFT) + 'px;top:' + (552 - (roomMore ? 30 : 0) + OY) + 'px;width:460px;z-index:2;display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 40px;' +
      'transition:opacity .5s ease ' + (showStatus ? '.35s' : '0s') + ', left .9s ' + EASE + ', top .9s ' + EASE + ';opacity:' + (showStatus ? 1 : 0)));
    if (localProc && v.ack === localProc) localProc = 0;  // the server has taken this recording (its own render)
    if (rec && !(live && v.live !== 'held' && v.live !== 'confirm' && (v.live !== 'caption' || v.settle))) cancelRec();

    const RP = 'left:' + (500 + OX) + 'px;top:' + (96 + OY) + 'px;right:' + (56 + OX) + 'px;bottom:' + (40 + OY) + 'px';
    const RPX = 'left:' + (500 + OX) + 'px;top:' + (96 + OY) + 'px;right:' + (showPanel ? 424 : 56 + OX) + 'px;bottom:' + (40 + OY) + 'px';
    const RPS = roomMore ? 'left:' + (390 + OX) + 'px;top:' + (96 + OY) + 'px;right:' + (MORE_W + 32) + 'px;bottom:' + (40 + OY) + 'px' : RP;
    css($('L-start'), M(lay(scr === 'start', RPS)));
    if (scr !== 'start') moreOpen = false;
    // the same docked side panel as Notes: flush right (left in RTL), under the header, full height, slides in
    css($('bz-more'), M('position:absolute;top:92px;right:0;bottom:0;width:' + MORE_W + 'px;z-index:6;overflow:hidden;border-left:1px solid #E3EAE9;border-top:1px solid #E3EAE9;border-top-left-radius:20px;background:#FFFFFF;display:flex;flex-direction:column;' +
      'transition:transform .55s ' + EASE + ', visibility 0s linear ' + (moreOpen ? '0s' : '.55s') + ';transform:' + (moreOpen ? 'none' : 'translateX(100%)') +
      ';visibility:' + (moreOpen ? 'visible' : 'hidden') + ';pointer-events:' + (moreOpen ? 'auto' : 'none')));
    css($('L-consent'), M(lay(scr === 'consent', RP)));
    css($('L-idle'), M(lay(live && v.live === 'idle', RPX)));
    css($('L-doctor'), M(lay(live && v.live === 'doctor', RPX)));
    css($('L-patient'), M(lay(live && v.live === 'patient', RPX)));
    css($('L-held'), M(lay(held, RPX)));
    css($('L-confirm'), M(lay(live && v.live === 'confirm', RPX)));
    const cf = v.confirm || {};
    txt($('bz-cf-q'), cf.detected === 'patient' ? T('cf_q_patient') : T('cf_q_doctor'));
    txt($('bz-cf-yes'), cf.detected === 'patient' ? T('cf_yes_patient') : T('cf_yes_doctor'));
    txt($('bz-cf-no'), cf.detected === 'patient' ? T('cf_keep_doctor') : T('cf_keep_patient'));
    css($('L-wrap'), M(lay(think, RP)));
    css($('L-revLeft'), M(lay(rev, 'left:40px;top:96px;right:500px;bottom:40px;display:flex;flex-direction:column;gap:14px')));
    css($('L-revRight'), M(lay(rev, 'right:0;top:0;bottom:0;width:460px', 2, 'linear-gradient(180deg, #F1F9F6 0%, #E8F4F0 100%);border-left:1px solid #DCEDE7')));
    css($('L-caption'), M(lay(cap, 'left:0;top:0;right:0;bottom:0', 4)));

    // consent
    const cn = (v.consent && v.consent.native) || '…';
    const cEl = $('bz-consent-native'); setLang(cEl, lang); txt(cEl, cn); cEl.style.fontSize = fit(cn, 34, 26, 80);
    txt($('bz-consent-en'), T('consent_doc'));
    setLang($('bz-yes'), lang); txt($('bz-yes'), L.yes); setLang($('bz-no'), lang); txt($('bz-no'), L.no);

    // doctor
    const d = v.doctor || {};
    const de = $('bz-doc-en'); txt(de, d.en); de.style.fontSize = fit(d.en, 40, 24, 40);
    const dn = $('bz-doc-native'); setLang(dn, lang); const dnt = d.pending ? '…' : (d.native || ''); txt(dn, dnt); dn.style.fontSize = fit(dnt, 34, 22, 32);

    // patient
    const p = v.patient || {};
    const pn = $('bz-pat-native'); setLang(pn, lang); patientNative(pn, p.native || '', p.idiom || '');
    pn.style.fontSize = showPanel ? '23px' : fit(p.native, 34, 22, 40);
    const pe = $('bz-pat-en'); const pet = p.pending ? '…' : (p.en || ''); txt(pe, pet); pe.style.fontSize = showPanel ? '23px' : fit(pet, 36, 22, 44);
    txt($('bz-pat-note-t'), p.note || ''); $('bz-pat-note').style.display = p.note ? 'flex' : 'none';

    // notes button + panel
    const nbOn = notesOn && !showPanel;
    css($('bz-notebtn'), M('position:absolute;right:24px;bottom:24px;z-index:6;width:60px;height:60px;border-radius:50%;border:1px solid #E3EAE9;background:#FFFFFF;' +
      'display:flex;align-items:center;justify-content:center;box-shadow:0 10px 26px -18px rgba(23,52,48,.4);transition:opacity .45s ease, transform .6s ' + EASE + ';' +
      'opacity:' + (nbOn ? 1 : 0) + ';transform:' + (nbOn ? 'none' : 'scale(.85)') + ';pointer-events:' + (nbOn ? 'auto' : 'none')));
    $('bz-notebtn').setAttribute('aria-expanded', showPanel ? 'true' : 'false');
    const badge = $('bz-badge'); txt(badge, String(v.badge || '')); badge.style.display = v.badge ? 'flex' : 'none';
    css($('bz-panel'), M('position:absolute;top:92px;right:0;bottom:0;width:380px;z-index:5;overflow:hidden;border-left:1px solid #E3EAE9;border-top:1px solid #E3EAE9;border-top-left-radius:20px;background:#FFFFFF;' +
      'transition:transform .55s ' + EASE + ', visibility 0s linear ' + (showPanel ? '0s' : '.55s') + ';transform:' + (showPanel ? 'none' : 'translateX(100%)') +
      ';visibility:' + (showPanel ? 'visible' : 'hidden') + ';pointer-events:' + (showPanel ? 'auto' : 'none')));
    notesList(v.notes || []);
    const sugs = v.suggestions || [];
    $('bz-sugsec').style.display = sugs.length ? 'block' : 'none';
    sugList(sugs, LN(lang));

    // held
    const h = v.held || {};
    txt($('bz-held-h'), h.headline || '');
    txt($('bz-held-pq'), h.pq ? '“' + h.pq + '”' : '');
    $('bz-held-pq').parentNode.style.display = h.pq ? '' : 'none';   // a held claim may quote no patient words
    txt($('bz-held-dq'), h.dq ? '“' + h.dq + '”' : '');

    // wrap
    stepsList(v.steps || []);

    // review
    const r = v.review || {};
    if (r.plan_id && r.plan_id !== planKey) { planKey = r.plan_id; $('careplan').value = r.plan || ''; $('bz-qr').innerHTML = r.qr || ''; }
    $('careplan').readOnly = done || !!r.sending;
    const rp = $('bz-report');
    if (rp) { if (r.doctor_pdf && (done || scr === 'review')) { if (rp.getAttribute('href') !== r.doctor_pdf) rp.setAttribute('href', r.doctor_pdf); rp.style.display = 'inline-block'; } else { rp.removeAttribute('href'); rp.style.display = 'none'; } }
    const ws = r.warnings || [], wk = JSON.stringify(ws) + (r.confirm ? '!' : '');
    const wl = $('bz-warn');
    if (wl.__k !== wk) {
      wl.__k = wk; wl.textContent = '';
      ws.forEach((t) => { const li = document.createElement('li'); li.textContent = t; if (r.confirm) li.className = 'strong'; wl.appendChild(li); });
    }
    wl.style.display = ws.length && !done ? 'flex' : 'none';
    txt($('bz-rev-title'), done ? T('sent_title') : T('for_patient'));
    const ap = $('bz-approve'); txt(ap, done ? T('sent') : r.sending ? T('sending') : r.confirm ? T('send_anyway') : T('approve'));
    ap.style.background = done ? '#0B6E59' : '#0E8A6F'; ap.disabled = done || !!r.sending; ap.style.cursor = done ? 'default' : 'pointer';
    css($('bz-new'), 'align-self:stretch;margin-top:12px;height:52px;border-radius:16px;border:1px solid #BFE3D8;background:#FFFFFF;color:#0B6E59;font-size:16px;font-weight:500;' +
      'opacity:' + (done ? 1 : 0) + ';pointer-events:' + (done ? 'auto' : 'none'));

    // caption
    const c = v.caption || {};
    const capIn = $('bz-cap-in'); setLang(capIn, lang); txt(capIn, L.inLang);
    const capEl = $('bz-cap-native'); setLang(capEl, lang); capEl.style.fontSize = fit(c.native, 68, 40, 30);
    if (c.key) words(capEl, c.native, c.rate, c.key, !!c.audio);
    txt($('bz-cap-en'), c.en ? '“' + c.en + '”' : '');
    $('bz-cap-novoice').style.display = c.key && c.audio === false ? 'block' : 'none';  // silent: text only, said so
    setLang($('bz-again'), lang); txt($('bz-again'), L.again); setLang($('bz-slower'), lang); txt($('bz-slower'), L.slower);

    // clock
    if (scr === 'consent' || live) { if (clockBase === null || Math.abs((performance.now() - clockBase) / 1000 - v.elapsed) > 2) clockBase = performance.now() - (v.elapsed || 0) * 1000; }
    else if (scr === 'start') { clockBase = null; txt($('bz-clock'), '0:00'); }

    // one-shot signals from the server
    if (v.autoEnd !== tokEnd) { const fire = v.autoEnd > tokEnd; tokEnd = v.autoEnd; if (fire) { stopMic(); send('end'); } }
    const nt = v.notice || {};
    if (nt.id && nt.id !== tokNotice) { const fire = nt.id > tokNotice; tokNotice = nt.id; if (fire && nt.text) toast(nt.text); }
    if (!demoTried && scr === 'start' && /[?&]demo=1\b/.test(location.search)) { demoTried = true; setTimeout(() => send('demo'), 900); }
    if (v.stopMic !== tokStop) { const fire = v.stopMic > tokStop; tokStop = v.stopMic; if (fire) stopMic(); }
    if (scr === 'start') { paintChips(); }
    if (v.toast) toast(v.toast);
    paintLive();
    fitFrames();
    tryLand();  // fly the loading pearl into place, then fade the app in (only once scaled + rendered + fonts)
  }

  setInterval(() => {
    if (clockBase === null || !V || !(V.screen === 'consent' || V.screen === 'live')) return;
    const t = Math.max(0, Math.floor((performance.now() - clockBase) / 1000));
    const el = $('bz-clock'); if (el) txt(el, Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'));
  }, 500);

  function check() {
    fitFrames();
    const el = document.querySelector('.bz-s[data-s]');
    if (!el) return;
    const s = el.getAttribute('data-s');
    const root = $('bayan');
    if (s === lastS && root === appliedEl) return;
    let v; try { v = JSON.parse(s); } catch (e) { return; }
    if (s !== lastS && V && v.seq < V.seq && root === appliedEl) { lastS = s; return; }  // stale update
    lastS = s; V = v; apply(v);
  }
  let raf = 0;
  new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; check(); }); })
    .observe(document.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-s']});
  window.addEventListener('load', check);
  // Light theme only.
  const light = () => { document.documentElement.classList.remove('dark'); if (document.body) document.body.classList.remove('dark'); };
  light(); window.addEventListener('load', light);
})();
