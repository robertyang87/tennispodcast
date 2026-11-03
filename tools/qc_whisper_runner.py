import json, os, re, subprocess, sys, difflib
import numpy as np
os.environ.setdefault("HF_HOME", os.path.abspath(".hfcache"))
from faster_whisper import WhisperModel
from pypinyin import lazy_pinyin

import os as _os
BASE = _os.environ.get("QC_BASE", ".")
spec = json.load(open(f"{BASE}/qc-staging/spec_ep001_minimax_flat.json", encoding="utf-8"))
report = json.load(open(f"{BASE}/qc-staging/mix_report_minimax_flat.json"))
rep = {r["id"]: r for r in report["segments"]}
os.makedirs("/tmp/qc_slices_runner", exist_ok=True)

model = WhisperModel("medium", device="cpu", compute_type="int8")

def pin(text):
    text = re.sub(r"[^一-鿿0-9A-Za-z]", "", text)
    return " ".join(lazy_pinyin(text))

results = {}
for s in spec["segments"]:
    sid = s["id"]; r = rep[sid]
    sl = f"/tmp/qc_slices_runner/{sid}.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{r['start']:.2f}",
                    "-t", f"{r['seg_seconds']:.2f}",
                    "-i", f"{BASE}/qc-staging/ep001_minimax_flat.mp3",
                    "-ar", "16000", "-ac", "1", sl], check=True)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sl, "-f", "f32le",
                          "-ar", "16000", "-ac", "1", "-"],
                         check=True, capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    segs, info = model.transcribe(audio, language="zh", beam_size=5,
                                  vad_filter=True)
    asr = "".join(x.text for x in segs).strip()
    tp, ap = pin(s["reading"]), pin(asr)
    ratio = difflib.SequenceMatcher(None, tp.split(), ap.split()).ratio()
    results[sid] = {"ratio": round(ratio, 3), "asr": asr}
    flag = "  <== CHECK" if ratio < 0.93 else ""
    print(f"{sid}: pinyin-ratio {ratio:.3f}{flag}", flush=True)
    if ratio < 0.97:
        sm = difflib.SequenceMatcher(None, tp.split(), ap.split())
        diffs = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                diffs.append(f"{tag}: target[{' '.join(tp.split()[i1:i2])}] vs asr[{' '.join(ap.split()[j1:j2])}]")
        print("   DIFFS:", " | ".join(diffs[:10]), flush=True)
    print(f"   ASR: {asr[:160]}", flush=True)
json.dump(results, open(f"{BASE}/qc-staging/qc_whisper_minimax_flat.json", "w"),
          ensure_ascii=False, indent=2)
print("saved", f"{BASE}/qc-staging/qc_whisper_minimax_flat.json")
