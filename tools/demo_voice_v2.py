#!/usr/bin/env python3
"""Demo v2: same Luna script as demo-001, re-produced with
- per-segment adaptive speed (brain/editor tags speed, mouth obeys)
- structural pauses (pause_after per segment = thinking time)
- sound design: signature rally hits at open, crowd applause as the
  reaction beat after the 70-68 record, single hit signature at close.

Runs in GitHub Actions. Output: output/demo_v2.mp3 + output/mix_notes.md
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

OUT = "output"
WORK = "work"
os.makedirs(OUT, exist_ok=True)
os.makedirs(WORK, exist_ok=True)

VOICE = "Chinese (Mandarin)_Gentleman"
MODEL = "speech-2.8-hd"

TONE = [
    "詹姆斯·范·艾伦/(zhan1)(mu3)(si1)(fan4)(ai4)(lun2)",
    "伊斯内尔/(yi1)(si1)(nei4)(er3)",
    "马胡特/(ma3)(hu2)(te4)",
    "抢七/(qiang3)(qi1)",
    "温网/(wen1)(wang3)",
    "大满贯/(da4)(man3)(guan4)",
    "决胜盘/(jue2)(sheng4)(pan2)",
    "累加/(lei3)(jia1)",
    "收束/(shou1)(shu4)",
    "净胜/(jing4)(sheng4)",
]

# (text, speed, pause_after_seconds)
SEGMENTS = [
    ("一场比赛打得越久，规则就越像是在承认自己管不住它吗？", 0.94, 1.4),
    ("抢七的出现，正是网球给漫长拉锯设下的一道出口。它由美国人詹姆斯·范·艾伦提出，一九七零年，美网率先在大满贯启用。", 1.0, 0.7),
    ("但出口有时仍然不够宽。二零一零年温网首轮，伊斯内尔和马胡特打出一场跨越三天的比赛。", 0.98, 0.7),
    ("决胜盘，七十比六十八；全场，十一小时零五分钟。光是决胜盘，就打了八小时十一分钟。", 0.92, 0.4),
    # applause beat is inserted here by the mixer (reaction + thinking time)
    ("这不是一串冷冰冰的纪录，而是一个问题被推到了眼前：比赛究竟应该由谁来决定，是球员一分一分地耗下去，还是规则替双方画出边界？这场球直接推动规则继续改革。", 1.0, 0.7),
    ("于是，二零一九年温网引入决胜盘十二平后的抢七。到二零二二年，四大满贯统一采用另一道界线：决胜盘六平后，打十分制抢七。先到十分，还要净胜两分，才算赢。", 0.98, 0.7),
    ("规则可以画出终点，却不能替任何人抵达。到了门槛，还得再把那两分赢出来。", 0.95, 1.0),
    ("普通抢七也是这个逻辑，只是门槛是七分。记分从一、二、三、四逐分累加，先到七分且净胜两分，赢下这一局与这一盘。它把一场可能继续延长的比赛，收束到一分一分的压力里。", 1.0, 0.7),
    ("每一分都像终点，却又不是终点；不到两分的差距，谁也不能提前庆祝。", 0.95, 1.2),
    ("所以，抢七究竟是在保护比赛，还是在替比赛删掉它最漫长、也最残酷的部分？", 0.92, 2.2),
]

SFX = {
    # CC0 (freesound 338122, jacklilley) - rally of pro ball hits
    "ballhits": "https://cdn.freesound.org/previews/338/338122_2527347-lq.mp3",
    # CC BY 4.0 (freesound 428231, Leoctiurs) - crowd applause; credit in mix notes
    "applause": "https://cdn.freesound.org/previews/428/428231_8343377-lq.mp3",
}


def post_json(url, headers, body, timeout=300):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from e


def synth(idx, text, speed):
    body = {
        "model": MODEL, "text": text, "stream": False,
        "voice_setting": {"voice_id": VOICE, "speed": speed, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        "pronunciation_dict": {"tone": TONE},
    }
    data = post_json("https://api.minimax.cn/v1/t2a_v2",
                     {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"}, body)
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax error on segment {idx}: {base}")
    path = f"{WORK}/seg{idx:02d}.mp3"
    with open(path, "wb") as f:
        f.write(bytes.fromhex(data["data"]["audio"]))
    print(f"seg{idx:02d} speed={speed} bytes ok")
    return path


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def to_wav(src, dst, extra=None):
    cmd = ["ffmpeg", "-y", "-i", src]
    if extra:
        cmd += extra
    cmd += ["-ar", "44100", "-ac", "2", dst]
    run(*cmd)


def silence(dst, secs):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(secs), dst)


def main():
    for name, url in SFX.items():
        dst = f"{WORK}/{name}.mp3"
        urllib.request.urlretrieve(url, dst)
        print("sfx downloaded:", name)

    parts = []  # wav files in timeline order

    def add_sil(secs):
        p = f"{WORK}/sil_{len(parts)}.wav"
        silence(p, secs)
        parts.append(p)

    # Opening signature: 3-hit rally (hits at ~1.27/2.42/3.70 in source)
    sting = f"{WORK}/sting.wav"
    run("ffmpeg", "-y", "-ss", "0.9", "-t", "3.3", "-i", f"{WORK}/ballhits.mp3",
        "-af", "afade=t=out:st=2.5:d=0.8,volume=0.9", "-ar", "44100", "-ac", "2", sting)
    parts.append(sting)
    add_sil(0.4)

    for i, (text, speed, pause) in enumerate(SEGMENTS, start=1):
        mp3 = synth(i, text, speed)
        wav = f"{WORK}/seg{i:02d}.wav"
        to_wav(mp3, wav)
        parts.append(wav)
        if i == 4:
            # crowd reaction beat: 0.4s breath, applause swell, 0.6s settle
            add_sil(0.4)
            app = f"{WORK}/applause_cut.wav"
            run("ffmpeg", "-y", "-ss", "3", "-t", "3.0", "-i", f"{WORK}/applause.mp3",
                "-af", "afade=t=in:st=0:d=0.4,afade=t=out:st=2.2:d=0.8,volume=0.5",
                "-ar", "44100", "-ac", "2", app)
            parts.append(app)
            add_sil(0.6)
        elif pause > 0:
            add_sil(pause)

    # Closing signature: one soft hit after the thinking pause
    hit = f"{WORK}/hit.wav"
    run("ffmpeg", "-y", "-ss", "1.0", "-t", "1.0", "-i", f"{WORK}/ballhits.mp3",
        "-af", "afade=t=out:st=0.4:d=0.6,volume=0.7", "-ar", "44100", "-ac", "2", hit)
    parts.append(hit)
    add_sil(0.8)

    listfile = f"{WORK}/concat.txt"
    with open(listfile, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    joined = f"{WORK}/joined.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, joined)
    run("ffmpeg", "-y", "-i", joined, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/demo_v2.mp3")

    with open(f"{OUT}/mix_notes.md", "w", encoding="utf-8") as f:
        f.write("# demo v2 混音说明（与 demo-001 同稿对照）\n\n")
        f.write("- 逐段语速：" + " / ".join(f"段{i+1} {s[1]}" for i, s in enumerate(SEGMENTS)) + "\n")
        f.write("- 留白：钩子问句后 1.4s；纪录段后用欢呼声浪作反应拍（0.4 静默＋3.0 欢呼＋0.6 静默）；"
                "结尾问题后 2.2s 静默再落标志击球声。\n")
        f.write("- 声音设计：开场 3 记击球（品牌标志音）、纪录点欢呼、结尾单记击球收束；无音乐床。\n")
        f.write("- 素材许可：击球声 freesound 338122（CC0, jacklilley）；欢呼声 freesound 428231"
                "（CC BY 4.0, Leoctiurs）——预览音质版，正式生产换全码率文件并保留署名。\n")
    print("done")


if __name__ == "__main__":
    main()
