# Audio credits: Bayan launch video (`../bayan-launch.mp4`, `../bayan-launch.webm`)

Checked on 7 Nov 2026. Every third-party file below comes from Mixkit (mixkit.co, Envato). Mixkit's licence terms were read on the source site: the licence modals at https://mixkit.co/license/modal/musicFree/ and https://mixkit.co/license/modal/sfxFree/, opened from https://mixkit.co/license/.

## Music

| File | Track | Artist | Source page | Download URL | Licence |
|---|---|---|---|---|---|
| `music-new-bass-01-lily-j-mixkit-720.mp3` | "New Bass 01" (Underscore; moods positive and futuristic; tags technology and industry; 1:36, 123 BPM) | Lily J | https://mixkit.co/free-stock-music/tag/technology/ | https://assets.mixkit.co/music/720/720.mp3 | Mixkit Stock Music Free License |

The source page's JSON-LD for this track reads `"copyrightNotice":"Mixkit Stock Music Free License"` and `"license":"https://mixkit.co/license/#musicFree"`.

Licence summary, quoted from the modal: the music "can be used in your commercial and non-commercial projects for free". It is permitted to "download, copy, modify, distribute and publicly perform the Music Items on any web or social media platform, including internet-based video on demand services, podcasts and advertisements".

The licence does not allow:
- use in CDs or DVDs, video games, or TV or radio broadcast;
- remixing the track, or incorporating it in a music-only track;
- claiming it as your own, or registering it with a rights-management service such as Content ID.

No attribution is required. We credit the track on the outro card anyway.

How we used it: the track starts at its beat-aligned 3.5 s point, is ducked about 13 dB under the narration, and fades out at the end. It plays under narration in a video, which the licence allows; it is not remixed as music.

## Sound effects (Mixkit Sound Effects Free License)

The SFX listing pages state: "All of our sound effects are free to download and ready to use in your next video or audio project, under the Mixkit License". That licence allows commercial use in YouTube videos, social media, online ads, film, presentations and broadcast.

The licence does not allow:
- redistributing an item on its own (as stock, in a tool or template, or with source files);
- claiming it as your own, or registering it with a rights-management service.

No attribution is required.

| File | Mixkit title (id) | Listing page | Download URL | Used for |
|---|---|---|---|---|
| `sfx/whoosh-air-mixkit-1489.wav` | Air woosh (1489) | https://mixkit.co/free-sound-effects/whoosh/ | https://assets.mixkit.co/active_storage/sfx/1489/1489.wav | Soft whoosh on each crossfade |
| `sfx/chime-relaxing-bell-mixkit-3109.wav` | Relaxing bell chime (3109) | https://mixkit.co/free-sound-effects/bell/ | https://assets.mixkit.co/active_storage/sfx/3109/3109.wav | Notes card appears |
| `sfx/pause-elevator-tone-mixkit-2863.wav` | Elevator tone (2863) | https://mixkit.co/free-sound-effects/notification/ | https://assets.mixkit.co/active_storage/sfx/2863/2863.wav | Low tone on "Paused: please check" |
| `sfx/tap-light-pop-mixkit-3005.wav` | Explainer video pops whoosh light pop (3005) | https://mixkit.co/free-sound-effects/whoosh/ | https://assets.mixkit.co/active_storage/sfx/3005/3005.wav | Doctor taps "Ask the patient in Nepali" |
| `sfx/shimmer-magic-sparkle-whoosh-mixkit-2350.wav` | Magic sparkle whoosh (2350) | https://mixkit.co/free-sound-effects/whoosh/ | https://assets.mixkit.co/active_storage/sfx/2350/2350.wav | Intro title shimmer |
| `sfx/shimmer-magic-glitter-mixkit-2352.wav` | Magic glitter or particles (2352) | https://mixkit.co/free-sound-effects/bell/ | https://assets.mixkit.co/active_storage/sfx/2352/2352.wav | Outro shimmer |

**Repository note:** both Mixkit licences forbid redistributing the raw files on their own. The finished videos are fine to publish. Do not push the raw `.mp3` and `.wav` files above to a public repository; keep them local, or add `docs/pitch/assets/audio/*.mp3` and `docs/pitch/assets/audio/sfx/` to `.gitignore`.

## Narration (synthetic)

| Files | Engine | Licence |
|---|---|---|
| `narration/n1.wav` to `n9.wav`; text in `narration/lines.json` | Supertonic 3 (`Supertone/supertonic-3`), voice style **F1**, speed 0.84, 32 steps, run locally on CPU with `voice_worker/supertonic.py` | Model: BigScience OpenRAIL-M. Its use restrictions require disclosing machine-generated content, so the outro card says "Narration: synthetic voice (Supertonic 3)" |
| `nepali/ne_q1.wav`, `nepali/ne_q2.wav` | Indic Parler-TTS (`ai4bharat/indic-parler-tts`) on the team's Bayan Voice Worker (`/v1/speak_stream`, `lang: "ne"`), speaking the exact Nepali lines shown in the demo | Apache-2.0 |
