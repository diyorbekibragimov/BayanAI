# Bayan pitch screenshots

Captured from the live Space (https://dullgrey-team-qh-129-bayan-app.hf.space/) on 2026-11-07.
Desktop shots: 1920×1080 viewport at device scale 2 (3840×2160 PNG), Playwright with Chromium in new-headless mode
(`channel="chromium"`). No browser chrome or cursor. Each shot waits for CSS transitions to finish (at least 1.2 s), and the
translation "shimmer" sweep is paused on its start frame while the shot is taken.
Shots 04–10 come from the built-in scripted demo (`?demo=1`, a Nepali consultation with real LLM translation and worker TTS).
Shots 15/15b come from a live Korean session. Each turn sent 16 kHz PCM made by the worker's TTS, through the page's own `bayanSend('audio', …)` channel (the same payload the pearl's recorder sends).

| File | What it shows | Pitch point |
|---|---|---|
| `01-start-en.png` | Start screen: "New consultation", 2×3 language chips (Nepali selected), "More… +31 languages", English/العربية toggle | Simple one-tap start; built for South-Asian patient languages |
| `02-start-more-panel.png` | "More…" side panel open: search box plus native-script language list (Tagalog, Tamil, Swahili, Japanese, Korean, Spanish…) | Breadth: 37 patient languages |
| `02b-start-more-search.png` | Same panel filtered by typing "kor": 한국어 / Korean | Find any language in seconds |
| `03-start-ar-rtl.png` | Whole UI in Arabic, mirrored right-to-left (language names given in Arabic) | Works for Arabic-speaking doctors (Gulf clinics) |
| `04-consent-ne.png` | Consent screen: Bayan speaks the consent in Nepali, English below for the doctor, big हो / होइन (Yes/No) buttons | Consent and privacy first ("voice is not stored") |
| `05-live-doctor-caption.png` | Doctor's question as a full-screen Nepali caption ("के तपाईंलाई कुनै औषधिहरूमा एलर्जी छ?") with the English beneath, plus "Say it again" / "Slower" in Nepali | Patient sees and hears their own language |
| `05b-live-doctor-translation.png` | Split view: "You are saying" (English) / "Patient will hear" (Nepali) | The doctor can check what will be said |
| `06-live-patient-notes.png` | Patient's Nepali with the English for the doctor; idiom "gyastrik" underlined and explained (may hide acute coronary syndrome); Notes panel with penicillin allergy, a gyastrik alert, observations and two "Ask the patient in Nepali" suggestions | Clinical copilot: catches cultural idioms, missed questions |
| `06b-live-patient-english.png` | Patient reports a penicillin reaction; clean English for the doctor | Patient's words, faithfully to the doctor |
| `07-held-penicillin-amoxicillin.png` | **HERO.** "Sentence held": the patient reported a penicillin allergy; amoxicillin is a penicillin. Shows the patient quote, the doctor quote, and "Say something else" / "Speak it anyway" | Safety: stops a dangerous instruction before the patient hears it |
| `08-wrap-checklist.png` | "Consultation ended" live checklist: care plan in English ✓, care plan in Nepali ✓, checking against safety rules (spinner) | The paperwork writes itself, safety-checked |
| `08b-wrap-checklist-early.png` | Same checklist earlier (Nepali plan in progress) | (alternate) |
| `08c-wrap-checklist-done.png` | Same checklist with every item done | (alternate) |
| `09-review-careplan-qr.png` | Review: editable bilingual care plan (medicines; do not take penicillin or amoxicillin; ECG and blood test; when to call 999), QR code, "Approve and send", doctor report PDF link | Doctor stays in control and approves |
| `10-sent-qr.png` | Sent state: "Sent to the patient", QR for the patient's phone, "Start a new consultation" | Patient leaves with a plan in their language |
| `15-ko-live-caption.png` | Korean consultation: the doctor's English question shown as a large Korean caption ("약에 알레르기가 있나요?") | Same flow in any language (Korean) |
| `15b-ko-consent.png` | Consent spoken and shown in Korean with 예 / 아니요 buttons | (alternate) |
| `../demo.webm` | 88 s screen recording of the scripted Nepali demo, from the start screen to the held screen (1920×1080, VP9, no audio). The HF Spaces badge shows top-right for about the first second. | Live demo backup video |

## Not captured (HF credit freeze, all consultation runs stopped)

- 11/12 phone `/plan` page and 13/14 PDF renders: these need a plan from a finished consultation on the current build
  (app commit 75355c9 redesigned `/plan`). The scripts are ready: `phone_pdf.py` and `render_pdf.py` in the temp capture folder.
- 16 Arabic-doctor live screen: the session was started, then stopped by the freeze. 03 shows the Arabic RTL UI.
- 09/10 may show the review screen from before 75355c9 (their run finished around the time 75355c9 went live). Retake them if
  the new "dotted-line warnings" design matters for the deck.

## Bugs / notes (see `bugs/`)

- `bugs/bug-review-false-dropped-allergy-warning.png` (pre-75355c9 build): the review warned "Dropped from history:
  'Penicillin allergy with swelling after injection': not stated by anyone in the consultation". This is a false positive:
  the patient said it (in Nepali). It also showed "No danger signs were stated by the doctor; the plan shows only the 999 number."
- Notes alert copy has nested parentheses: "The patient described 'gyastrik' ('gastric' (English loanword))." (see 06).
- Care plan repeats itself: "Let's not use amoxicillin." appears under Other instructions as well as under Do not take (09/10).
- More panel: with no match, "No language matches." sits at the very bottom of the panel, far from the search box.
  Georgian was not in the live list at capture time.
- 05b: while the doctor's sentence is still pending, the status already reads "Patient's turn" with the switch on Patient.
- Rendering note, not an app bug: Playwright's old headless shell draws tile seams in the pearl's blurred shadow
  (`bugs/note-headless-shell-tile-seams.png`). Use new-headless or a real browser for screenshots.

## Added for the deck (2026-11-07, no live calls)

| File | What it shows | Source |
|---|---|---|
| `11-plan-phone.png` | Phone `/plan` page (current design), Nepali care plan with English beneath, "Download PDF", Do not take, 999 section. 780×3130 (390-wide at 2×) | Local render of the Nepali demo plan (`bayan-verify…/plan/plan_ne.png`) |
| `13-care-plan-pdf.png` | Patient sheet PDF page 1, Tamil: azithromycin; penicillins (amoxicillin) under "Do not take"; 999 line. 1819×2573 (220 dpi) | `reports/sim/gptoss120b-full/pdf/alg-09-withdraw-then-represcribe_patient.pdf` via `pdftoppm` |
| `14-doctor-report-pdf.png` | Consultation note PDF page 1, Tamil patient: penicillin allergy, azithromycin, safety alert "amoxicillin was then prescribed. The instruction was held." | `…/alg-09-withdraw-then-represcribe_doctor.pdf` via `pdftoppm` |
