
(() => {
  if (window.__bayanUI) return; window.__bayanUI = true;
  const EASE = 'cubic-bezier(.2,.8,.2,1)';
  const LANGS = {
    ne: {name:'Nepali', inLang:'नेपालीमा', again:'फेरि भन्नुहोस्', slower:'बिस्तारै', yes:'हो', no:'होइन'},
    hi: {name:'Hindi', inLang:'हिन्दी में', again:'फिर से कहिए', slower:'धीरे', yes:'हाँ', no:'नहीं'},
    ur: {name:'Urdu', inLang:'اردو میں', again:'دوبارہ کہیے', slower:'آہستہ', yes:'ہاں', no:'نہیں'},
    bn: {name:'Bengali', inLang:'বাংলায়', again:'আবার বলুন', slower:'ধীরে', yes:'হ্যাঁ', no:'না'},
    ml: {name:'Malayalam', inLang:'മലയാളത്തിൽ', again:'വീണ്ടും പറയൂ', slower:'പതുക്കെ', yes:'അതെ', no:'ഇല്ല'},
    tl: {name:'Filipino', inLang:'sa Filipino', again:'Ulitin', slower:'Mas mabagal', yes:'Oo', no:'Hindi'}
  };
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
  ICON.observation = ICON.bulb;
  const $ = (id) => document.getElementById(id);
  let V = null, lastS = '', appliedEl = null, selLang = 'ne', panelOpen = false, hearing = false, revTab = 'plan';
  let tokOpen = 0, tokClose = 0, tokEnd = 0, tokStop = 0, capKey = '', planKey = '', notesKey = '', sugKey = '', stepsKey = '', patKey = '';
  let clockBase = null;

  const fit = (text, max, min, ideal) => { const n = (text || '').length; return n <= ideal ? max + 'px' : Math.max(min, Math.round(max * Math.sqrt(ideal / n))) + 'px'; };
  const css = (el, s) => { if (el && el.__css !== s) { el.style.cssText = s; el.__css = s; } };
  const txt = (el, t) => { if (el && el.textContent !== (t || '')) el.textContent = t || ''; };
  const lay = (on, pos, z, bg) => 'position:absolute;' + pos + ';z-index:' + (z || 3) + ';' + (bg ? 'background:' + bg + ';' : '') +
    'transition:opacity .55s ease ' + (on ? '.3s' : '0s') + ', transform .8s ' + EASE + ' ' + (on ? '.25s' : '0s') + ', right .55s ' + EASE + ';' +
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

  // ---------------------------------------------------------------- microphone (FastRTC component, kept off-screen)
  const micBtns = () => { const r = document.querySelector('#mic'); return r ? [...r.querySelectorAll('button')] : []; };
  const findBtn = (re) => micBtns().find((b) => re.test((b.textContent || '').trim()));
  let micTimer = null;
  function startMic() {
    clearInterval(micTimer);
    let tries = 0, accessClicked = false;
    const tick = () => {
      tries++;
      if (findBtn(/Bayan stop/)) { clearInterval(micTimer); return; }
      const start = findBtn(/Bayan start/);
      if (start) { start.click(); clearInterval(micTimer); return; }
      const access = findBtn(/Access Microphone/i);
      if (access && !accessClicked) { accessClicked = true; access.click(); }
      if (tries > 160) { clearInterval(micTimer); send('mic_failed'); }
    };
    tick(); micTimer = setInterval(tick, 250);
  }
  function stopMic() { clearInterval(micTimer); const b = findBtn(/Bayan stop/); if (b) b.click(); hearing = false; }
  window.bayanStopMic = stopMic;

  // ReplyOnPause status over the data channel + connection state, no server round trip.
  const origCDC = RTCPeerConnection.prototype.createDataChannel;
  RTCPeerConnection.prototype.createDataChannel = function (...args) {
    const ch = origCDC.apply(this, args), pc = this;
    ch.addEventListener('message', (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m && m.type === 'log') {
        if (m.data === 'started_talking') hearing = true;
        else if (m.data === 'pause_detected' || m.data === 'response_starting') hearing = false;
        paintBars();
      }
    });
    pc.addEventListener('connectionstatechange', () => {
      if (pc.connectionState === 'connected') send('connected');
      if (pc.connectionState === 'failed') send('mic_failed');
      if (['closed', 'failed', 'disconnected'].includes(pc.connectionState)) { hearing = false; paintBars(); }
    });
    return ch;
  };

  // ---------------------------------------------------------------- actions -> Python
  function send(act, extra) {
    window.__bzNext = JSON.stringify(Object.assign({act: act, n: Date.now()}, extra || {}));
    const b = $('bz-send'); if (b) b.click();
  }
  window.bayanSend = send;
  function paintChips() { document.querySelectorAll('#bz-chips .chip').forEach((c) => c.classList.toggle('sel', c.dataset.id === selLang)); }
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-act]');
    if (!b) { window.__bayanAct = ''; return; }
    const act = b.dataset.act;
    if (act === '__send') { window.__bayanAct = window.__bzNext || ''; window.__bzNext = ''; return; }
    const p = {act: act, id: b.dataset.id || '', n: Date.now()};
    if (act === 'lang') { selLang = b.dataset.id; paintChips(); window.__bayanAct = ''; return; }
    if (act === 'notes') { panelOpen = !panelOpen; if (V) apply(V); window.__bayanAct = ''; return; }
    if (act === 'notes-close') { panelOpen = false; if (V) apply(V); window.__bayanAct = ''; return; }
    if (act === 'revtab') { revTab = b.dataset.id === 'note' ? 'note' : 'plan'; if (V) apply(V); window.__bayanAct = ''; return; }
    if (act === 'start') { p.lang = selLang; startMic(); }
    if (act === 'demo') { p.lang = 'ne'; }
    if (act === 'end' || act === 'consent_no' || act === 'new') stopMic();
    if (act === 'approve') { if (V && V.screen !== 'review') { window.__bayanAct = ''; return; } p.text = ($('careplan') || {}).value || ''; p.note = ($('bz-note') || {}).value || ''; }
    if (act === 'ask') { panelOpen = false; if (V) apply(V); }
    if (act === 'unlock') { p.code = ($('bz-code') || {}).value || ''; }
    window.__bayanAct = JSON.stringify(p);
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target && e.target.id === 'bz-code') { e.preventDefault(); const b = document.querySelector('[data-act=unlock]'); if (b) b.click(); }
  }, true);

  // ---------------------------------------------------------------- render
  function paintBars() {
    if (!V) return;
    const on = V.listen || (hearing && V.screen === 'live' && V.live !== 'caption' && V.live !== 'held');
    css($('bz-bars'), 'display:flex;align-items:center;gap:6px;height:34px;margin-bottom:14px;transition:opacity .4s;opacity:' + (on ? 1 : 0));
  }
  function words(el, text, rate, key) {
    if (capKey === key) return; capKey = key;
    el.textContent = '';
    let chars = 0;
    (text || '').split(/\s+/).filter(Boolean).forEach((w) => {
      const s = document.createElement('span'); s.className = 'w';
      s.style.animationDelay = (0.35 + chars / (rate || 11)).toFixed(2) + 's';
      s.textContent = w + ' '; el.appendChild(s); chars += w.length + 1;
    });
  }
  function notesList(notes) {
    const k = JSON.stringify(notes); if (k === notesKey) return; notesKey = k;
    const box = $('bz-noted'); box.textContent = '';
    if (!notes.length) { const p = document.createElement('div'); p.style.cssText = 'font-size:15px;color:#5B6B69;line-height:1.5'; p.textContent = 'Allergies, medicines and tests show here as they come up.'; box.appendChild(p); }
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
      h.innerHTML = '<span style="display:flex;align-items:center">' + ICON.bulb + '</span>'; h.appendChild(document.createTextNode(s.label || 'Ask next'));
      const p = document.createElement('p'); p.style.cssText = 'margin:0;font-size:17px;line-height:1.45;font-weight:500;color:#173430'; p.textContent = s.text;
      const b = document.createElement('button'); b.type = 'button'; b.dataset.act = 'ask'; b.dataset.id = s.id;
      b.style.cssText = 'align-self:flex-start;height:44px;padding:0 18px 0 14px;border-radius:999px;border:none;background:#0E8A6F;color:#FFFFFF;font-size:15px;font-weight:500;display:flex;align-items:center;gap:8px';
      b.innerHTML = ICON.speaker; b.appendChild(document.createTextNode('Ask the patient in ' + langName));
      w.appendChild(h); w.appendChild(p); w.appendChild(b); box.appendChild(w);
    });
  }
  function stepsList(steps) {
    const k = JSON.stringify(steps); if (k === stepsKey) return; stepsKey = k;
    const box = $('bz-steps'); box.textContent = '';
    steps.forEach((s) => {
      const d = document.createElement('div'); d.className = 'step ' + s.state;
      d.innerHTML = s.state === 'done' ? ICON.check : s.state === 'doing' ? '<span class="spinner"></span>' : '<span class="dot"></span>';
      d.appendChild(document.createTextNode(s.label)); box.appendChild(d);
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
    const scr = v.screen, live = scr === 'live';
    const cap = live && v.live === 'caption', rev = scr === 'review' || scr === 'sent';
    const think = scr === 'wrap', held = live && v.live === 'held', done = scr === 'sent';
    const L = LANGS[v.lang] || LANGS.ne, lang = v.lang || 'ne';
    const notesOn = live && !cap;
    if (!notesOn) panelOpen = false;
    if (v.openNotes !== tokOpen) { const fire = v.openNotes > tokOpen; tokOpen = v.openNotes; if (fire && notesOn) panelOpen = true; }
    if (v.closeNotes !== tokClose) { const fire = v.closeNotes > tokClose; tokClose = v.closeNotes; if (fire) panelOpen = false; }
    const showPanel = panelOpen && notesOn;
    const tint = v.tint || 'n';

    const geo = cap ? {s: 64, cx: 76, cy: 62} : rev ? {s: 48, cx: FW - 392, cy: 64} : think ? {s: 220, cx: 230 + OX, cy: 380 + OY} : {s: 280, cx: 230 + OX, cy: 380 + OY};
    const shadowCol = {n: 'rgba(31,111,178,.32)', d: 'rgba(31,111,178,.45)', p: 'rgba(14,138,111,.42)', h: 'rgba(194,65,12,.38)'}[tint];
    const glowD = cap ? 420 : rev ? 220 : 1000;
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
    css($('s-iri'), 'transition:opacity .8s;opacity:' + (held ? .25 : 1) + ';animation-duration:' + (think ? '2.5s' : v.speak ? '7s' : '14s'));
    css($('bz-pearl-wrap'), 'position:absolute;z-index:7;left:' + (geo.cx - geo.s / 2) + 'px;top:' + (geo.cy - geo.s / 2) + 'px;width:' + geo.s + 'px;height:' + geo.s + 'px;' +
      'transition:left .9s ' + EASE + ', top .9s ' + EASE + ', width .9s ' + EASE + ', height .9s ' + EASE + ';pointer-events:none');
    css($('s-pearl'), 'box-shadow:' + (held ? '0 0 0 3px #F5D0B5, ' : '') + '0 40px 90px -30px ' + shadowCol + ', inset 0 -20px 40px rgba(14,138,111,.12), inset 0 10px 26px rgba(255,255,255,.95);' +
      'transition:box-shadow .8s;animation-play-state:' + (held ? 'paused' : 'running'));

    css($('bz-wordmark'), 'position:absolute;left:40px;top:28px;z-index:6;display:flex;align-items:baseline;gap:10px;transition:opacity .4s;opacity:' + (cap ? 0 : 1));
    const hdr = scr === 'consent' || live;
    css($('bz-hright'), 'position:absolute;right:40px;top:26px;z-index:6;display:flex;align-items:center;gap:16px;transition:opacity .5s;opacity:' + (hdr ? 1 : 0) + ';pointer-events:' + (hdr ? 'auto' : 'none'));

    const showStatus = !cap && !rev;
    css($('bz-status'), 'position:absolute;left:' + OX + 'px;top:' + (552 + OY) + 'px;width:460px;z-index:2;display:flex;flex-direction:column;align-items:center;text-align:center;padding:0 40px;' +
      'transition:opacity .5s ease ' + (showStatus ? '.35s' : '0s') + ';opacity:' + (showStatus ? 1 : 0));
    const st = v.status || ['', '', '#173430'];
    txt($('bz-st-title'), st[0]); $('bz-st-title').style.color = st[2]; txt($('bz-st-sub'), st[1]);
    root.querySelectorAll('#bz-bars .bar').forEach((b) => { b.style.background = st[2]; });
    paintBars();

    const RP = 'left:' + (500 + OX) + 'px;top:' + (96 + OY) + 'px;right:' + (56 + OX) + 'px;bottom:' + (40 + OY) + 'px';
    const RPX = 'left:' + (500 + OX) + 'px;top:' + (96 + OY) + 'px;right:' + (showPanel ? 424 : 56 + OX) + 'px;bottom:' + (40 + OY) + 'px';
    css($('L-start'), lay(scr === 'start', RP));
    css($('L-consent'), lay(scr === 'consent', RP));
    css($('L-idle'), lay(live && v.live === 'idle', RPX));
    css($('L-doctor'), lay(live && v.live === 'doctor', RPX));
    css($('L-patient'), lay(live && v.live === 'patient', RPX));
    css($('L-held'), lay(held, RPX));
    css($('L-wrap'), lay(think, RP));
    css($('L-revLeft'), lay(rev, 'left:40px;top:96px;right:500px;bottom:40px;display:flex;flex-direction:column;gap:14px'));
    css($('L-revRight'), lay(rev, 'right:0;top:0;bottom:0;width:460px', 2, 'linear-gradient(180deg, #F1F9F6 0%, #E8F4F0 100%);border-left:1px solid #DCEDE7'));
    css($('L-caption'), lay(cap, 'left:0;top:0;right:0;bottom:0', 4));

    // consent
    const cn = (v.consent && v.consent.native) || '…';
    const cEl = $('bz-consent-native'); setLang(cEl, lang); txt(cEl, cn); cEl.style.fontSize = fit(cn, 34, 26, 80);
    txt($('bz-consent-en'), v.consent ? v.consent.en : '');
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
    css($('bz-notebtn'), 'position:absolute;right:24px;bottom:24px;z-index:6;width:60px;height:60px;border-radius:50%;border:1px solid #E3EAE9;background:#FFFFFF;' +
      'display:flex;align-items:center;justify-content:center;box-shadow:0 10px 26px -18px rgba(23,52,48,.4);transition:opacity .45s ease, transform .6s ' + EASE + ';' +
      'opacity:' + (nbOn ? 1 : 0) + ';transform:' + (nbOn ? 'none' : 'scale(.85)') + ';pointer-events:' + (nbOn ? 'auto' : 'none'));
    $('bz-notebtn').setAttribute('aria-expanded', showPanel ? 'true' : 'false');
    const badge = $('bz-badge'); txt(badge, String(v.badge || '')); badge.style.display = v.badge ? 'flex' : 'none';
    css($('bz-panel'), 'position:absolute;top:92px;right:0;bottom:0;width:380px;z-index:5;overflow:hidden;border-left:1px solid #E3EAE9;border-top:1px solid #E3EAE9;border-top-left-radius:20px;background:#FFFFFF;' +
      'transition:transform .55s ' + EASE + ', visibility 0s linear ' + (showPanel ? '0s' : '.55s') + ';transform:' + (showPanel ? 'none' : 'translateX(100%)') +
      ';visibility:' + (showPanel ? 'visible' : 'hidden') + ';pointer-events:' + (showPanel ? 'auto' : 'none'));
    notesList(v.notes || []);
    const sugs = v.suggestions || [];
    $('bz-sugsec').style.display = sugs.length ? 'block' : 'none';
    sugList(sugs, v.langName || L.name);

    // held
    const h = v.held || {};
    txt($('bz-held-h'), h.headline || '');
    txt($('bz-held-pq'), h.pq ? '“' + h.pq + '”' : '');
    txt($('bz-held-dq'), h.dq ? '“' + h.dq + '”' : '');

    // wrap
    stepsList(v.steps || []);

    // review
    const r = v.review || {};
    if (r.plan_id && r.plan_id !== planKey) { planKey = r.plan_id; $('careplan').value = r.plan_en || ''; $('bz-note').value = r.note || ''; $('bz-qr').innerHTML = r.qr || ''; revTab = 'plan'; }
    $('careplan').readOnly = true; $('bz-note').readOnly = done;
    const onNote = revTab === 'note';
    $('careplan').style.display = onNote ? 'none' : 'block'; $('bz-note').style.display = onNote ? 'block' : 'none';
    $('bz-tab-plan').style.fontWeight = onNote ? '500' : '600'; $('bz-tab-plan').style.color = onNote ? '#5B6B69' : '#173430';
    $('bz-tab-note').style.fontWeight = onNote ? '600' : '500'; $('bz-tab-note').style.color = onNote ? '#173430' : '#5B6B69';
    [['bz-pdf-patient', r.patient_pdf], ['bz-pdf-doctor', r.doctor_pdf], ['bz-wa', done ? r.wa : '']].forEach(([id, href]) => {
      const a = $(id); if (!a) return;
      if (href) { if (a.getAttribute('href') !== href) a.setAttribute('href', href); a.style.display = 'inline-block'; } else { a.removeAttribute('href'); a.style.display = 'none'; }
    });
    const w = (r.warnings || []).join(' ');
    txt($('bz-warn'), w); $('bz-warn').style.display = w && !done ? 'block' : 'none';
    txt($('bz-rev-title'), done ? 'Sent to the patient' : 'For the patient');
    const ap = $('bz-approve'); txt(ap, done ? 'Sent' : r.sending ? 'Sending…' : 'Approve and send');
    ap.style.background = done ? '#0B6E59' : '#0E8A6F'; ap.disabled = done || !!r.sending; ap.style.cursor = done ? 'default' : 'pointer';
    css($('bz-new'), 'align-self:stretch;margin-top:12px;height:52px;border-radius:16px;border:1px solid #BFE3D8;background:#FFFFFF;color:#0B6E59;font-size:16px;font-weight:500;transition:opacity .5s;' +
      'opacity:' + (done ? 1 : 0) + ';pointer-events:' + (done ? 'auto' : 'none'));

    // caption
    const c = v.caption || {};
    const capIn = $('bz-cap-in'); setLang(capIn, lang); txt(capIn, L.inLang);
    const capEl = $('bz-cap-native'); setLang(capEl, lang); capEl.style.fontSize = fit(c.native, 68, 40, 30);
    if (c.key) words(capEl, c.native, c.rate, c.key);
    txt($('bz-cap-en'), c.en ? '“' + c.en + '”' : '');
    setLang($('bz-again'), lang); txt($('bz-again'), L.again); setLang($('bz-slower'), lang); txt($('bz-slower'), L.slower);

    // clock
    if (scr === 'consent' || live) { if (clockBase === null || Math.abs((performance.now() - clockBase) / 1000 - v.elapsed) > 2) clockBase = performance.now() - (v.elapsed || 0) * 1000; }
    else if (scr === 'start') { clockBase = null; txt($('bz-clock'), '0:00'); }

    // one-shot signals from the server
    if (v.autoEnd !== tokEnd) { const fire = v.autoEnd > tokEnd; tokEnd = v.autoEnd; if (fire) { stopMic(); send('end'); } }
    if (v.stopMic !== tokStop) { const fire = v.stopMic > tokStop; tokStop = v.stopMic; if (fire) stopMic(); }
    if (scr === 'start') { paintChips(); }
    toast(v.toast || '');
    fitFrames();
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

