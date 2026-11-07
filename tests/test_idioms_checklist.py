"""Idiom index (deterministic matching) and presenting-complaint checklists."""

from __future__ import annotations

import pytest

from bayan.brain.checklist import QUESTION_TOPICS, checklist
from bayan.brain.idioms import IdiomIndex
from bayan.brain.merge import merge_delta
from bayan.brain.rules import RuleEngine
from bayan.brain.state import Consultation, empty_state


@pytest.fixture(scope="module")
def ix() -> IdiomIndex:
    return IdiomIndex()


def hit_ids(hits):
    return [h["id"] for h in hits]


# ============================================================================ idioms
def test_golden_path_nepali_sentence_matches_npi_005(ix):
    hits = ix.match("मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ", "My chest is burning like gastric", lang="ne")
    assert hit_ids(hits) == ["npi-005"]
    h = hits[0]
    assert set(h) >= {"id", "matched", "red_flag_tags", "entry"}
    assert h["red_flag_tags"] == ["acs", "gi_bleed"] and h["entry"]["romanized"] == "gyastrik"
    assert h["matched"] == "ग्यास्ट्रिक"
    assert hit_ids(ix.match("मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ")) == ["npi-005"]   # no lang, no English


@pytest.mark.parametrize("text,lang,expected", [
    ("gyastrik", "ne", ["npi-005"]),
    ("gastric", "ne", ["npi-005"]),
    ("Gastric", "npi", ["npi-005"]),
    ("gastric", "bn", ["ben-007"]),
    ("mero chati gyastrikle jasto polyo", "ne", ["npi-005"]),
    ("kabag", None, ["tgl-002"]),
    ("kabag", "tl", ["tgl-002"]),
    ("Kinakabagan po ako", "tl", ["tgl-002"]),
    ("Pasma po ang kamay ko, nanginginig.", "tl", ["tgl-001"]),
    ("gas trouble", "ml", ["mal-001"]),
    ("Mero man bhaari chha", "ne", ["npi-002"]),
    ("मलाई टेन्सन छ", "ne", ["mul-001"]),
    ("दिल घबरा रहा है", "hi", ["hin-001"]),
    ("قلبي مقبوض", "ar", ["ara-001"]),
])
def test_matches(ix, text, lang, expected):
    assert hit_ids(ix.match(text, "", lang)) == expected


def test_english_rendering_loanword_respects_patient_language(ix):
    assert hit_ids(ix.match("...", "My chest is burning like gastric", "ne")) == ["npi-005"]
    assert hit_ids(ix.match("...", "My chest is burning like gastric", "bn")) == ["ben-007"]
    assert hit_ids(ix.match("...", "I get tension at work", "hi")) == ["mul-001"]
    # a Tagalog patient's English rendering "gas pain" must not pull in the Hindi 'gas' idiom
    hits = ix.match("May kabag po ako, masakit ang tiyan, tsaka nahihilo.", "I have gas pain, my stomach hurts, and I feel dizzy.", "tl")
    assert "tgl-002" in hit_ids(hits) and "hin-004" not in hit_ids(hits)
    assert set(hit_ids(ix.match("মাথা গরম, শরীর দুর্বল", "My head is hot, my body is weak.", "bn"))) == {"ben-003", "ben-005"}


@pytest.mark.parametrize("sentence", [
    "I work outside on a building site",
    "my throat has hurt for three days",
    "I work outside on a building site. Once, after a penicillin injection, my body swelled up. And my throat has hurt for three days.",
    "What brings you in today?",
    "It's probably a throat infection. You can go home.",
    "I have a mass in my belly and an initial test was normal",
    "My stomach hurts and I feel tired",
    "The pain is in my chest and spreads to my arm",
    "I feel hot and weak after work",
    "Take paracetamol, one gram, up to three times a day.",
])
@pytest.mark.parametrize("lang", [None, "ne", "tl", "en"])
def test_ordinary_sentences_do_not_match(ix, sentence, lang):
    assert ix.match(sentence, sentence, lang) == []


def test_english_utterance_only_matches_loanwords_of_the_patient_language(ix):
    for s in ("Mass casualty incident at the site", "I init the system", "There is a gas leak in the kitchen"):
        for lang in ("tl", "ar", "ne", "bn", "en"):
            assert ix.match(s, s, lang) == [], (s, lang)
    assert ix.match("The tension in my shoulders is bad", "", "en") == []
    assert hit_ids(ix.match("I have tension", "I have tension", "ne")) == ["mul-001"]


def test_no_duplicates_best_first_and_lookup(ix):
    hits = ix.match("gyastrik gastric gyastrikle", "gastric", None)
    ids = hit_ids(hits)
    assert len(ids) == len(set(ids)) and ids[0] == "npi-005"
    assert ix.lookup("gyastrik", "ne")["id"] == "npi-005"
    assert ix.lookup("kabag")["id"] == "tgl-002"
    assert ix.lookup("npi-002")["id"] == "npi-002"
    assert ix.lookup("the weather is nice") is None
    assert ix.get("tgl-002")["literal_en"].startswith("gas pain")
    assert ix.get("nope") is None


def test_every_entry_matches_its_own_native_or_romanized_form(ix):
    for e in ix.entries:
        lang = e["iso639_3"]
        native = e["native"].split(" / ")[0].split(" (")[0]
        assert e["id"] in hit_ids(ix.match(native, "", lang)), (e["id"], native)


# ---------------------------------------------------------------------------- lexicon schema (v0.2)
# Tags the rules and the copilot already understand; a new tag needs a rule/checklist change first.
ALLOWED_TAGS = {"acs", "arrhythmia_syncope", "ectopic_pregnancy", "gi_bleed", "heat_illness", "malaria", "metabolic",
                "neuro_psych_emergency", "postpartum", "respiratory", "sepsis_infection", "stroke", "suicidality"}
REQUIRED_KEYS = {"id", "language", "iso639_3", "native", "romanized", "literal_en", "clinical_interpretations",
                 "masks_red_flags", "clarifying_questions_en", "body_system", "source_urls", "evidence_level",
                 "red_flag_tags"}
OPTIONAL_KEYS = {"also_used_in", "notes"}


def test_lexicon_schema_ids_tags_and_sources(ix):
    import re

    ids = [e["id"] for e in ix.entries]
    assert len(ids) == len(set(ids)) and len(ids) >= 95
    levels = set(ix.meta["evidence_levels"])
    for e in ix.entries:
        assert REQUIRED_KEYS <= set(e) <= REQUIRED_KEYS | OPTIONAL_KEYS, e["id"]
        assert re.fullmatch(r"[a-z]{3}-\d{3}", e["id"]), e["id"]
        assert e["native"].strip() and e["romanized"].strip() and e["literal_en"].strip(), e["id"]
        assert set(e["red_flag_tags"]) <= ALLOWED_TAGS, (e["id"], e["red_flag_tags"])
        assert e["red_flag_tags"] == sorted(set(e["red_flag_tags"])), e["id"]
        assert e["evidence_level"] in levels, e["id"]
        assert e["source_urls"] and all(u.startswith("https://") for u in e["source_urls"]), e["id"]
        assert e["clinical_interpretations"] and all(
            i["likelihood"] in ("high", "medium", "low") and i["meaning"] for i in e["clinical_interpretations"]), e["id"]
        assert 1 <= len(e["clarifying_questions_en"]) <= 5, e["id"]
        assert e["red_flag_tags"] == [] or e["masks_red_flags"], e["id"]


def test_rule_tags_exist_in_lexicon(ix):
    """Every red_flag_tags value a safety rule matches on is carried by at least one lexicon entry."""
    import json

    from bayan.brain.vocab import RULES_PATH

    rule_tags: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("fact") == "red_flag_tags":
                v = node.get("value")
                rule_tags.update(v if isinstance(v, list) else [v])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    with open(RULES_PATH, encoding="utf-8") as f:
        walk(json.load(f))
    lex_tags = {t for e in ix.entries for t in e["red_flag_tags"]}
    assert rule_tags and rule_tags <= lex_tags <= ALLOWED_TAGS


@pytest.mark.parametrize("text,lang,expected", [
    # Nepali (Kohrt & Harper 2008)
    ("मलाई दिमाग गयो जस्तो भयो", "ne", "npi-013"),
    ("kaam pachhi dimaag gayo", "ne", "npi-013"),
    ("उसको दिमाग खराब भयो", "ne", "npi-014"),
    ("मलाई चैत लाग्यो", "ne", "npi-015"),
    # Hindi / Urdu: conjugated verb idioms match through the infinitive stem
    ("कल धूप में काम किया और लू लग गई", "hi", "hin-011"),
    ("mujhe loo lag gayi", "hi", "hin-011"),
    ("सीढ़ी चढ़ते ही साँस फूल जाती है", "hi", "hin-012"),
    ("Mera badan toot raha hai", "hi", "hin-013"),
    ("میرا بدن ٹوٹ رہا ہے", "ur", "hin-013"),
    ("biwi ke paon bhari hain", "hi", "hin-014"),
    ("मैं उम्मीद से हूँ", "hi", "hin-015"),
    ("میں امید سے ہوں", "ur", "hin-015"),
    ("सफ़ेद पानी आता है", "hi", "hin-016"),
    ("mujhe gupt rog hai", "hi", "hin-017"),
    ("bawaseer se khoon aata hai", "hi", "hin-018"),
    ("कल रात दौरा पड़ा", "hi", "hin-019"),
    ("दिल बैठा जा रहा है", "hi", "hin-020"),
    ("जी मिचला रहा है", "hi", "hin-021"),
    ("डर से हाथ पैर फूल गए", "hi", "hin-022"),
    ("आँखों के आगे अँधेरा छा गया", "hi", "hin-023"),
    # Bengali (Wahid et al. 2021 and others)
    ("ব্রেন স্ট্রোক হয়ে গেছে", "bn", "ben-009"),
    ("মাথা কাজ করে না", "bn", "ben-010"),
    ("সব কিছুতে হতাশা লাগে", "bn", "ben-011"),
    ("ওর মাথা খারাপ হয়ে গেছে", "bn", "ben-012"),
    ("আমার বুক জ্বালাপোড়া করছে", "bn", "ben-013"),
    ("buk jala korche", "bn", "ben-013"),
    ("আমাশয় হয়েছে", "bn", "ben-014"),
    # Malayalam, Tamil
    ("എനിക്ക് നെഞ്ചെരിച്ചിൽ ഉണ്ട്", "ml", "mal-003"),
    ("ഭാര്യക്ക് വിശേഷം ഉണ്ട്", "ml", "mal-004"),
    ("എനിക്ക് നെഞ്ചെരിച്ചില്‍ ഉണ്ട്", "ml", "mal-003"),    # old-style chillu (ZWJ) spelling
    ("எனக்கு மயக்கமா இருக்கு", "ta", "tam-002"),
    ("நெஞ்சில் வாய்வு வலி", "ta", "tam-003"),
    # Tagalog (Lasco et al. 2020; Gaw et al. 2011)
    ("Na-hi-highblood po ako kapag galit", "tl", "tgl-010"),
    ("Lowblood daw po ako sabi ng nurse", "tl", "tgl-011"),
    ("Tinigil ko ang maintenance ko", "tl", "tgl-012"),
    ("Namatay sa bangungot ang kuya ko", "tl", "tgl-013"),
    ("Sinusumpong po ako ng hika", "tl", "tgl-014"),
    ("Kinulam daw siya", "tl", "tgl-015"),
    # Swahili (lang 'swh'; see test_swahili_language_code below)
    ("Nina msongo wa mawazo", "swh", "swh-001"),
    ("Kichwa kimejaa mawazo", "swh", "swh-002"),
    ("Mtoto ana degedege", "swh", "swh-003"),
    ("Nina kiungulia", "swh", "swh-004"),
    ("Presha imepanda", "swh", "swh-005"),
    # Arabic
    ("عندي حموضة", "ar", "ara-014"),
    ("صار عنده ضربة شمس بالشغل", "ar", "ara-015"),
])
def test_new_entries_match_in_context(ix, text, lang, expected):
    assert hit_ids(ix.match(text, "", lang)) == [expected]
    assert hit_ids(ix.match(text, "", None))[0] == expected


@pytest.mark.parametrize("lang,sentences", [
    ("en", ["I ate rice", "Thank you doctor", "Good morning", "I have had a headache since yesterday",
            "My blood test was normal", "Please take this medicine after food", "I work in maintenance at a hotel"]),
    ("ne", ["नमस्ते डाक्टर साब", "मैले भात खाएँ", "धन्यवाद", "मलाई टाउको दुख्यो", "Namaste doctor sab", "maile bhat khae"]),
    ("hi", ["नमस्ते डॉक्टर साहब", "मैंने चावल खाया", "धन्यवाद डॉक्टर जी", "दर्द पेट से शुरू हुआ",
            "डॉक्टर साहब का दौरा कब है?", "उम्मीद है आप ठीक हैं", "maine chawal khaya", "mujhe ummeed hai aap theek hain"]),
    ("ur", ["السلام علیکم ڈاکٹر صاحب", "میں نے چاول کھائے", "شکریہ ڈاکٹر صاحب", "امید ہے آپ ٹھیک ہیں"]),
    ("bn", ["আমি ভাত খেয়েছি", "ধন্যবাদ ডাক্তার", "নমস্কার", "আসসালামু আলাইকুম", "ami bhat kheyechi"]),
    ("ml", ["ഞാൻ ചോറ് കഴിച്ചു", "നന്ദി ഡോക്ടർ", "എന്താ വിശേഷം?", "എന്തുണ്ട് വിശേഷം", "സുഖമാണോ?"]),
    ("ta", ["நான் சாப்பாடு சாப்பிட்டேன்", "நன்றி டாக்டர்", "வணக்கம்", "என் வாய் வலிக்கிறது"]),
    ("tl", ["Kumain ako ng kanin", "Salamat po doktor", "Magandang umaga po", "May ulam po kami", "Kumusta po kayo"]),
    ("swh", ["Nimekula wali", "Asante daktari", "Habari za asubuhi", "Mawazo yangu ni mazuri", "Jambo"]),
    ("ar", ["أكلت رز", "شكرا دكتور", "صباح الخير", "السلام عليكم", "عندي حرقان في البول"]),
])
def test_greetings_and_ordinary_sentences_match_nothing(ix, lang, sentences):
    """Ordinary words that overlap an idiom ('vishesham' in a greeting, 'pet se', 'ummeed', 'daura' = visit,
    'vaay' = mouth, 'ulam' = dish, 'mawazo' = ideas) must not raise an idiom card."""
    for s in sentences:
        for lg in (lang, None):
            assert ix.match(s, "", lg) == [], (s, lg)
            assert ix.match(s, s, lg) == [], (s, lg)


def test_swahili_language_code(ix):
    """Swahili entries match with lang None or the ISO code 'swh'. The app passes 'sw', which the matcher's
    _LANG table does not map yet, so romanized Swahili forms are skipped for lang='sw' (see lexicon report)."""
    assert hit_ids(ix.match("Nina kiungulia", "", "swh")) == ["swh-004"]
    assert hit_ids(ix.match("Nina kiungulia", "", None)) == ["swh-004"]
    assert ix.match("Nina kiungulia", "", "ne") == []


# ============================================================================ checklist
def _chest_state():
    c = Consultation()
    c.set_scenario_time(1.0)
    t = c.add_turn("patient", "ne", "मेरो छाती ग्यास्ट्रिकले जस्तो पोलेको छ", english="My chest is burning like gastric")
    merge_delta(c, {"symptoms": [{"code": "chest_burning", "evidence": [{"utt": t.id}]}]})
    return c


def test_checklist_empty_and_topics():
    assert checklist(empty_state()) == []
    assert {"pain_radiation", "exertional_pattern", "sweating_breathlessness"} <= set(QUESTION_TOPICS)
    assert len(QUESTION_TOPICS) == len(set(QUESTION_TOPICS))


def test_chest_pain_checklist_open_to_done():
    c = _chest_state()
    rows = checklist(c.state, 1.0)
    by = {r["id"]: r for r in rows}
    assert {"ecg_12lead", "troponin", "bp", "ask_pain_radiation", "ask_exertional_pattern",
            "ask_sweating_breathlessness"} <= set(by)
    assert all(r["group"] == "chest_pain" and r["status"] == "open" and r["closed_by"] is None for r in rows)
    assert set(rows[0]) >= {"id", "group", "label", "status", "closed_by"}
    assert by["ask_pain_radiation"]["ask_en"] and by["ecg_12lead"]["overdue"] is False
    assert checklist(c.state, 12.0)[0]["overdue"] is True

    # ECG ordered closes the ECG item (and only it)
    c.set_scenario_time(13.0)
    d = c.add_turn("doctor", "en", "We'll do a heart tracing (ECG) and a troponin.")
    merge_delta(c, {"investigations": [{"code": "ecg_12lead", "status": "ordered", "evidence": [{"utt": d.id}]}]})
    by = {r["id"]: r for r in checklist(c.state, 13.0)}
    assert by["ecg_12lead"]["status"] == "done" and "ecg_12lead ordered" in by["ecg_12lead"]["closed_by"]
    assert d.id in by["ecg_12lead"]["closed_by"]
    assert by["troponin"]["status"] == "open" and by["bp"]["status"] == "open"

    merge_delta(c, {"investigations": [{"code": "troponin_hs", "status": "ordered"}],
                    "vitals": {"bp": "128/82"},
                    "questions_asked": ["pain_radiation", "exertional_pattern", "sweating"]})
    by = {r["id"]: r for r in checklist(c.state, 14.0)}
    assert all(r["status"] == "done" for r in by.values()), by
    assert by["bp"]["closed_by"] == "BP 128/82"


def test_asked_item_closes_when_answer_already_volunteered():
    c = _chest_state()
    merge_delta(c, {"symptoms": [{"code": "jaw_arm_pain", "first_mention_min": 2.0}]})
    by = {r["id"]: r for r in checklist(c.state)}
    assert by["ask_pain_radiation"]["status"] == "done" and "jaw_arm_pain" in by["ask_pain_radiation"]["closed_by"]


def test_checklist_items_track_the_rules():
    """When every chest-pain checklist item is done, no WORK-CHEST rule fires (and vice versa for ECG)."""
    engine = RuleEngine()
    c = _chest_state()
    merge_delta(c, {"idiom_hits": [{"id": "npi-005", "utt": "u001", "t_min": 1.0}], "disposition": "discharge"})
    assert {f["rule_id"] for f in engine.evaluate(c.state, 12)} == {"WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"}
    merge_delta(c, {"investigations": ["ecg_12lead", "troponin"]})
    by = {r["id"]: r for r in checklist(c.state)}
    assert by["ecg_12lead"]["status"] == by["troponin"]["status"] == "done"
    assert engine.evaluate(c.state, 12) == []


def test_heat_and_other_groups_and_unique_ids():
    st = empty_state()
    merge_delta(st, {"patient": {"heat_exposure": True, "sex": "female", "age_years": 30},
                     "symptoms": ["confusion", "syncope", "dizziness"]})
    rows = checklist(st)
    groups = {r["group"] for r in rows}
    assert {"heat_illness", "pregnancy_check", "syncope"} <= groups and "chest_pain" not in groups
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert {"temp_core", "active_cooling", "ck", "creatinine", "electrolytes", "pregnancy_test", "ecg_12lead"} <= set(ids)
    merge_delta(st, {"investigations": [{"code": "temp_rectal", "status": "resulted"}], "interventions": ["active_cooling"],
                     "patient": {"pregnant": False}})
    by = {r["id"]: r for r in checklist(st)}
    assert by["temp_core"]["status"] == by["active_cooling"]["status"] == by["pregnancy_test"]["status"] == "done"
    assert by["ck"]["status"] == "open"
    # suicidality idiom opens the suicide-risk group
    st2 = empty_state()
    merge_delta(st2, {"idiom_hits": [{"id": "ara-007", "red_flag_tags": ["suicidality"], "utt": "u3", "t_min": 2}]})
    assert {r["id"] for r in checklist(st2)} == {"suicide_risk_assessment", "ask_suicidal_thoughts"}
