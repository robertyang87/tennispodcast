#!/usr/bin/env python3
"""Fixed show intro （前导音） for 网球时差 podcast.
Structure (~11s): signature 3-hit sting -> crowd swell -> brand VO
(Gentleman: 「网球时差。<#0.7#>听见球场另一边。」) -> single hit close.
Mastered to -18 LUFS (benchmark standard, docs/benchmarks.md).
Also splices intro + demo-003 into output/episode_with_intro.mp3.
"""
import json
import os
import subprocess
import urllib.request
import urllib.error

OUT = "output"
WORK = "work"
os.makedirs(OUT, exist_ok=True)
os.makedirs(WORK, exist_ok=True)

VO_TEXT = "网球时差。<#0.7#>听见球场另一边。"


def post_json(url, headers, body, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from e


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def silence(dst, secs):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(secs), dst)


def main():
    body = {"model": "speech-2.8-hd", "text": VO_TEXT, "stream": False,
            "voice_setting": {"voice_id": "Chinese (Mandarin)_Gentleman",
                              "speed": 0.88, "vol": 1, "pitch": 0, "emotion": "calm"},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            "pronunciation_dict": {"tone": []}}
    data = post_json("https://api.minimax.cn/v1/t2a_v2",
                     {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"}, body)
    if data.get("base_resp", {}).get("status_code") != 0:
        raise SystemExit(f"MiniMax error: {data.get('base_resp')}")
    with open(f"{WORK}/vo.mp3", "wb") as f:
        f.write(bytes.fromhex(data["data"]["audio"]))
    print("vo synthesized")

    urllib.request.urlretrieve(
        "https://cdn.freesound.org/previews/338/338122_2527347-lq.mp3", f"{WORK}/ballhits.mp3")
    urllib.request.urlretrieve(
        "https://cdn.freesound.org/previews/428/428231_8343377-lq.mp3", f"{WORK}/applause.mp3")

    parts = []

    def add(p):
        parts.append(p)

    sting = f"{WORK}/sting.wav"
    run("ffmpeg", "-y", "-ss", "0.9", "-t", "3.3", "-i", f"{WORK}/ballhits.mp3",
        "-af", "afade=t=out:st=2.5:d=0.8,volume=0.9", "-ar", "44100", "-ac", "2", sting)
    add(sting)

    s1 = f"{WORK}/s1.wav"; silence(s1, 0.3); add(s1)

    swell = f"{WORK}/swell.wav"
    run("ffmpeg", "-y", "-ss", "3", "-t", "1.8", "-i", f"{WORK}/applause.mp3",
        "-af", "afade=t=in:st=0:d=0.7,afade=t=out:st=1.1:d=0.7,volume=0.4",
        "-ar", "44100", "-ac", "2", swell)
    add(swell)

    vo = f"{WORK}/vo.wav"
    run("ffmpeg", "-y", "-i", f"{WORK}/vo.mp3", "-ar", "44100", "-ac", "2", vo)
    add(vo)

    s2 = f"{WORK}/s2.wav"; silence(s2, 0.35); add(s2)

    hit = f"{WORK}/hit.wav"
    run("ffmpeg", "-y", "-ss", "1.0", "-t", "1.0", "-i", f"{WORK}/ballhits.mp3",
        "-af", "afade=t=out:st=0.4:d=0.6,volume=0.7", "-ar", "44100", "-ac", "2", hit)
    add(hit)

    s3 = f"{WORK}/s3.wav"; silence(s3, 0.9); add(s3)

    listfile = f"{WORK}/concat.txt"
    with open(listfile, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    joined = f"{WORK}/joined.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, joined)
    run("ffmpeg", "-y", "-i", joined, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/intro.mp3")
    print("intro done")

    # splice: intro + 0.5s + demo-003 (v3), re-normalize whole to -18
    urllib.request.urlretrieve(
        "https://github.com/robertyang87/tennispodcast/releases/download/demo-003/demo_v3.mp3",
        f"{WORK}/v3.mp3")
    gap = f"{WORK}/gap.wav"; silence(gap, 0.5)
    list2 = f"{WORK}/concat2.txt"
    with open(list2, "w") as f:
        for p in [f"{OUT}/intro.mp3", gap, f"{WORK}/v3.mp3"]:
            f.write(f"file '{os.path.abspath(p)}'\n")
    joined2 = f"{WORK}/joined2.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list2, joined2)
    run("ffmpeg", "-y", "-i", joined2, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/episode_with_intro.mp3")
    print("splice done")

    with open(f"{OUT}/intro_notes.md", "w", encoding="utf-8") as f:
        f.write("# 固定前导音 v1\n\n"
                "- 0.0–3.3s 标志击球声（三连拍，与 demo 片头一致）\n"
                "- 3.6–5.4s 欢呼声浪（渐入渐出，球场氛围）\n"
                "- 品牌口播（温润男声，0.88 倍速，calm）：「网球时差。听见球场另一边。」\n"
                "- 单记击球收尾 + 0.9s 尾音；母带 -18 LUFS\n"
                "- episode_with_intro.mp3 = 前导音 + 0.5s + v3 全文（整体重归一 -18 LUFS）\n")


if __name__ == "__main__":
    main()
