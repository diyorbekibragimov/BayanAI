"""Bayan AI · patient and doctor outputs: PDF care plan, doctor report, WhatsApp / SMS links, care-plan audio.

LABELS holds the fixed patient-sheet wording per language (headings, times of day, footer). Plain, short and
literal; machine drafts for a native speaker to verify, like every other patient-facing string in the demo.
"""

from __future__ import annotations

LANG_NAMES = {
    "en": "English", "ar": "Arabic", "ne": "Nepali", "hi": "Hindi", "ur": "Urdu", "bn": "Bengali",
    "ml": "Malayalam", "tl": "Filipino (Tagalog)", "ta": "Tamil", "te": "Telugu", "sw": "Swahili",
    "ko": "Korean", "ja": "Japanese", "es": "Spanish", "fr": "French", "pt": "Portuguese", "id": "Indonesian",
    "tr": "Turkish", "vi": "Vietnamese", "ru": "Russian", "uk": "Ukrainian", "de": "German", "it": "Italian",
    "nl": "Dutch", "pl": "Polish", "ro": "Romanian", "el": "Greek", "cs": "Czech", "sk": "Slovak",
    "hu": "Hungarian", "bg": "Bulgarian", "hr": "Croatian", "sl": "Slovenian", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "et": "Estonian", "lv": "Latvian", "lt": "Lithuanian",
}

EN_LABELS = {
    "title": "Your medicines and care instructions",
    "medicines": "Your medicines",
    "medicine": "Medicine",
    "morning": "Morning", "noon": "Noon", "evening": "Evening", "bedtime": "Bedtime",
    "duration": "For how long",
    "days": "days",
    "avoid": "Do not take",
    "other": "Other instructions",
    "red_flags": "Call 999 or come back now if",
    "emergency": "In an emergency, call 999.",
    "scan": "Scan to listen",
    "footer": "Translated by machine from your doctor's words. If anything is unclear, ask a nurse or doctor.",
    "date": "Date",
    "language": "English",
    "wake": "When you wake up",
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "bedtime": "Bedtime",
    "how_long": "How long",
    "prn": "Only when needed",
    "schedule": "Daily schedule",
}

LABELS: dict[str, dict[str, str]] = {
    "ne": {
        "title": "तपाईंको औषधि र हेरचाह निर्देशन",
        "medicines": "तपाईंको औषधि",
        "medicine": "औषधि",
        "morning": "बिहान", "noon": "दिउँसो", "evening": "बेलुका", "bedtime": "सुत्ने बेला",
        "duration": "कति दिन",
        "days": "दिन",
        "avoid": "नखानुहोस्",
        "other": "अन्य निर्देशन",
        "red_flags": "यस्तो भए 999 मा फोन गर्नुहोस् वा तुरुन्त फर्कनुहोस्",
        "scan": "सुन्न स्क्यान गर्नुहोस्",
        "footer": "तपाईंको डाक्टरको कुरा मेसिनले अनुवाद गरेको हो। केही नबुझिए नर्स वा डाक्टरलाई सोध्नुहोस्।",
        "date": "मिति",
        "language": "नेपाली",
        "wake": "उठ्ने बित्तिकै",
        "breakfast": "बिहानको खाना",
        "lunch": "दिउँसोको खाना",
        "dinner": "बेलुकाको खाना",
        "bedtime": "सुत्ने बेला",
        "how_long": "कति दिन",
        "prn": "चाहिएको बेला मात्र",
        "schedule": "दैनिक तालिका",
    },
    "hi": {
        "title": "आपकी दवाइयाँ और देखभाल के निर्देश",
        "medicines": "आपकी दवाइयाँ",
        "medicine": "दवा",
        "morning": "सुबह", "noon": "दोपहर", "evening": "शाम", "bedtime": "सोते समय",
        "duration": "कितने दिन",
        "days": "दिन",
        "avoid": "न लें",
        "other": "अन्य निर्देश",
        "red_flags": "ऐसा हो तो 999 पर फ़ोन करें या तुरंत वापस आएँ",
        "scan": "सुनने के लिए स्कैन करें",
        "footer": "आपके डॉक्टर की बातों का मशीन से अनुवाद किया गया है। कुछ समझ न आए तो नर्स या डॉक्टर से पूछें।",
        "date": "तारीख",
        "language": "हिन्दी",
        "wake": "उठते ही",
        "breakfast": "नाश्ता",
        "lunch": "दोपहर का खाना",
        "dinner": "रात का खाना",
        "bedtime": "सोते समय",
        "how_long": "कितने दिन",
        "prn": "सिर्फ़ ज़रूरत पड़ने पर",
        "schedule": "रोज़ की समय सारणी",
    },
    "bn": {
        "title": "আপনার ওষুধ ও যত্নের নির্দেশনা",
        "medicines": "আপনার ওষুধ",
        "medicine": "ওষুধ",
        "morning": "সকাল", "noon": "দুপুর", "evening": "সন্ধ্যা", "bedtime": "ঘুমানোর আগে",
        "duration": "কত দিন",
        "days": "দিন",
        "avoid": "খাবেন না",
        "other": "অন্যান্য নির্দেশনা",
        "red_flags": "এমন হলে 999-এ ফোন করুন বা সঙ্গে সঙ্গে ফিরে আসুন",
        "scan": "শুনতে স্ক্যান করুন",
        "footer": "আপনার ডাক্তারের কথা মেশিনে অনুবাদ করা। কিছু বুঝতে না পারলে নার্স বা ডাক্তারকে জিজ্ঞেস করুন।",
        "date": "তারিখ",
        "language": "বাংলা",
        "wake": "ঘুম থেকে উঠে",
        "breakfast": "সকালের খাবার",
        "lunch": "দুপুরের খাবার",
        "dinner": "রাতের খাবার",
        "bedtime": "ঘুমানোর আগে",
        "how_long": "কত দিন",
        "prn": "শুধু দরকার হলে",
        "schedule": "দৈনিক সময়সূচি",
    },
    "ml": {
        "title": "നിങ്ങളുടെ മരുന്നുകളും പരിചരണ നിർദ്ദേശങ്ങളും",
        "medicines": "നിങ്ങളുടെ മരുന്നുകൾ",
        "medicine": "മരുന്ന്",
        "morning": "രാവിലെ", "noon": "ഉച്ച", "evening": "വൈകിട്ട്", "bedtime": "ഉറങ്ങുമ്പോൾ",
        "duration": "എത്ര ദിവസം",
        "days": "ദിവസം",
        "avoid": "കഴിക്കരുത്",
        "other": "മറ്റ് നിർദ്ദേശങ്ങൾ",
        "red_flags": "ഇങ്ങനെ വന്നാൽ 999 വിളിക്കുക അല്ലെങ്കിൽ ഉടൻ തിരികെ വരിക",
        "scan": "കേൾക്കാൻ സ്കാൻ ചെയ്യുക",
        "footer": "നിങ്ങളുടെ ഡോക്ടറുടെ വാക്കുകൾ യന്ത്രം വിവർത്തനം ചെയ്തതാണ്. സംശയമുണ്ടെങ്കിൽ നഴ്സിനോടോ "
                  "ഡോക്ടറോടോ ചോദിക്കുക.",
        "date": "തീയതി",
        "language": "മലയാളം",
        "wake": "ഉണർന്നയുടൻ",
        "breakfast": "പ്രാതൽ",
        "lunch": "ഉച്ചഭക്ഷണം",
        "dinner": "അത്താഴം",
        "bedtime": "ഉറങ്ങുമ്പോൾ",
        "how_long": "എത്ര ദിവസം",
        "prn": "ആവശ്യമുള്ളപ്പോൾ മാത്രം",
        "schedule": "ദിവസേനയുള്ള സമയക്രമം",
    },
    "ur": {
        "title": "آپ کی دوائیں اور دیکھ بھال کی ہدایات",
        "medicines": "آپ کی دوائیں",
        "medicine": "دوا",
        "morning": "صبح", "noon": "دوپہر", "evening": "شام", "bedtime": "سوتے وقت",
        "duration": "کتنے دن",
        "days": "دن",
        "avoid": "نہ لیں",
        "other": "دیگر ہدایات",
        "red_flags": "ایسا ہو تو 999 پر فون کریں یا فوراً واپس آئیں",
        "scan": "سننے کے لیے اسکین کریں",
        "footer": "آپ کے ڈاکٹر کی باتوں کا مشینی ترجمہ کیا گیا ہے۔ کوئی بات سمجھ نہ آئے تو نرس یا ڈاکٹر سے پوچھیں۔",
        "date": "تاریخ",
        "language": "اردو",
        "wake": "جاگتے ہی",
        "breakfast": "ناشتہ",
        "lunch": "دوپہر کا کھانا",
        "dinner": "رات کا کھانا",
        "bedtime": "سوتے وقت",
        "how_long": "کتنے دن",
        "prn": "صرف ضرورت پڑنے پر",
        "schedule": "روزانہ کا شیڈول",
    },
    "ar": {
        "title": "أدويتك وتعليمات الرعاية",
        "medicines": "أدويتك",
        "medicine": "الدواء",
        "morning": "الصباح", "noon": "الظهر", "evening": "المساء", "bedtime": "قبل النوم",
        "duration": "لكم يوم",
        "days": "أيام",
        "avoid": "لا تتناول",
        "other": "تعليمات أخرى",
        "red_flags": "اتصل بالرقم 999 أو عد فورًا إذا",
        "scan": "امسح للاستماع",
        "footer": "تُرجم كلام طبيبك آليًا. إذا كان أي شيء غير واضح، اسأل الممرض أو الطبيب.",
        "date": "التاريخ",
        "language": "العربية",
        "wake": "عند الاستيقاظ",
        "breakfast": "الفطور",
        "lunch": "الغداء",
        "dinner": "العشاء",
        "bedtime": "قبل النوم",
        "how_long": "المدة",
        "prn": "عند الحاجة فقط",
        "schedule": "الجدول اليومي",
    },
}

RTL_LANGS = {"ar", "ur", "fa", "ps"}


# Machine-drafted sheet labels for the other languages (data/sheet_labels.json, generated once with gpt-oss-120b,
# checked for 999/digits; a native speaker should still review them, like every patient-facing string).
try:
    import json as _json
    from pathlib import Path as _Path

    _EXTRA = _json.loads((_Path(__file__).resolve().parents[2] / "data" / "sheet_labels.json").read_text("utf-8"))
except (OSError, ValueError):
    _EXTRA = {}


def labels(lang: str) -> dict[str, str]:
    """Native labels for a language (English for any missing key or unknown language)."""
    return {**EN_LABELS, **_EXTRA.get(lang, {}), **LABELS.get(lang, {})}
