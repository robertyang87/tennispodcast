#!/usr/bin/env python3
"""Demo: OpenAI (brain) writes a tennis podcast script + pronunciation dict,
MiniMax (mouth) synthesizes it. Runs in GitHub Actions with repo secrets.

Output: output/script.md, output/script.json, output/demo.mp3
"""
import json
import os
import sys
import urllib.request
import urllib.error

OUT = "output"
os.makedirs(OUT, exist_ok=True)

FACT_CARD = """
事实卡（只许用这些事实，不许另编数字与人名）：
- 抢七由美国人詹姆斯·范·艾伦提出，1970 年美网率先在大满贯启用。
- 2010 年温网首轮，伊斯内尔与马胡特打出一场三天的比赛：决胜盘七十比六十八，
  全场十一小时五分钟，决胜盘本身就打了八小时十一分钟。这场球直接推动规则继续改革。
- 2019 年温网引入决胜盘十二平后的抢七；2022 年四大满贯统一：
  决胜盘六平后打十分制抢七（先到十分、净胜两分）。
- 抢七局记分是一二三四逐分累加，先到七分且净胜两分者赢下这一局与这一盘。
"""

PROMPT = f"""你是中文网球播客《网球时差》的写稿人。请写一段可直接录制的播客开场独白。

主题：抢七，是被一场打不完的比赛逼出来的。
{FACT_CARD}

硬性要求：
1. 朗读稿 420 到 520 个汉字，大约九十秒。按耳朵写：一句一口气，长句拆短，
   多用短句和停顿；开场第一句必须是钩子（一个反直觉的问题或对照），不要自我介绍式开头。
2. 所有数字、比分、年份一律写成中文口语形态（如「七十比六十八」「二零一零年」），
   稿子里不许出现阿拉伯数字和英文。
3. 结尾落在一个能引发讨论的问题上。
4. 另外给出发音词典：把稿子里出现的多音字词、人名按 MiniMax 的 tone 格式列出，
   格式示例："草地/(cao3)(di1)"、"重新/(chong2)(xin1)"。声调数字 1-5，轻声为 5。
   只列真的在稿子里出现、且读音容易被读错的词，最多 12 条。

只输出一个 JSON 对象，不要任何解释、不要 markdown 代码块：
{{"title": "本段标题", "script_read": "朗读稿全文", "tone": ["词/(pin1)(yin1)", "..."]}}
"""


def post_json(url, headers, body, timeout=120):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def write_script():
    key = os.environ["OPENAI_API_KEY"]
    models = ["gpt-6-luna", "gpt-5.6-luna"]
    last_err = None
    for model in models:
        try:
            data = post_json(
                "https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {key}"},
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你只输出 JSON。"},
                        {"role": "user", "content": PROMPT},
                    ],
                    "temperature": 0.8,
                },
            )
            text = data["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:]
            obj = json.loads(text)
            print(f"brain model used: {model}")
            return obj
        except Exception as e:  # noqa: BLE001 - try next candidate model
            print(f"model {model} failed: {e}", file=sys.stderr)
            last_err = e
    raise SystemExit(f"all brain models failed: {last_err}")


def synthesize(script, tone):
    key = os.environ["MINIMAX_API_KEY"]
    body = {
        "model": "speech-2.8-hd",
        "text": script,
        "stream": False,
        "voice_setting": {
            "voice_id": "Chinese (Mandarin)_Gentleman",
            "speed": 1,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "pronunciation_dict": {"tone": tone},
    }
    data = post_json(
        "https://api.minimax.cn/v1/t2a_v2",
        {"Authorization": f"Bearer {key}"},
        body,
        timeout=300,
    )
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax error: {base}")
    audio_hex = data["data"]["audio"]
    return bytes.fromhex(audio_hex), data.get("extra_info", {})


def main():
    obj = write_script()
    title = obj["title"]
    script = obj["script_read"]
    tone = [t for t in obj.get("tone", []) if "/" in t][:12]
    print(f"title: {title}")
    print(f"script chars: {len(script)}")
    print(f"tone entries: {tone}")
    audio, extra = synthesize(script, tone)
    with open(f"{OUT}/demo.mp3", "wb") as f:
        f.write(audio)
    with open(f"{OUT}/script.json", "w", encoding="utf-8") as f:
        json.dump({"title": title, "script_read": script, "tone": tone, "extra_info": extra},
                  f, ensure_ascii=False, indent=2)
    with open(f"{OUT}/script.md", "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n{script}\n\n---\n发音词典（MiniMax tone）：\n\n")
        for t in tone:
            f.write(f"- `{t}`\n")
    print(f"audio bytes: {len(audio)}")


if __name__ == "__main__":
    main()
