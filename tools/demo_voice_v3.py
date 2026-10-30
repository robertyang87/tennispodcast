#!/usr/bin/env python3
"""Demo v3: copy matched to voice.
Brain (Luna) writes a *matched spec*: every segment carries its own
speed / pause_after / emotion / sfx_after, written for the Gentleman
voice's persona. The executor (mouth + mixer) only obeys the spec.

Output: output/demo_v3.mp3, output/spec_v3.json, output/spec_v3.md
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
EMOTIONS = {None, "calm", "surprised", "happy", "sad"}

FACT_CARD = """
事实卡（只许用这些事实，不许另编数字与人名）：
- 抢七由美国人詹姆斯·范·艾伦提出，1970 年美网率先在大满贯启用。
- 2010 年温网首轮，伊斯内尔与马胡特打出一场三天的比赛：决胜盘七十比六十八，
  全场十一小时五分钟，决胜盘本身就打了八小时十一分钟。这场球直接推动规则继续改革。
- 2019 年温网引入决胜盘十二平后的抢七；2022 年四大满贯统一：
  决胜盘六平后打十分制抢七（先到十分、净胜两分）。
- 抢七局记分是一二三四逐分累加，先到七分且净胜两分者赢下这一局与这一盘。
"""

PROMPT = f"""你是中文网球播客《网球时差》的写稿人。这次你写的不是文章，
是给一个具体音色念的稿子——音色是「温润男声」：强项是像朋友讲故事的亲近感，
弱项是播报腔、书面长句和生僻词。文案必须和声音匹配：

主题：抢七，是被一场打不完的比赛逼出来的。
{FACT_CARD}

匹配要求（最重要）：
1. 句子短、口语、有画面感；一句一口气。所有数字、比分、年份写成中文口语形态，
   稿子里不许出现阿拉伯数字和英文。
2. 分成 7 到 10 段，每段同时给出声音指令：
   - speed：0.90 到 1.05。叙事段 1.0；钩子、金句、设问段 0.92-0.95；
     数字密集的那一段单独成段，0.90-0.93。
   - pause_after：这段念完停几秒（0.4 到 3.0）。设问段后至少 1.2；
     最后一段（结尾问题）至少 2.2，给听众留思考时间。
   - emotion：只能从 calm、surprised、happy 里选，或填 null（多数段填 null）。
   - sfx_after：只能在讲完七十比六十八纪录的那一段填 "applause"（欢呼声浪落在那里），
     其余段一律 null。
3. 开场第一段要承接节目固定的开场击球声：从一记球、一拍、一个球场画面切入，
   第一句就是钩子。结尾一段落在一个能引发讨论的问题上。
4. 总字数 420 到 540（所有段 text 合计）。
5. 发音词典 tone：把稿子里易读错的多音字词、人名按 "词/(pin1)(yin1)" 格式列出，
   声调数字 1-5，最多 12 条，只列真的在稿子里出现的。

只输出一个 JSON 对象，不要解释、不要 markdown 代码块：
{{"title": "标题",
  "segments": [{{"text": "...", "speed": 1.0, "pause_after": 0.7,
                 "emotion": null, "sfx_after": null}}],
  "tone": ["词/(pin1)(yin1)"]}}
"""


def post_json(url, headers, body, timeout=300):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} from {url}: {e.read().decode('utf-8', 'replace')[:500]}") from e


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def write_spec():
    key = os.environ["OPENAI_API_KEY"]
    auth = {"Authorization": f"Bearer {key}"}
    errors = []
    for model in ["gpt-6-luna", "gpt-5.6-luna"]:
        try:
            data = post_json("https://api.openai.com/v1/chat/completions", auth,
                             {"model": model,
                              "messages": [{"role": "system", "content": "你只输出 JSON。"},
                                           {"role": "user", "content": PROMPT}]})
            obj = parse_json(data["choices"][0]["message"]["content"])
            print(f"brain used: {model}")
            return obj
        except Exception as e:  # noqa: BLE001
            print(f"{model} failed: {e}", file=sys.stderr)
            errors.append(str(e))
    raise SystemExit("brain failed: " + " | ".join(errors))


def clamp_spec(obj):
    segs = []
    for s in obj["segments"]:
        emo = s.get("emotion")
        if emo not in EMOTIONS:
            emo = None
        sfx = s.get("sfx_after")
        if sfx not in (None, "applause"):
            sfx = None
        segs.append({
            "text": str(s["text"]).strip(),
            "speed": min(1.05, max(0.90, float(s.get("speed", 1.0)))),
            "pause_after": min(3.0, max(0.4, float(s.get("pause_after", 0.7)))),
            "emotion": emo,
            "sfx_after": sfx,
        })
    tone = [t for t in obj.get("tone", []) if "/" in t][:12]
    return obj["title"], segs, tone


def synth(idx, seg, tone):
    vs = {"voice_id": VOICE, "speed": seg["speed"], "vol": 1, "pitch": 0}
    if seg["emotion"]:
        vs["emotion"] = seg["emotion"]
    body = {"model": MODEL, "text": seg["text"], "stream": False,
            "voice_setting": vs,
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            "pronunciation_dict": {"tone": tone}}
    data = post_json("https://api.minimax.cn/v1/t2a_v2",
                     {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"}, body)
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax error seg {idx}: {base}")
    path = f"{WORK}/seg{idx:02d}.mp3"
    with open(path, "wb") as f:
        f.write(bytes.fromhex(data["data"]["audio"]))
    print(f"seg{idx:02d} speed={seg['speed']} emotion={seg['emotion']} pause={seg['pause_after']} sfx={seg['sfx_after']}")
    return path


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def silence(dst, secs):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(secs), dst)


def main():
    title, segs, tone = clamp_spec(write_spec())
    total = sum(len(s["text"]) for s in segs)
    print(f"title: {title} | segments: {len(segs)} | chars: {total} | tone: {len(tone)}")

    sfx_urls = {
        "ballhits": "https://cdn.freesound.org/previews/338/338122_2527347-lq.mp3",
        "applause": "https://cdn.freesound.org/previews/428/428231_8343377-lq.mp3",
    }
    for name, url in sfx_urls.items():
        urllib.request.urlretrieve(url, f"{WORK}/{name}.mp3")

    parts = []

    def add_sil(secs):
        p = f"{WORK}/sil_{len(parts)}.wav"
        silence(p, secs)
        parts.append(p)

    sting = f"{WORK}/sting.wav"
    run("ffmpeg", "-y", "-ss", "0.9", "-t", "3.3", "-i", f"{WORK}/ballhits.mp3",
        "-af", "afade=t=out:st=2.5:d=0.8,volume=0.9", "-ar", "44100", "-ac", "2", sting)
    parts.append(sting)
    add_sil(0.4)

    applause_wav = f"{WORK}/applause_cut.wav"
    run("ffmpeg", "-y", "-ss", "3", "-t", "3.0", "-i", f"{WORK}/applause.mp3",
        "-af", "afade=t=in:st=0:d=0.4,afade=t=out:st=2.2:d=0.8,volume=0.5",
        "-ar", "44100", "-ac", "2", applause_wav)

    for i, seg in enumerate(segs, start=1):
        mp3 = synth(i, seg, tone)
        wav = f"{WORK}/seg{i:02d}.wav"
        run("ffmpeg", "-y", "-i", mp3, "-ar", "44100", "-ac", "2", wav)
        parts.append(wav)
        if seg["sfx_after"] == "applause":
            add_sil(0.4)
            parts.append(applause_wav)
            add_sil(0.6)
        else:
            add_sil(seg["pause_after"])

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
        "-codec:a", "libmp3lame", "-b:a", "128k", f"{OUT}/demo_v3.mp3")

    with open(f"{OUT}/spec_v3.json", "w", encoding="utf-8") as f:
        json.dump({"title": title, "segments": segs, "tone": tone}, f, ensure_ascii=False, indent=2)
    with open(f"{OUT}/spec_v3.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}（v3 匹配版分段稿）\n\n")
        for i, s in enumerate(segs, start=1):
            f.write(f"{i}. [{s['speed']}x · 停{s['pause_after']}s"
                    f"{' · ' + s['emotion'] if s['emotion'] else ''}"
                    f"{' · 后接欢呼' if s['sfx_after'] else ''}] {s['text']}\n")
        f.write("\n发音词典：\n\n")
        for t in tone:
            f.write(f"- `{t}`\n")
    print("done")


if __name__ == "__main__":
    main()
