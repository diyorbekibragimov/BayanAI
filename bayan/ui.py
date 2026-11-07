"""Bayan stage: static markup + CSS + a client-side renderer (ported from the approved prototype).

The server never re-renders this markup. It pushes a JSON view into a hidden gr.HTML
(`.bz-s[data-s]`); the head script watches for it and updates styles/text in place, so every
CSS transition from the prototype still plays. Text is always set with textContent (no HTML
injection). Buttons carry data-act; a capture-phase click listener records the action, and the
gr.HTML click event sends it to Python through a hidden textbox (see app.py).

The markup, CSS, JavaScript and icons live in bayan/web/ (templates/, static/); this module holds the doctor-facing
string table (English / Arabic) and assembles the files:
  templates/head.html   <head> extras: fonts, static/css/duet.css, static/js/stage.js (inlined, STRINGS injected)
  templates/stage.html  every stage screen (start ... sent)
  templates/pearl.html  the pearl                   templates/glow.html   its glow layers
  templates/chip.html   a language chip             templates/wordmark.html (the home button's content)
  static/img/*.svg      inline icons                static/js/stage_inputs.js  the gr.HTML click -> inputs bridge
"""

import json

from .langs import MORE
from .web import fill, read

# ------------------------------------------------------------------ UI strings (doctor-facing), one table
# The doctor chooses English or Arabic on the start screen; the whole interface follows (RTL for Arabic).
# Patient-language text never comes from here. Python (consult.py) and the page (JS) both read this table.
STRINGS = {
    "en": {
        "start_title": "New consultation", "start_sub": "Choose the language the patient speaks.",
        "start_btn": "Start consultation", "end_btn": "End consultation",
        "consent_label": "Bayan is saying to the patient",
        "consent_doc": "Hello, I am Bayan. I translate between you and the doctor. Your voice is processed to translate it and is not stored. Do you consent?",
        "yes": "Yes", "no": "No",
        "idle_title": "Ready when you are",
        "idle_sub": "Tap the pearl and speak, then tap it again. Bayan works out who is talking and translates for both of you. The space bar works too.",
        "you_say": "You are saying", "will_hear": "Patient will hear", "pat_say": "Patient is saying", "for_you": "For you, in English",
        "notes": "Notes", "notes_aria": "Notes and suggestions", "close_notes": "Close notes", "noted": "Noted in this visit",
        "notes_empty": "Allergies, medicines and tests show here as they come up.", "suggestions": "Suggestions",
        "ask_next": "Ask next", "ask_btn": "Ask the patient in {lang}",
        "held_patient": "Patient: ", "held_you": "You: ", "held_else": "Say something else", "held_anyway": "Speak it anyway",
        "wrap_title": "Consultation ended", "step_plan": "Care plan, in {lang}", "step_safety": "Checking the plan against the safety rules",
        "rev_label": "Patient’s care plan", "rev_placeholder": "Write the plan for the patient here.",
        "for_patient": "For the patient", "sent_title": "Sent to the patient", "approve": "Approve and send", "sending": "Sending…",
        "sent": "Sent", "new": "Start a new consultation", "qr_aria": "QR code to open the care plan",
        "cap_title": "Speaking to the patient", "again": "Say it again", "slower": "Slower",
        "tap_aria": "Tap to speak", "tap_done_aria": "Tap when done", "doclang_aria": "Doctor’s language",
        "st_ready": "Ready", "st_speaking_patient": "Speaking to the patient", "st_consent": "Asking for consent",
        "st_writing": "Writing it up", "st_writing_sub": "This takes a few seconds.", "st_held": "Sentence held",
        "st_translating": "Translating…", "st_speaking_you": "Speaking to you", "st_tap": "Tap the pearl to speak",
        "st_or": "{a} or {b}", "st_listening": "Listening… tap when done",
        "not_caught": "I didn’t catch that. Tap and try again.",
        "mic_denied": "Bayan cannot use the microphone. Allow it in the browser, then tap again.",
        "err_voice_service": "Voice service is offline or starting. Please try again in a minute.",
        "err_translate": "Could not translate that. Please say it again.",
        "err_process": "Bayan could not process that. Please tap and say it again.",
        "err_voice_off": "Voice is offline. Showing text only.",
        "voice_unavailable": "Voice unavailable for that sentence. Showing the text only.",
        "cap_novoice": "Voice unavailable · text only",
        "err_lang": "Choose the patient’s language first.",
        "err_plan": "Could not write the plan. Please write it here.",
        "err_ask": "Could not translate that question.", "err_demo": "The demo hit a problem. Please try again.",
        "lang_en": "English", "lang_ar": "Arabic", "lang_ne": "Nepali", "lang_hi": "Hindi", "lang_ur": "Urdu",
        "lang_bn": "Bengali", "lang_ml": "Malayalam", "lang_tl": "Filipino", "chip_tl": "Tagalog",
        "lang_ta": "Tamil", "lang_sw": "Swahili", "lang_ko": "Korean",
        "report_pdf": "Download report (PDF)", "send_anyway": "Send anyway",
        "more": "More…", "more_count": "+{n} languages", "more_search": "Search",
        "more_close": "Close", "more_none": "No language matches.",
        "home_aria": "Go to home", "home_q": "End this consultation and start over?", "home_yes": "Start over", "home_no": "Keep going",
        "spk_aria": "Who is speaking", "spk_doctor": "Doctor", "spk_patient": "Patient",
        "turn_doc": "Your turn", "turn_pat": "Patient’s turn",
        "cf_q_patient": "That sounded like the patient. Translate it as the patient?",
        "cf_q_doctor": "That sounded like you. Translate it as the doctor?",
        "cf_yes_patient": "Yes, patient", "cf_keep_doctor": "No, keep doctor",
        "cf_yes_doctor": "Yes, doctor", "cf_keep_patient": "No, keep patient",
    },
    "ar": {
        "start_title": "استشارة جديدة", "start_sub": "اختر اللغة التي يتحدث بها المريض.",
        "start_btn": "بدء الاستشارة", "end_btn": "إنهاء الاستشارة",
        "consent_label": "يقول بيان للمريض",
        "consent_doc": "مرحبًا، أنا بيان. أترجم بينك وبين الطبيب. تتم معالجة صوتك لترجمته فقط ولا يُحفظ. هل تمنح موافقتك؟",
        "yes": "نعم", "no": "لا",
        "idle_title": "جاهز متى شئت",
        "idle_sub": "اضغط على اللؤلؤة وتحدّث، ثم اضغط عليها مرة أخرى. يتعرّف بيان على المتحدّث ويترجم لكليكما. ويمكنك أيضًا استخدام مفتاح المسافة.",
        "you_say": "أنت تقول", "will_hear": "سيسمع المريض", "pat_say": "يقول المريض", "for_you": "لك، بالعربية",
        "notes": "الملاحظات", "notes_aria": "الملاحظات والاقتراحات", "close_notes": "إغلاق الملاحظات", "noted": "دُوِّن في هذه الزيارة",
        "notes_empty": "تظهر هنا الحساسية والأدوية والفحوصات فور ذكرها.", "suggestions": "اقتراحات",
        "ask_next": "السؤال التالي", "ask_btn": "اسأل المريض باللغة {lang}",
        "held_patient": "المريض: ", "held_you": "أنت: ", "held_else": "قل شيئًا آخر", "held_anyway": "انطقها رغم ذلك",
        "wrap_title": "انتهت الاستشارة", "step_plan": "خطة الرعاية باللغة {lang}", "step_safety": "مراجعة الخطة وفق قواعد السلامة",
        "rev_label": "خطة رعاية المريض", "rev_placeholder": "اكتب خطة المريض هنا.",
        "for_patient": "للمريض", "sent_title": "أُرسلت إلى المريض", "approve": "اعتماد وإرسال", "sending": "جارٍ الإرسال…",
        "sent": "أُرسلت", "new": "بدء استشارة جديدة", "qr_aria": "رمز QR لفتح خطة الرعاية",
        "cap_title": "يتحدث إلى المريض", "again": "أعِد القول", "slower": "أبطأ",
        "tap_aria": "اضغط للتحدث", "tap_done_aria": "اضغط عند الانتهاء", "doclang_aria": "لغة الطبيب",
        "st_ready": "جاهز", "st_speaking_patient": "يتحدث إلى المريض", "st_consent": "طلب الموافقة",
        "st_writing": "جارٍ إعداد الخطة", "st_writing_sub": "يستغرق ذلك بضع ثوانٍ.", "st_held": "أُوقفت الجملة",
        "st_translating": "جارٍ الترجمة…", "st_speaking_you": "يتحدث إليك", "st_tap": "اضغط على اللؤلؤة للتحدث",
        "st_or": "{a} أو {b}", "st_listening": "أستمع… اضغط عند الانتهاء",
        "not_caught": "لم أفهم ذلك. اضغط وحاول مرة أخرى.",
        "mic_denied": "لا يستطيع بيان استخدام الميكروفون. اسمح به في المتصفح ثم اضغط مرة أخرى.",
        "err_voice_service": "خدمة الصوت غير متاحة حاليًا أو قيد التشغيل. يُرجى المحاولة بعد دقيقة.",
        "err_translate": "تعذّرت الترجمة. يُرجى إعادة الجملة.",
        "err_process": "تعذّر على بيان معالجة ذلك. اضغط وأعد الجملة.",
        "err_voice_off": "الصوت غير متاح. يُعرض النص فقط.",
        "voice_unavailable": "الصوت غير متاح لهذه الجملة. يُعرض النص فقط.",
        "cap_novoice": "الصوت غير متاح · نص فقط",
        "err_lang": "اختر لغة المريض أولًا.",
        "err_plan": "تعذّرت كتابة الخطة. يُرجى كتابتها هنا.",
        "err_ask": "تعذّرت ترجمة السؤال.", "err_demo": "واجه العرض التوضيحي مشكلة. يُرجى المحاولة مرة أخرى.",
        "lang_en": "الإنجليزية", "lang_ar": "العربية", "lang_ne": "النيبالية", "lang_hi": "الهندية", "lang_ur": "الأردية",
        "lang_bn": "البنغالية", "lang_ml": "المالايالامية", "lang_tl": "الفلبينية", "chip_tl": "التاغالوغية",
        "lang_ta": "التاميلية", "lang_sw": "السواحيلية", "lang_ko": "الكورية",
        "report_pdf": "تنزيل التقرير (PDF)", "send_anyway": "أرسل رغم ذلك",
        "more": "المزيد…", "more_count": "+{n} لغة", "more_search": "بحث",
        "more_close": "إغلاق", "more_none": "لا توجد لغة مطابقة.",
        "home_aria": "العودة إلى الصفحة الرئيسية", "home_q": "هل تريد إنهاء هذه الاستشارة والبدء من جديد؟",
        "home_yes": "البدء من جديد", "home_no": "متابعة",
        "spk_aria": "من المتحدث", "spk_doctor": "الطبيب", "spk_patient": "المريض",
        "turn_doc": "دورك", "turn_pat": "دور المريض",
        "cf_q_patient": "بدا هذا كلام المريض. هل أترجمه على أنه كلام المريض؟",
        "cf_q_doctor": "بدا هذا كلامك. هل أترجمه على أنه كلام الطبيب؟",
        "cf_yes_patient": "نعم، المريض", "cf_keep_doctor": "لا، أبقِه للطبيب",
        "cf_yes_doctor": "نعم، الطبيب", "cf_keep_patient": "لا، أبقِه للمريض",
    },
}


for _code, _v in MORE.items():  # names of the "More…" languages in both UI languages
    STRINGS["en"][f"lang_{_code}"], STRINGS["ar"][f"lang_{_code}"] = _v["en"], _v["ar"]


def t(ui_lang: str, key: str, **kw) -> str:
    """Look up a UI string (falls back to English, then to the key)."""
    out = STRINGS.get(ui_lang, STRINGS["en"]).get(key) or STRINGS["en"].get(key) or key
    return out.format(**kw) if kw else out


CSS = read("static/css/duet.css")
JS = read("static/js/stage.js")
SVG = {k: read(f"static/img/{k}.svg") for k in ("note", "close", "book", "again", "slower", "pause", "check")}
WORDMARK = read("templates/wordmark.html")
STAGE_INPUTS_JS = read("static/js/stage_inputs.js")   # stage.click js=: the recorded action (one-shot), sid

_PEARL = read("templates/pearl.html")
_GLOW = read("templates/glow.html")
_CHIP = read("templates/chip.html")
_STAGE = read("templates/stage.html")
_HEAD = read("templates/head.html")

# Patient languages on the start screen, by Qatar population: (code, native, English, lang attr, font px, extra)
CHIPS = [
    ("ne", "नेपाली", "Nepali", "ne", 20, ""),
    ("ml", "മലയാളം", "Malayalam", "ml", 18, ""),
    ("bn", "বাংলা", "Bengali", "bn", 20, ""),
    ("hi", "हिन्दी", "Hindi", "hi", 20, ""),
    ("ur", "اردو", "Urdu", "ur", 22, 'dir="rtl"'),
]  # 2 x 3 grid: these five + "More…" (SHEET below) as the sixth chip

# The "More…" sheet: Filipino, Tamil and Swahili first (large groups in Qatar, with their own GPU/MMS voices and
# consent lines in consult), then bayan/langs.MORE (Supertonic languages, incl. Korean). Display names only here.
SHEET = {
    "tl": {"en": "Filipino", "ar": "الفلبينية", "native": "Tagalog"},
    "ta": {"en": "Tamil", "ar": "التاميلية", "native": "தமிழ்"},
    "sw": {"en": "Swahili", "ar": "السواحيلية", "native": "Kiswahili"},
    **MORE,
}


def _pearl(prefix: str) -> str:
    return fill(_PEARL, prefix=prefix, svg_pause=SVG["pause"], svg_check=SVG["check"])


def _glow(prefix: str) -> str:
    return fill(_GLOW, prefix=prefix)


def _chip(code, native, name, lang_attr, size, extra=""):
    return fill(_CHIP, sel=" sel" if code == "ne" else "", code=code, native=native, name=name, lang_attr=lang_attr,
                size=size, extra=extra, tkey="chip_tl" if code == "tl" else f"lang_{code}")


STAGE_HTML = fill(
    _STAGE, glow=_glow("s"), wordmark=WORDMARK, pearl=_pearl("s"),
    chips="\n        ".join(_chip(*c) for c in CHIPS) + "\n        " + fill(read("templates/more_chip.html"), more_count=len(SHEET)),
    **{f"svg_{k}": SVG[k] for k in ("note", "close", "book", "again", "slower")},
)

HEAD = fill(_HEAD, css=CSS, js=JS.replace("__STRINGS__", json.dumps(STRINGS, ensure_ascii=False))
            .replace("__LANGS_MORE__", json.dumps(SHEET, ensure_ascii=False)))
