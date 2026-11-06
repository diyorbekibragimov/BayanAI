"""Bayan AI — HF Space entry point.

Placeholder build (soft-submission checkpoint). The real ambient pipeline
(VAD → ASR → clinical brain → TTS, safety sentinel, outputs) lands here per
docs/08-build-plan.md.
"""

import gradio as gr

INTRO = """
# بيان · Bayan AI

**An ambient interpreter and clinical safety net for the patients Qatar's clinics struggle to hear.**

One tablet on the consultation desk that **listens, talks and thinks**:

- 🎧 **Listens.** No push-to-talk. Works out who is speaking from the language they use.
- 🗣️ **Talks.** Speaks each sentence to the other person in their own language: Nepali, Hindi, Urdu, Bengali, Malayalam, Filipino ↔ English / Arabic.
- 🧠 **Thinks.** Interprets cultural idioms and raises **silent** safety alerts for the doctor only (allergy conflicts, dose errors, missing chest-pain workup).

At the end of the consultation it produces an English SOAP note for the doctor and, for the patient, a care plan in their own language: PDF, WhatsApp, SMS and audio.

---

🚧 **Build in progress:** Qai × Hugging Face Hackathon O1 · Team QH-129 · Doha, 5–7 Nov 2026.

*Decision support for licensed clinicians only. Not a medical device. Demo uses synthetic consultations only.*
"""

with gr.Blocks(title="Bayan AI") as demo:
    gr.Markdown(INTRO)

if __name__ == "__main__":
    demo.launch()
