"""CardStore guardrails, grouping, dedupe, audit (no LLM, no network)."""

from __future__ import annotations

import threading

from bayan.brain.cards import CardStore
from bayan.brain.state import Consultation


def _store(consult: Consultation | None = None, groundings=("npi-005", "ask_pain_radiation", "ALG-PEN-01")):
    c = consult or Consultation()
    if not c.turns:
        c.add_turn("patient", "ne", "छाती पोलेको छ", english="My chest burns like gastric", t_min=1.0)
        c.add_turn("doctor", "en", "Any allergies?", english="Any allergies?", t_min=2.0)
    store = CardStore(grounding_check=lambda kind, g: g in groundings, turn_lookup=c.turn_by_id,
                      clock=c.now_min, state_version=lambda: c.state_version, log=c.log, audit=c.audit)
    return c, store


def _fired(rule_id, severity, key=None, family="missing_workup", utt="u001", group=None):
    return {"rule_id": rule_id, "family": family, "severity": severity, "message": f"{rule_id} message",
            "rationale": "r", "source_urls": ["https://example.org"], "fire_on": "state_change",
            "verification": "label_or_guideline_checked",
            "evidence": [{"utt": utt, "t_min": 1.0, "quote": "chest burns"}],
            "group": group, "key": key or rule_id}


def test_agent_cannot_post_critical():
    c, s = _store()
    r = s.post("missed", "No ECG", "body", [{"utt": "u001"}], "npi-005", severity="critical", source="agent")
    assert r.startswith("rejected") and "rule engine" in r
    assert s.all_cards() == []
    assert c.audit[-1]["action"] == "rejected" and c.audit[-1]["user"] == "agent"
    r = s.post("missed", "No ECG", "body", [{"utt": "u001"}], "npi-005", severity="critical", source="fallback")
    assert r.startswith("rejected")


def test_agent_needs_evidence_and_valid_grounding():
    _c, s = _store()
    assert s.post("ask", "Q?", "b", [], "npi-005", ask_text="Q?").startswith("rejected: evidence")
    assert s.post("ask", "Q?", "b", [{"utt": "u999"}], "npi-005", ask_text="Q?").startswith("rejected: evidence")
    assert s.post("ask", "Q?", "b", [{"utt": "u001"}], "ECG", ask_text="Q?").startswith("rejected: grounding")
    assert s.post("idiom", "x", "b", [{"utt": "u001"}], "npi-005").startswith("rejected: kind")
    cid = s.post("ask", "Ask about radiation", "b", ["u001"], "npi-005", ask_text="Does it spread to your arm?")
    assert cid.startswith("c")
    card = s.get(cid)
    assert card["evidence"][0]["t_min"] == 1.0 and card["evidence"][0]["quote"]
    assert card["source"] == "agent" and card["status"] == "open"


def test_observation_may_ground_on_utterance():
    _c, s = _store()
    assert s.post("observation", "Dose said twice", "500 vs 50", [{"utt": "u002"}], "u002").startswith("c")
    assert s.post("ask", "Q", "b", [{"utt": "u002"}], "u002", ask_text="Q?").startswith("rejected: grounding")


def test_ask_cap_and_dedupe():
    _c, s = _store()
    qs = ["Does the pain spread to your arm or jaw?", "Do you sweat when it comes?",
          "Does it come on when you walk or climb stairs?", "Have you had black stools?"]
    res = [s.post("ask", q, "b", [{"utt": "u001"}], "npi-005", ask_text=q, severity="info") for q in qs]
    assert all(r.startswith("c") for r in res[:3])
    assert res[3].startswith("rejected: ask-card cap")
    assert s.post("ask", qs[0], "b", [{"utt": "u001"}], "npi-005", ask_text=qs[0]) == "duplicate"
    # reworded question, same meaning -> fuzzy duplicate
    assert s.post("ask", "Does the pain spread to your arm or your jaw?", "b", [{"utt": "u001"}], "ask_pain_radiation",
                  ask_text="Does the pain spread to your arm or your jaw?") == "duplicate"


def test_dismissed_never_returns():
    _c, s = _store()
    q = "Does the pain spread to your arm or jaw?"
    cid = s.post("ask", q, "b", [{"utt": "u001"}], "npi-005", ask_text=q)
    out = s.act(cid, "dismiss", user="doctor")
    assert out["ok"] and out["status"] == "dismissed"
    again = s.post("ask", q, "b", [{"utt": "u001"}], "npi-005", ask_text=q)
    assert again.startswith("rejected") and "dismissed" in again
    again2 = s.post("ask", "Does the pain spread to the arm or jaw?", "b", [{"utt": "u001"}], "ask_pain_radiation",
                    ask_text="Does the pain spread to the arm or jaw?", source="fallback")
    assert again2.startswith("rejected")
    assert len([c for c in s.all_cards() if c["status"] == "open"]) == 0


def test_chest_group_severity_and_resolution():
    c, s = _store()
    v0 = s.version
    s.sync_rules([_fired("WORK-CHEST-04", "caution")], 1.2)
    cards = s.open_cards()
    assert len(cards) == 1 and cards[0]["title"] == "Chest-pain workup" and cards[0]["severity"] == "caution"
    assert s.version > v0
    s.sync_rules([_fired("WORK-CHEST-04", "caution"), _fired("WORK-CHEST-01", "caution")], 11.0)
    card = s.open_cards()[0]
    assert len(card["items"]) == 2 and card["severity"] == "caution"
    s.act(card["id"], "acknowledge")
    # discharge without ECG/troponin: same card escalates to critical and reopens
    s.sync_rules([_fired("WORK-CHEST-04", "caution"), _fired("WORK-CHEST-01", "caution"),
                  _fired("WORK-CHEST-02", "critical"), _fired("WORK-CHEST-03", "critical"),
                  _fired("ALG-PEN-01", "critical", key="ALG-PEN-01|amoxicillin", family="drug_allergy")], 12.0)
    opens = s.open_cards()
    assert len(opens) == 2 and all(o["severity"] == "critical" for o in opens)
    chest = next(o for o in opens if o["title"] == "Chest-pain workup")
    assert sorted(chest["rule_ids"]) == ["WORK-CHEST-01", "WORK-CHEST-02", "WORK-CHEST-03", "WORK-CHEST-04"]
    assert chest["items"][0]["severity"] == "critical"
    pen = next(o for o in opens if o["grounding"] == "ALG-PEN-01")
    assert pen["kind"] == "safety" and pen["source"] == "rules"
    # unchanged sync does not bump the version
    v = s.version
    s.sync_rules([_fired("WORK-CHEST-04", "caution"), _fired("WORK-CHEST-01", "caution"),
                  _fired("WORK-CHEST-02", "critical"), _fired("WORK-CHEST-03", "critical"),
                  _fired("ALG-PEN-01", "critical", key="ALG-PEN-01|amoxicillin", family="drug_allergy")], 12.1)
    assert s.version == v
    s.sync_rules([], 13.0)
    assert s.open_cards() == []
    assert {c_["status"] for c_ in s.all_cards()} == {"resolved"}
    actions = [a["action"] for a in c.audit]
    assert "shown" in actions and "acknowledge" in actions and "escalated" in actions and "resolved" in actions
    a = next(a for a in c.audit if a["action"] == "acknowledge")
    assert set(a) >= {"card_id", "rule_id", "grounding", "action", "reason", "user", "t_min", "state_version"}


def test_add_rule_hits_does_not_resolve():
    _c, s = _store()
    s.sync_rules([_fired("WORK-CHEST-04", "caution")], 1.0)
    s.add_rule_hits([_fired("ALG-PEN-01", "critical", key="ALG-PEN-01|amoxicillin", family="drug_allergy")], 2.0)
    assert len(s.open_cards()) == 2


def test_agent_missed_card_duplicate_of_rule_card():
    _c, s = _store(groundings=("WORK-CHEST-01",))
    s.sync_rules([_fired("WORK-CHEST-01", "caution")], 11.0)
    assert s.post("missed", "No ECG yet", "b", [{"utt": "u001"}], "WORK-CHEST-01") == "duplicate"


def test_override_and_ask_actions():
    _c, s = _store()
    q = "Do you sweat with it?"
    cid = s.post("ask", q, "b", [{"utt": "u001"}], "npi-005", ask_text=q)
    out = s.act(cid, "ask")
    assert out["status"] == "accepted" and out["actions"][-1]["action"] == "ask"
    s.sync_rules([_fired("ALG-PEN-01", "critical", key="k", family="drug_allergy")], 3.0)
    rid = s.open_cards()[0]["id"]
    out = s.act(rid, "override")
    assert out["status"] == "overridden" and out["actions"][-1]["reason"] == "no reason given"
    assert s.act("nope", "dismiss")["ok"] is False
    assert s.act(rid, "explode")["ok"] is False


def test_thread_safe_posts():
    _c, s = _store()
    results = []

    topics = ["arm pain", "sweating", "stairs", "black stools", "vomiting blood", "fever", "cough", "rash",
              "headache", "nausea", "dizziness", "fainting", "palpitations", "swelling", "itching", "back pain",
              "jaw pain", "breathlessness", "diarrhoea", "weight loss"]

    def worker(i):
        q = f"Any {topics[i]}?"
        results.append(s.post("ask", q, "b", [{"utt": "u001"}], "npi-005", ask_text=q))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = [r for r in results if r.startswith("c")]
    assert len(ids) == 3 and len(set(ids)) == 3
    assert len([c for c in s.open_cards() if c["kind"] == "ask"]) == 3


def test_one_open_card_per_checklist_item():
    """Live smoke test regression: 'BP not recorded' and 'No blood pressure recorded' were both left open."""
    _c, s = _store(groundings=("bp",))
    first = s.post("missed", "BP not recorded", "b", ["u001"], "bp")
    assert first.startswith("c")
    assert s.post("missed", "No blood pressure recorded", "b", ["u001"], "bp") == "duplicate"
    assert len(s.open_cards()) == 1
