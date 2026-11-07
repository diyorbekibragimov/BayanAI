"""Bayan stage: static markup + CSS + a client-side renderer (ported from the approved prototype).

The server never re-renders this markup. It pushes a JSON view into a hidden gr.HTML
(`.bz-s[data-s]`); the head script watches for it and updates styles/text in place, so every
CSS transition from the prototype still plays. Text is always set with textContent (no HTML
injection). Buttons carry data-act; a capture-phase click listener records the action, and the
gr.HTML click event sends it to Python through a hidden textbox (see app.py).
"""

FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600"
         "&family=Noto+Sans+Devanagari:wght@400;500;600&family=Noto+Sans+Bengali:wght@400;500;600"
         "&family=Noto+Sans+Malayalam:wght@400;500;600&family=Noto+Naskh+Arabic:wght@400;500;600"
         "&family=Reem+Kufi:wght@500&display=swap")

CSS = r"""
html,body{margin:0;overflow:hidden;background:#FBFCFC !important}
body,gradio-app,.gradio-container,.gradio-container .main,.gradio-container .wrap,.gradio-container .contain{background:#FBFCFC !important}
.gradio-container{padding:0 !important;max-width:none !important;min-height:100vh}
footer,.gradio-container footer,.toast-wrap{display:none !important}
#mic,#demo-audio{position:fixed !important;left:-10000px !important;top:0 !important;width:360px !important}
#bayan-state{position:fixed !important;left:-10000px !important;top:0 !important;width:10px !important;height:10px !important;overflow:hidden !important}
.bz-frame{position:fixed;left:0;top:0;width:1280px;height:800px;overflow:hidden;background:#FBFCFC;transform-origin:0 0;
  font-family:'Instrument Sans',system-ui,sans-serif;color:#173430;z-index:50;-webkit-font-smoothing:antialiased}
.bz-frame *{box-sizing:border-box}
.bz-frame p,.bz-frame h1,.bz-frame h2{margin:0}
.bz-frame button{font-family:inherit;cursor:pointer;-webkit-tap-highlight-color:transparent}
.bz-frame button:focus-visible{outline:2px solid #1F6FB2;outline-offset:3px}
.bz-frame [lang=ne],.bz-frame [lang=hi]{font-family:'Noto Sans Devanagari','Instrument Sans',sans-serif}
.bz-frame [lang=bn]{font-family:'Noto Sans Bengali','Instrument Sans',sans-serif}
.bz-frame [lang=ml]{font-family:'Noto Sans Malayalam','Instrument Sans',sans-serif}
.bz-frame [lang=ur]{font-family:'Noto Naskh Arabic',serif}
.bz-frame [lang=en],.bz-frame [lang=tl]{font-family:'Instrument Sans',system-ui,sans-serif}
@keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.035)}}
@keyframes turn{to{transform:rotate(360deg)}}
@keyframes sweep{0%{background-position:120% 0}100%{background-position:-20% 0}}
@keyframes level{0%,100%{transform:scaleY(.3)}50%{transform:scaleY(1)}}
@keyframes wave{0%{transform:scale(1);opacity:.6}100%{transform:scale(1.9);opacity:0}}
@keyframes lit{to{color:#173430}}
@keyframes spin{to{transform:rotate(360deg)}}
.bz-frame .pearl{position:relative;width:100%;height:100%;border-radius:50%;overflow:hidden;animation:breathe 5s ease-in-out infinite}
.bz-frame .iri{position:absolute;inset:-25%;background:conic-gradient(from 90deg,rgba(255,255,255,0) 0deg,rgba(189,235,230,.75) 70deg,rgba(255,255,255,0) 140deg,rgba(207,227,255,.7) 210deg,rgba(255,255,255,0) 280deg,rgba(228,222,250,.7) 330deg,rgba(255,255,255,0) 360deg);filter:blur(16px);animation:turn 14s linear infinite}
.bz-frame .gloss{position:absolute;left:16%;top:11%;width:44%;height:30%;border-radius:50%;background:radial-gradient(closest-side,rgba(255,255,255,.95),rgba(255,255,255,0))}
.bz-frame .ring{position:absolute;inset:0;border-radius:50%;border:2px solid rgba(14,138,111,.32);animation:wave 3.6s ease-out infinite}
.bz-frame .r2{animation-delay:1.2s}.bz-frame .r3{animation-delay:2.4s}
.bz-frame .bar{width:6px;height:34px;border-radius:3px;transform-origin:center;animation:level 1s ease-in-out infinite}
.bz-frame .b2{animation-delay:.15s}.bz-frame .b3{animation-delay:.3s}.bz-frame .b4{animation-delay:.45s}.bz-frame .b5{animation-delay:.6s}
.bz-frame .emerge{background:linear-gradient(100deg,#173430 0%,#173430 42%,#6CC3B3 50%,#173430 58%,#173430 100%);background-size:250% 100%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:sweep 3.4s ease-in-out infinite}
.bz-frame .w{color:#A8B8B5;animation:lit .3s ease forwards}
.bz-frame .spinner{display:inline-block;width:18px;height:18px;border-radius:50%;border:2px solid #CFE7E1;border-top-color:#0E8A6F;animation:spin .9s linear infinite;flex:none}
.bz-frame .tl{position:absolute;inset:0;border-radius:50%}
.bz-frame .pt{position:absolute;inset:0;transition:opacity .8s}
.bz-frame .lbl{font-size:15px}
.bz-frame .chip{height:76px;border-radius:18px;border:1px solid #D5DEDD;background:#FFFFFF;color:#173430;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;transition:border-color .25s,background .25s}
.bz-frame .chip.sel{border:2px solid #0E8A6F;background:#F1F8F7}
.bz-frame .chip .n{font-size:20px;font-weight:500}.bz-frame .chip .e{font-size:14px;color:#5B6B69}
.bz-frame .pill{height:64px;padding:0 30px;border-radius:999px;border:1px solid #E3EAE9;background:rgba(255,255,255,.82);backdrop-filter:blur(8px);box-shadow:0 12px 32px -22px rgba(23,52,48,.35);color:#173430;display:flex;align-items:center;gap:12px;transition:background .2s,box-shadow .2s}
.bz-frame .pill:active{background:#F1F8F7}
.bz-frame .note-row{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:500;color:#173430;line-height:1.35}
.bz-frame .note-row svg{flex:none}
.bz-frame .idiom{text-decoration:underline;text-decoration-style:dotted;text-decoration-color:#6B4FA8;text-underline-offset:8px}
.bz-frame textarea{outline:none}
.bz-frame .btn-dark{height:64px;padding:0 30px;border-radius:18px;border:none;background:#173430;color:#FFFFFF;font-size:18px;font-weight:500}
.bz-frame .link{border:none;background:none;color:#5B6B69;font-size:15px;text-decoration:underline;text-underline-offset:4px;padding:10px 6px}
.bz-frame .link:hover{color:#173430}
.bz-frame .step{display:flex;align-items:center;gap:14px}
.bz-frame .step .dot{width:18px;height:18px;border-radius:50%;border:2px solid #D5DEDD;flex:none}
.bz-frame .step.todo{color:#5B6B69}
@media (prefers-reduced-motion: reduce){.bz-frame .pearl,.bz-frame .iri,.bz-frame .ring,.bz-frame .bar,.bz-frame .emerge,.bz-frame .spinner{animation:none}.bz-frame .emerge{color:#173430;background:none}.bz-frame .w{animation:none;color:#173430}}
"""

SVG = {
    "note": '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><path d="M14 3v6h6"></path><path d="M8 13h8"></path><path d="M8 17h5"></path></svg>',
    "close": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5B6B69" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"></path></svg>',
    "book": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6B4FA8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none;margin-top:2px"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z"></path><path d="M4 5.5v16"></path></svg>',
    "again": '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"></path><path d="M3 4v5h5"></path></svg>',
    "slower": '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>',
    "pause": '<svg width="34%" height="34%" viewBox="0 0 24 24" fill="none" stroke="#C2410C" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 6v12"></path><path d="M15 6v12"></path></svg>',
    "check": '<svg width="40%" height="40%" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"></path></svg>',
}


def _pearl(prefix: str) -> str:
    return f"""
  <div class="pearl" id="{prefix}-pearl">
    <div class="pt" id="{prefix}-pt-n" style="opacity:1;background:radial-gradient(circle at 34% 28%, #FFFFFF 0%, #F4FBFA 20%, #D4F1EC 46%, #CFE2FB 70%, #E4DEFA 100%)"></div>
    <div class="pt" id="{prefix}-pt-d" style="opacity:0;background:radial-gradient(circle at 34% 28%, #FFFFFF 0%, #F1F6FD 18%, #C6DCF6 46%, #BFD6F3 66%, #DCD9F7 100%)"></div>
    <div class="pt" id="{prefix}-pt-p" style="opacity:0;background:radial-gradient(circle at 34% 28%, #FFFFFF 0%, #F2FBF8 18%, #BFEBDF 46%, #C9EDE6 66%, #D9E9FA 100%)"></div>
    <div class="pt" id="{prefix}-pt-h" style="opacity:0;background:radial-gradient(circle at 34% 28%, #FFFFFF 0%, #FBF7F4 22%, #F1DFD2 55%, #EBDDE0 100%)"></div>
    <div class="iri" id="{prefix}-iri" style="transition:opacity .8s"></div>
    <div class="gloss"></div>
    <div class="pt" id="{prefix}-pause" style="opacity:0;display:flex;align-items:center;justify-content:center;transition:opacity .5s">{SVG['pause']}</div>
    <div class="pt" id="{prefix}-check" style="opacity:0;display:flex;align-items:center;justify-content:center;transition:opacity .5s">{SVG['check']}</div>
  </div>"""


def _glow(prefix: str) -> str:
    g = [("n", "#E8F4F2", "232,244,242"), ("d", "#E4EEFB", "228,238,251"), ("p", "#E1F3ED", "225,243,237"), ("h", "#FBEBDF", "251,235,223")]
    return "".join(
        f'<div class="tl" id="{prefix}-gl-{k}" style="transition:opacity .9s;opacity:{1 if k == "n" else 0};'
        f'background:radial-gradient(closest-side, {c} 0%, rgba({rgb},.55) 45%, rgba(251,252,252,0) 100%)"></div>'
        for k, c, rgb in g)


WORDMARK = ('<span style="font-family:\'Reem Kufi\',sans-serif;font-size:28px;font-weight:500">بيان</span>'
            '<span style="font-size:15px;color:#5B6B69">Bayan</span>')


def gate_html(error: str = "") -> str:
    err = ("That code did not work. Please try again." if error else "")
    return f"""
<div class="bz-frame" id="bz-gate">
  <div style="position:absolute;z-index:1;left:calc(-270px + var(--ox, 0px));top:calc(-120px + var(--oy, 0px));width:1000px;height:1000px;pointer-events:none" aria-hidden="true">{_glow('g')}</div>
  <div style="position:absolute;left:40px;top:28px;z-index:6;display:flex;align-items:baseline;gap:10px">{WORDMARK}</div>
  <div style="position:absolute;z-index:7;left:calc(90px + var(--ox, 0px));top:calc(240px + var(--oy, 0px));width:280px;height:280px;pointer-events:none">{_pearl('g')}</div>
  <section style="position:absolute;left:calc(500px + var(--ox, 0px));top:calc(96px + var(--oy, 0px));right:calc(56px + var(--ox, 0px));bottom:calc(40px + var(--oy, 0px));z-index:3">
    <form onsubmit="return false" style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:22px;max-width:560px">
      <h1 style="font-size:36px;font-weight:600;line-height:1.2">Enter the access code</h1>
      <p style="font-size:18px;line-height:1.5;color:#5B6B69">Bayan is in private preview. The code keeps the microphone and patient data off the open web.</p>
      <input id="bz-code" type="password" autocomplete="off" aria-label="Access code" placeholder="Access code"
        style="height:64px;border-radius:18px;border:1px solid #D5DEDD;background:#FFFFFF;color:#173430;font:inherit;font-size:22px;padding:0 22px;letter-spacing:.06em;outline:none">
      <p id="bz-gate-err" role="alert" style="min-height:24px;font-size:16px;color:#C2410C">{err}</p>
      <button type="button" data-act="unlock" class="btn-dark" style="align-self:flex-start">Continue</button>
    </form>
  </section>
</div>"""


def _chip(code, native, name, lang_attr, size, extra=""):
    return (f'<button type="button" class="chip{" sel" if code == "ne" else ""}" data-act="lang" data-id="{code}">'
            f'<span class="n" lang="{lang_attr}" {extra} style="font-size:{size}px">{native}</span><span class="e">{name}</span></button>')


STAGE_HTML = f"""
<div class="bz-frame" id="bayan">
  <div id="bz-glow" aria-hidden="true">{_glow('s')}</div>
  <div id="bz-rings" aria-hidden="true"><span class="ring"></span><span class="ring r2"></span><span class="ring r3"></span></div>

  <div id="bz-wordmark">{WORDMARK}</div>

  <div id="bz-hright">
    <span id="bz-clock" style="font-size:15px;color:#5B6B69;font-variant-numeric:tabular-nums">0:00</span>
    <button type="button" data-act="end" style="height:44px;padding:0 20px;border-radius:14px;border:1px solid #D5DEDD;background:#FFFFFF;color:#173430;font-size:15px;font-weight:500">End consultation</button>
  </div>

  <div id="bz-status">
    <div id="bz-bars" aria-hidden="true" style="display:flex;align-items:center;gap:6px;height:34px;margin-bottom:14px;transition:opacity .4s;opacity:0">
      <span class="bar"></span><span class="bar b2"></span><span class="bar b3"></span><span class="bar b4"></span><span class="bar b5"></span>
    </div>
    <p id="bz-st-title" style="font-size:22px;font-weight:500">Ready</p>
    <p id="bz-st-sub" style="margin-top:6px;font-size:15px;line-height:1.5;color:#5B6B69"></p>
  </div>

  <section id="L-start">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:22px;max-width:640px">
      <h1 style="font-size:36px;font-weight:600;line-height:1.2">New consultation</h1>
      <p style="font-size:18px;line-height:1.5;color:#5B6B69">Choose the language the patient speaks. Bayan listens from here on, so nobody needs to press anything.</p>
      <div id="bz-chips" style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px">
        {_chip('ne', 'नेपाली', 'Nepali', 'ne', 20)}
        {_chip('hi', 'हिन्दी', 'Hindi', 'hi', 20)}
        {_chip('ur', 'اردو', 'Urdu', 'ur', 22, 'dir="rtl"')}
        {_chip('bn', 'বাংলা', 'Bengali', 'bn', 20)}
        {_chip('ml', 'മലയാളം', 'Malayalam', 'ml', 19)}
        {_chip('tl', 'Filipino', 'Tagalog', 'tl', 20)}
      </div>
      <div style="display:flex;align-items:center;gap:18px">
        <button type="button" data-act="start" class="btn-dark">Start consultation</button>
        <button type="button" data-act="demo" class="link">Play demo</button>
      </div>
    </div>
  </section>

  <section id="L-consent">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:18px;max-width:690px">
      <span class="lbl" style="color:#0E8A6F">Bayan is saying to the patient</span>
      <p id="bz-consent-native" dir="auto" style="line-height:1.6;font-weight:500"></p>
      <p id="bz-consent-en" style="font-size:17px;line-height:1.5;color:#5B6B69"></p>
      <div style="display:flex;gap:16px;margin-top:10px">
        <button type="button" data-act="consent_yes" style="width:230px;height:84px;border-radius:22px;border:none;background:#0E8A6F;color:#FFFFFF;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px"><span id="bz-yes" style="font-size:25px;font-weight:500"></span><span style="font-size:15px">Yes</span></button>
        <button type="button" data-act="consent_no" style="width:180px;height:84px;border-radius:22px;border:1px solid #D5DEDD;background:#FFFFFF;color:#173430;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px"><span id="bz-no" style="font-size:25px;font-weight:500"></span><span style="font-size:15px;color:#5B6B69">No</span></button>
      </div>
    </div>
  </section>

  <section id="L-idle">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:14px;max-width:640px">
      <p style="font-size:30px;font-weight:500;line-height:1.3">Bayan is listening</p>
      <p style="font-size:18px;line-height:1.5;color:#5B6B69">Speak naturally. Bayan works out who is talking and translates for both of you.</p>
    </div>
  </section>

  <section id="L-doctor">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:34px;max-width:690px">
      <div style="display:flex;flex-direction:column;gap:10px">
        <span class="lbl" style="color:#1F6FB2">You are saying</span>
        <p id="bz-doc-en" dir="auto" style="line-height:1.3;font-weight:500"></p>
      </div>
      <div style="height:1px;background:linear-gradient(90deg,#D3E2F2,rgba(211,226,242,0))"></div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <span class="lbl" style="color:#0E8A6F">Patient will hear</span>
        <p id="bz-doc-native" class="emerge" dir="auto" style="line-height:1.6;font-weight:500"></p>
      </div>
    </div>
  </section>

  <section id="L-patient">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:26px;max-width:700px">
      <div style="display:flex;flex-direction:column;gap:10px">
        <span class="lbl" style="color:#0E8A6F">Patient is saying</span>
        <p id="bz-pat-native" dir="auto" style="line-height:1.65;font-weight:500;transition:font-size .55s"></p>
      </div>
      <div style="height:1px;background:linear-gradient(90deg,#CFE7E1,rgba(207,231,225,0))"></div>
      <div style="display:flex;flex-direction:column;gap:10px">
        <span class="lbl" style="color:#1F6FB2">For you, in English</span>
        <p id="bz-pat-en" class="emerge" lang="en" style="line-height:1.35;font-weight:500;transition:font-size .55s"></p>
        <p id="bz-pat-note" style="margin-top:4px;display:none;align-items:flex-start;gap:10px;font-size:16px;line-height:1.5;color:#4A3A78">{SVG['book']}<span id="bz-pat-note-t"></span></p>
      </div>
    </div>
  </section>

  <button type="button" id="bz-notebtn" data-act="notes" aria-label="Notes and suggestions">
    {SVG['note']}
    <span id="bz-badge" style="position:absolute;top:-4px;right:-4px;min-width:24px;height:24px;padding:0 6px;border-radius:999px;border:2px solid #FFFFFF;background:#0E8A6F;color:#FFFFFF;font-size:12px;font-weight:600;align-items:center;justify-content:center;display:none"></span>
  </button>

  <aside id="bz-panel" aria-label="Notes and suggestions">
    <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 12px 12px 22px;border-bottom:1px solid #EEF3F3">
      <span style="font-size:17px;font-weight:600;color:#173430">Notes</span>
      <button type="button" data-act="notes-close" aria-label="Close notes" style="width:44px;height:44px;border-radius:50%;border:none;background:transparent;display:flex;align-items:center;justify-content:center">{SVG['close']}</button>
    </div>
    <div style="height:calc(100% - 73px);overflow-y:auto">
      <div style="padding:18px 22px 10px;display:flex;flex-direction:column;gap:12px">
        <span style="font-size:13px;color:#5B6B69">Noted in this visit</span>
        <div id="bz-noted" style="display:flex;flex-direction:column;gap:12px"></div>
      </div>
      <div id="bz-sugsec" style="display:none">
        <div style="height:1px;margin:8px 22px 0;background:#EEF3F3"></div>
        <span style="display:block;padding:18px 22px 0;font-size:13px;color:#5B6B69">Suggestions</span>
        <div id="bz-suglist"></div>
      </div>
    </div>
  </aside>

  <section id="L-held">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:26px;max-width:700px">
      <h2 id="bz-held-h" style="font-size:30px;line-height:1.3;font-weight:600"></h2>
      <div style="display:flex;flex-direction:column;gap:14px">
        <p style="font-size:19px;line-height:1.5;color:#173430"><span style="font-weight:600">Patient: </span><span id="bz-held-pq"></span></p>
        <p style="font-size:19px;line-height:1.5;color:#173430"><span style="font-weight:600">You: </span><span id="bz-held-dq"></span></p>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <button type="button" data-act="held_else" style="height:58px;padding:0 24px;border-radius:16px;border:none;background:#173430;color:#FFFFFF;font-size:17px;font-weight:500">Say something else</button>
        <button type="button" data-act="held_anyway" style="height:58px;padding:0 22px;border-radius:16px;border:1px solid #D5DEDD;background:#FFFFFF;color:#173430;font-size:17px">Speak it anyway</button>
      </div>
    </div>
  </section>

  <section id="L-wrap">
    <div style="height:100%;display:flex;flex-direction:column;justify-content:center;gap:28px;max-width:640px">
      <p style="font-size:38px;line-height:1.3;font-weight:500">Consultation ended</p>
      <div id="bz-steps" style="display:flex;flex-direction:column;gap:16px;font-size:18px"></div>
    </div>
  </section>

  <section id="L-revLeft">
    <label for="careplan" style="font-size:20px;font-weight:600">Patient’s care plan</label>
    <p id="bz-warn" style="display:none;font-size:16px;line-height:1.45;color:#C2410C"></p>
    <div style="flex:1;min-height:0;border-radius:26px;background:#FFFFFF;border:1px solid #E3EAE9;padding:24px 26px;display:flex">
      <textarea id="careplan" spellcheck="false" placeholder="Write the plan for the patient here." style="flex:1;resize:none;border:none;padding:0;font-family:inherit;font-size:17px;line-height:1.7;color:#173430;background:transparent"></textarea>
    </div>
  </section>

  <section id="L-revRight">
    <div style="height:100%;display:flex;flex-direction:column;align-items:center;padding:40px 44px 40px">
      <div style="align-self:stretch;height:48px;display:flex;align-items:center;padding-left:62px">
        <p id="bz-rev-title" style="font-size:18px;font-weight:600">For the patient</p>
      </div>
      <div style="flex:1;display:flex;align-items:center;justify-content:center">
        <div style="padding:22px;border-radius:26px;background:#FFFFFF"><div id="bz-qr" role="img" aria-label="QR code to open the care plan" style="width:232px;height:232px"></div></div>
      </div>
      <button type="button" id="bz-approve" data-act="approve" style="align-self:stretch;height:60px;border-radius:18px;border:none;background:#0E8A6F;color:#FFFFFF;font-size:17px;font-weight:500;transition:background .5s">Approve and send</button>
      <button type="button" id="bz-new" data-act="new" style="align-self:stretch;margin-top:12px;height:52px;border-radius:16px;border:1px solid #BFE3D8;background:#FFFFFF;color:#0B6E59;font-size:16px;font-weight:500;transition:opacity .5s;opacity:0;pointer-events:none">Start a new consultation</button>
    </div>
  </section>

  <section id="L-caption">
    <div style="position:absolute;left:146px;top:36px">
      <p style="font-size:18px;font-weight:500;color:#0E8A6F">Speaking to the patient</p>
      <p id="bz-cap-in" dir="auto" style="margin-top:2px;font-size:15px;color:#5B6B69"></p>
    </div>
    <div style="position:absolute;left:96px;right:96px;top:130px;bottom:150px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px">
      <p id="bz-cap-native" dir="auto" style="text-align:center;line-height:1.55;font-weight:600"></p>
      <p id="bz-cap-en" lang="en" style="max-width:820px;text-align:center;font-size:20px;line-height:1.5;color:#5B6B69"></p>
    </div>
    <div style="position:absolute;left:0;right:0;bottom:48px;display:flex;justify-content:center;gap:16px">
      <button type="button" class="pill" data-act="again">{SVG['again']}<span id="bz-again" style="font-size:20px"></span><span style="font-size:15px;color:#5B6B69">Say it again</span></button>
      <button type="button" class="pill" data-act="slower">{SVG['slower']}<span id="bz-slower" style="font-size:20px"></span><span style="font-size:15px;color:#5B6B69">Slower</span></button>
    </div>
  </section>

  <div id="bz-pearl-wrap">{_pearl('s')}</div>
  <div id="bz-toast" role="status" style="position:absolute;left:50%;bottom:28px;z-index:9;transform:translateX(-50%);max-width:640px;padding:12px 20px;border-radius:999px;background:#FFF4EC;color:#9A3412;font-size:15px;opacity:0;transition:opacity .4s;pointer-events:none"></div>
  <button type="button" id="bz-send" data-act="__send" hidden aria-hidden="true" tabindex="-1"></button>
</div>"""


JS = r"""
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
    check: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0E8A6F" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="m5 12.5 4.5 4.5L19 7.5"></path></svg>'
  };
  const $ = (id) => document.getElementById(id);
  let V = null, lastS = '', appliedEl = null, selLang = 'ne', panelOpen = false, hearing = false;
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
    if (act === 'start') { p.lang = selLang; startMic(); }
    if (act === 'demo') { p.lang = 'ne'; }
    if (act === 'end' || act === 'consent_no' || act === 'new') stopMic();
    if (act === 'approve') { if (V && V.screen !== 'review') { window.__bayanAct = ''; return; } p.text = ($('careplan') || {}).value || ''; }
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
      if (n.kind === 'held' || n.kind === 'override') d.style.color = '#9A3412';
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
    if (r.plan_id && r.plan_id !== planKey) { planKey = r.plan_id; $('careplan').value = r.plan_en || ''; $('bz-qr').innerHTML = r.qr || ''; }
    $('careplan').readOnly = done;
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
"""

HEAD = (f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{FONTS}"><meta name="robots" content="noindex">'
        f'<style>{CSS}</style><script>{JS}</script>')
