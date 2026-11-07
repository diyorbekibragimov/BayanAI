"""Supertonic 3 (Supertone, OpenRAIL-M; ~99M params, ONNX) — fast multilingual TTS on CPU.

Used for languages our GPU voices don't cover well (Korean first). Runs on CPU with onnxruntime, so it
never waits for the GPU lock and costs nothing extra. Adapted from the MIT-licensed reference helper at
github.com/supertone-inc/supertonic (py/helper.py).
"""

from __future__ import annotations

import json
import os
import re
from unicodedata import normalize

import numpy as np
import onnxruntime as ort

REPO = "Supertone/supertonic-3"
LANGS = {"en", "ko", "ja", "ar", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", "hi", "hr", "hu", "id", "it",
         "lt", "lv", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi"}

_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿\U0001f1e6-\U0001f1ff]+")
_REPL = {"–": "-", "‑": "-", "—": "-", "_": " ", "“": '"', "”": '"', "‘": "'", "’": "'",
         "´": "'", "`": "'", "[": " ", "]": " ", "|": " ", "/": " ", "#": " ", "→": " ", "←": " "}


def _mask(lengths: np.ndarray, max_len: int | None = None) -> np.ndarray:
    max_len = max_len or int(lengths.max())
    return (np.arange(max_len) < lengths[:, None]).astype(np.float32).reshape(-1, 1, max_len)


class Supertonic:
    def __init__(self, root: str, voice: str = "F1", threads: int = 0):
        d = os.path.join(root, "onnx")
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        cpu = ["CPUExecutionProvider"]
        run = lambda n: ort.InferenceSession(os.path.join(d, f"{n}.onnx"), sess_options=opts, providers=cpu)  # noqa: E731
        self.dp, self.enc, self.est, self.voc = (run(n) for n in
                                                 ("duration_predictor", "text_encoder", "vector_estimator", "vocoder"))
        cfg = json.load(open(os.path.join(d, "tts.json")))
        self.indexer = json.load(open(os.path.join(d, "unicode_indexer.json")))
        self.sr = cfg["ae"]["sample_rate"]
        self.base_chunk = cfg["ae"]["base_chunk_size"]
        self.compress = cfg["ttl"]["chunk_compress_factor"]
        self.ldim = cfg["ttl"]["latent_dim"]
        st = json.load(open(os.path.join(root, "voice_styles", f"{voice}.json")))
        self.style_ttl = np.array(st["style_ttl"]["data"], dtype=np.float32).reshape(1, *st["style_ttl"]["dims"][1:])
        self.style_dp = np.array(st["style_dp"]["data"], dtype=np.float32).reshape(1, *st["style_dp"]["dims"][1:])

    def _prep(self, text: str, lang: str) -> str:
        text = _EMOJI.sub("", normalize("NFKD", text))
        for k, v in _REPL.items():
            text = text.replace(k, v)
        text = re.sub(r"\s+([,.!?;:'])", r"\1", re.sub(r"[♥☆♡©\\]", "", text))
        text = re.sub(r"\s+", " ", text).strip()
        if not re.search(r"[.!?;:,'\"')\]}…。」』】〉》›»؟]$", text):
            text += "."
        return f"<{lang}>{text}</{lang}>"

    def synth(self, text: str, lang: str, steps: int = 8, speed: float = 1.0, seed: int = 0) -> np.ndarray:
        """One sentence -> float32 mono at self.sr."""
        t = self._prep(text, lang)
        ids = np.array([[self.indexer[ord(c)] if ord(c) < len(self.indexer) else 0 for c in t]], dtype=np.int64)
        tmask = _mask(np.array([ids.shape[1]], dtype=np.int64))
        dur, *_ = self.dp.run(None, {"text_ids": ids, "style_dp": self.style_dp, "text_mask": tmask})
        dur = dur / speed
        emb, *_ = self.enc.run(None, {"text_ids": ids, "style_ttl": self.style_ttl, "text_mask": tmask})
        wav_len = (dur * self.sr).astype(np.int64)
        chunk = self.base_chunk * self.compress
        lat_len = int((wav_len.max() + chunk - 1) // chunk)
        lmask = _mask((wav_len + chunk - 1) // chunk, lat_len)
        rng = np.random.default_rng(seed)  # fixed seed: the same sentence always sounds the same
        xt = rng.standard_normal((1, self.ldim * self.compress, lat_len)).astype(np.float32) * lmask
        total = np.array([steps], dtype=np.float32)
        for i in range(steps):
            xt, *_ = self.est.run(None, {"noisy_latent": xt, "text_emb": emb, "style_ttl": self.style_ttl,
                                         "text_mask": tmask, "latent_mask": lmask,
                                         "current_step": np.array([i], dtype=np.float32), "total_step": total})
        wav, *_ = self.voc.run(None, {"latent": xt})
        return wav[0, : int(wav_len[0])].astype(np.float32)
