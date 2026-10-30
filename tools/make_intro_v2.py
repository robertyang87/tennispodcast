#!/usr/bin/env python3
"""Intro v2: umpire-led opening + real match ball hits.
Owner direction (2026-10-30): the opening must use the umpire's voice;
the v1 freesound hits sounded like table tennis, so the signature hits
now come from real broadcast match audio committed at
assets/sfx/real_serve.wav (serve sequence, serve lands ~0.15s in).

Structure (EN): crowd bed + umpire (PA-processed) "Quiet please. Thank you."
-> 0.45s hush -> real serve sting -> brand VO -> close hit -> tail.
ZH variant: umpire line 「请安静，比赛开始。」. Master -18 LUFS.
Also splices EN intro + demo-003 into episode_with_intro_v2.mp3.
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

UMPIRE_VOICES = ["Chinese (Mandarin)_Male_Announcer",
                 "Chinese (Mandarin)_Radio_Host",
                 "Chinese (Mandarin)_Gentleman"]
BRAND_TEXT = "网球时差。<#0.7#>听见球场另一边。"
SERVE = "assets/sfx/real_serve.wav"


def post_json(url, headers, body, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e


def synth(text, voices, speed, path, emotion=None):
    last = None
    for voice in voices:
        vs = {"voice_id": voice, "speed": speed, "vol": 1, "pitch": 0}
        if emotion:
            vs["emotion"] = emotion
        body = {"model": "speech-2.8-hd", "text": text, "stream": False,
                "voice_setting": vs,
                "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
                "pronunciation_dict": {"tone": []}}
        try:
            data = post_json("https://api.minimax.cn/v1/t2a_v2",
                             {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"}, body)
            if data.get("base_resp", {}).get("status_code") != 0:
                raise RuntimeError(str(data.get("base_resp")))
            with open(path, "wb") as f:
                f.write(bytes.fromhex(data["data"]["audio"]))
            print(f"synth ok: voice={voice} text={text[:24]}")
            return voice
        except Exception as e:  # noqa: BLE001
            print(f"voice {voice} failed: {e}")
            last = e
    raise SystemExit(f"synth failed for {text[:20]}: {last}")


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def silence(dst, secs):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(secs), dst)


def build(umpire_mp3, tag):
    # PA-process the umpire voice: band-limited, compressed, venue echo
    pa = f"{WORK}/umpire_pa_{tag}.wav"
    run("ffmpeg", "-y", "-i", umpire_mp3,
        "-af", "highpass=f=250,lowpass=f=3400,acompressor=threshold=-18dB:ratio=4:attack=5:release=120,"
               "aecho=0.8:0.55:55:0.22,volume=1.15",
        "-ar", "44100", "-ac", "2", pa)
    # crowd bed under the umpire (audience murmur before the hush)
    bed = f"{WORK}/bed_{tag}.wav"
    run("ffmpeg", "-y", "-ss", "8", "-t", "3.6", "-i", f"{WORK}/applause.mp3",
        "-af", "afade=t=in:st=0:d=0.5,afade=t=out:st=2.6:d=1.0,volume=0.16",
        "-ar", "44100", "-ac", "2", bed)
    block = f"{WORK}/umpire_block_{tag}.wav"
    run("ffmpeg", "-y", "-i", bed, "-i", pa,
        "-filter_complex", "[1:a]adelay=350|350[uv];[0:a][uv]amix=inputs=2:duration=first:dropout_transition=0",
        "-ar", "44100", "-ac", "2", block)

    parts = [block]
    hush = f"{WORK}/hush_{tag}.wav"; silence(hush, 0.45); parts.append(hush)

    sting = f"{WORK}/sting_{tag}.wav"
    run("ffmpeg", "-y", "-t", "3.3", "-i", SERVE,
        "-af", "afade=t=out:st=2.6:d=0.7,volume=1.0", "-ar", "44100", "-ac", "2", sting)
    parts.append(sting)

    s = f"{WORK}/s_{tag}.wav"; silence(s, 0.3); parts.append(s)

    vo = f"{WORK}/vo_{tag}.wav"
    run("ffmpeg", "-y", "-i", f"{WORK}/brand.mp3", "-ar", "44100", "-ac", "2", vo)
    parts.append(vo)

    s2 = f"{WORK}/s2_{tag}.wav"; silence(s2, 0.35); parts.append(s2)

    hit = f"{WORK}/hit_{tag}.wav"
    run("ffmpeg", "-y", "-ss", "0.05", "-t", "0.85", "-i", SERVE,
        "-af", "afade=t=out:st=0.35:d=0.5,volume=1.0", "-ar", "44100", "-ac", "2", hit)
    parts.append(hit)

    tail = f"{WORK}/tail_{tag}.wav"; silence(tail, 0.9); parts.append(tail)

    listfile = f"{WORK}/concat_{tag}.txt"
    with open(listfile, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    joined = f"{WORK}/joined_{tag}.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, joined)
    run("ffmpeg", "-y", "-i", joined, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/intro_v2_{tag}.mp3")
    print(f"intro_v2_{tag} done")


def main():
    urllib.request.urlretrieve(
        "https://cdn.freesound.org/previews/428/428231_8343377-lq.mp3", f"{WORK}/applause.mp3")

    synth("Quiet please. Thank you.", UMPIRE_VOICES, 0.92, f"{WORK}/umpire_en.mp3")
    synth("请安静，比赛开始。", UMPIRE_VOICES, 0.92, f"{WORK}/umpire_zh.mp3")
    synth(BRAND_TEXT, ["Chinese (Mandarin)_Gentleman"], 0.88, f"{WORK}/brand.mp3", emotion="calm")

    build(f"{WORK}/umpire_en.mp3", "en")
    build(f"{WORK}/umpire_zh.mp3", "zh")

    urllib.request.urlretrieve(
        "https://github.com/robertyang87/tennispodcast/releases/download/demo-003/demo_v3.mp3",
        f"{WORK}/v3.mp3")
    gap = f"{WORK}/gap.wav"; silence(gap, 0.5)
    list2 = f"{WORK}/concat_splice.txt"
    with open(list2, "w") as f:
        for p in [f"{OUT}/intro_v2_en.mp3", gap, f"{WORK}/v3.mp3"]:
            f.write(f"file '{os.path.abspath(p)}'\n")
    joined2 = f"{WORK}/joined2.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list2, joined2)
    run("ffmpeg", "-y", "-i", joined2, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/episode_with_intro_v2.mp3")
    print("splice done")

    with open(f"{OUT}/intro_v2_notes.md", "w", encoding="utf-8") as f:
        f.write("# 前导音 v2（裁判开场 + 真实击球声）\n\n"
                "- 开场：观众底噪 + 裁判扩声（带通 250–3400Hz + 压缩 + 场馆回声模拟）：\n"
                "  EN 版 “Quiet please. Thank you.”；ZH 版「请安静，比赛开始。」\n"
                "- 裁判说完留 0.45s 静场，然后是真实比赛录音的发球序列\n"
                "  （assets/sfx/real_serve.wav，源自真实转播音频，发球频谱质心约 995Hz，\n"
                "  对比 v1 的 freesound 样本被所有者判定像乒乓球，已弃用）\n"
                "- 品牌口播（温润男声 0.88）：「网球时差。听见球场另一边。」+ 同源单记击球收尾\n"
                "- 母带 -18 LUFS；episode_with_intro_v2.mp3 为 EN 前导 + v3 拼接版\n")


if __name__ == "__main__":
    main()
