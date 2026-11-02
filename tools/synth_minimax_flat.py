#!/usr/bin/env python3
"""EP001 MiniMax flat (no-emotion) comparison: synthesis only.

Reads a committed spec (same schema as specs/ep001_spec.json), synthesizes
every segment with MiniMax speech-2.8-hd + Gentleman, emotion NEVER set
(all segments null by construction of the flat spec), and writes the raw
segment mp3s + a duration report as artifact output. Assembly, mastering
and QC happen locally so pauses can be set and measured exactly.

Env:
  SPEC_PATH   repo path of the spec json (default specs/ep001_spec_minimax_flat.json)
  ONLY_SEGS   optional comma list of segment ids to (re)synthesize
  MINIMAX_API_KEY  required (repo secret)
"""
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

VOICE = "Chinese (Mandarin)_Gentleman"
MODEL = "speech-2.8-hd"
OUT = "output"
SEGS_DIR = os.path.join(OUT, "segs")
os.makedirs(SEGS_DIR, exist_ok=True)


def post_json(url, headers, body, attempts=3):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, data=raw, method="POST")
            req.add_header("Content-Type", "application/json")
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # HTTPError / URLError / timeout
            last = e
            print(f"  post attempt {i + 1} failed: {e}; retrying")
            time.sleep(5 * (i + 1))
    raise SystemExit(f"POST {url} failed after {attempts} attempts: {last}")


def probe_seconds(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def synth(seg, tone):
    vs = {"voice_id": VOICE, "speed": seg["speed"], "vol": 1, "pitch": 0}
    if seg.get("emotion"):
        raise SystemExit(f"{seg['id']}: flat spec must have emotion null")
    body = {"model": MODEL, "text": seg["reading"], "stream": False,
            "voice_setting": vs,
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000,
                              "format": "mp3", "channel": 1},
            "pronunciation_dict": {"tone": tone}}
    data = post_json("https://api.minimax.cn/v1/t2a_v2",
                     {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"},
                     body)
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax error seg {seg['id']}: {base}")
    path = os.path.join(SEGS_DIR, f"{seg['id']}.mp3")
    audio = bytes.fromhex(data["data"]["audio"])
    with open(path, "wb") as f:
        f.write(audio)
    secs = probe_seconds(path)
    print(f"synth {seg['id']} speed={seg['speed']} bytes={len(audio)} "
          f"seconds={secs:.2f} target={seg.get('target_seconds')}")
    return {"id": seg["id"], "speed": seg["speed"], "bytes": len(audio),
            "seconds": round(secs, 2),
            "target_seconds": seg.get("target_seconds")}


def main():
    spec_path = os.environ.get("SPEC_PATH",
                               "specs/ep001_spec_minimax_flat.json")
    only = [s.strip() for s in os.environ.get("ONLY_SEGS", "").split(",")
            if s.strip()]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    tone = spec.get("tone", [])
    report = []
    for seg in spec["segments"]:
        if only and seg["id"] not in only:
            continue
        report.append(synth(seg, tone))
    with open(os.path.join(OUT, "synth_report.json"), "w",
              encoding="utf-8") as f:
        json.dump({"spec_path": spec_path, "only_segs": only,
                   "tone_entries": len(tone), "segments": report},
                  f, ensure_ascii=False, indent=2)
    print(f"done: {len(report)} segments, tone entries {len(tone)}")


if __name__ == "__main__":
    main()
