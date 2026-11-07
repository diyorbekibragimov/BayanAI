"""Bayan AI · consultation state shared by the talk loop, the rule engine and the copilot agent.

Times are consultation-relative minutes (float). Live mode uses the wall clock since the consultation
started; replay mode sets the scenario clock per turn (manifest `t_scenario`), so timer rules such as
WORK-CHEST-01 ("no ECG 10 min after chest pain") behave as in a real consultation.

Evidence items everywhere have the shape {"utt": "u003", "t_min": 1.0, "quote": "..."}.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def empty_state() -> dict:
    """Clinical state, following docs/05 §2.3 (plus stopped_meds and questions_asked)."""
    return {
        "allergies": [],        # {"substance","class","reaction","severity","evidence":[ev],"confidence"}
        "current_meds": [],     # {"drug","class":[..],"dose_mg","frequency_per_day","daily_dose_mg","route","evidence"}
        "prescribed_meds": [],  # as current_meds + "duration_days","indication"
        "stopped_meds": [],     # drugs the doctor withdrew this consultation: {"drug","evidence"}
        "symptoms": [],         # {"code","severity","onset","first_mention_min","evidence"}
        "vitals": {},           # hr, bp_sys, bp_dia, rr, spo2, temp_c, temp_site
        "investigations": [],   # {"code","status":"ordered|resulted","result","evidence"}
        "interventions": [],    # {"code","evidence"}
        "assessments": [],      # {"code","evidence"}
        "disposition": {"type": None, "evidence": []},  # discharge|admit|refer|observe|None
        "patient": {
            "age_years": None, "sex": None, "pregnant": "unknown", "gestation_weeks": None, "weight_kg": None,
            "egfr": None, "hepatic_impairment": "unknown", "heat_exposure": None, "heat_illness_suspected": None,
            "dehydration": "unknown", "travel_malaria_endemic_days": None, "ancestry_region": None,
        },
        "idiom_hits": [],       # {"id","red_flag_tags":[..],"utt","t_min","matched"}
        "questions_asked": [],  # topic codes the doctor has already asked about, e.g. "pain_radiation"
    }


def fmt_t(t_min: float | None) -> str:
    """Consultation time as mm:ss."""
    if t_min is None:
        return "--:--"
    s = int(round(t_min * 60))
    return f"{s // 60:02d}:{s % 60:02d}"


@dataclass
class Turn:
    id: str                 # "u001", "u002", ...
    t_min: float            # consultation time of the utterance
    role: str               # "doctor" | "patient" | "bayan"
    lang: str               # language the words were said in
    text: str               # as said (native script for the patient)
    english: str = ""       # literal English rendering
    translation: str = ""   # what was (or would be) spoken to the listener
    held: bool = False      # doctor turn held back by a critical prescribing alert
    kind: str = "speech"    # "speech" | "ask" (Bayan asking a doctor-approved question) | "system"

    def line(self) -> str:
        en = self.english if self.english and self.english != self.text else ""
        return f"{self.id} [{fmt_t(self.t_min)}] {self.role.upper()} ({self.lang}): {self.text}" + (f" | EN: {en}" if en else "")


@dataclass
class Consultation:
    patient_lang: str = "ne"
    doctor_lang: str = "en"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    started_at: float = field(default_factory=time.time)
    scenario_min: float | None = None   # replay mode: consultation clock set from the manifest
    turns: list[Turn] = field(default_factory=list)
    state: dict = field(default_factory=empty_state)
    state_version: int = 0
    cards: Any = None                   # bayan.brain.cards.CardStore, attached by bayan.brain.copilot
    trace: list[dict] = field(default_factory=list)   # agent activity feed: {"t_min","kind","text"}
    audit: list[dict] = field(default_factory=list)   # append-only log of alerts/cards and doctor actions
    agent_seen: int = 0                 # number of turns the copilot has already processed
    mute_until: float = 0.0             # wall-clock seconds; mic turns ending before this are Bayan's own voice
    ended: bool = False
    outputs: dict = field(default_factory=dict)       # wrap-up results (note, care plan, file paths, links)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # ---------------------------------------------------------------- clock
    def now_min(self) -> float:
        if self.scenario_min is not None:
            return self.scenario_min
        return (time.time() - self.started_at) / 60.0

    def set_scenario_time(self, t_min: float) -> None:
        self.scenario_min = float(t_min)

    # ---------------------------------------------------------------- transcript
    def add_turn(self, role: str, lang: str, text: str, english: str = "", translation: str = "",
                 held: bool = False, kind: str = "speech", t_min: float | None = None) -> Turn:
        with self.lock:
            turn = Turn(id=f"u{len(self.turns) + 1:03d}", t_min=self.now_min() if t_min is None else t_min,
                        role=role, lang=lang, text=text, english=english, translation=translation,
                        held=held, kind=kind)
            self.turns.append(turn)
            return turn

    def transcript(self, since: int = 0, limit: int | None = None) -> str:
        turns = self.turns[since:]
        if limit is not None:
            turns = turns[-limit:]
        return "\n".join(t.line() for t in turns)

    def turn_by_id(self, utt: str) -> Turn | None:
        return next((t for t in self.turns if t.id == utt), None)

    # ---------------------------------------------------------------- activity feed
    def log(self, kind: str, text: str) -> None:
        """kind: "tool" | "agent" | "card" | "rule" | "error" | "system". Shown in the UI's agent-activity panel."""
        with self.lock:
            self.trace.append({"t_min": self.now_min(), "kind": kind, "text": text})
