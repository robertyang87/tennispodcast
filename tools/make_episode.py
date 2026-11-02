#!/usr/bin/env python3
"""EP001: first full episode, morning-news format (results roundup + one deep topic).

Brain (Luna, gpt-6-luna via Chat Completions) writes a matched spec:
every segment carries display text + reading text (fully Chinese-numeral,
pronunciation-safe) + speed / pause_after / emotion directives.
Executor: MiniMax speech-2.8-hd (Gentleman) synthesizes per segment,
ffmpeg assembles narration with the spec's pauses, lays the original
music bed under results/topic sections with sidechain ducking, puts
intro-002 in front, loudnorms to -18 LUFS.

Modes:
  MODE=full       Luna writes the spec, then produce.
  MODE=from_spec  SPEC_PATH=<repo path to spec json>; skip Luna, produce
                  from that spec (used for QC fix iterations).

Outputs (output/): ep001.mp3, script.md, spec_ep001.json,
mix_report.json, narration_mix.wav (pre-bed, for pause QC).
"""
import json
import os
import re
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
INTRO = "assets/intro/intro_002_zh.mp3"
BGM = os.environ.get("BGM_PATH", "assets/bgm/A_rally_groove.wav")
TITLE = "早班车｜兹韦列夫登顶世界第一：是加冕，还是捡漏？"

# ---------------------------------------------------------------------------
# Role policy: order, speed range, pause range (s), music-bed zone.
# Bed zones: none / news (results, louder) / low (topic, quieter).
# ---------------------------------------------------------------------------
ROLES = [
    # id,        speed range,   pause range,  bed
    ("S0a", (0.90, 0.95), (0.5, 0.8), "none"),
    ("S0b", (0.90, 0.95), (0.8, 1.2), "none"),
    ("S1_1", (0.93, 0.97), (0.6, 0.9), "news"),
    ("S1_2", (0.93, 0.97), (0.6, 0.9), "news"),
    ("S1_3", (0.93, 0.97), (0.6, 0.9), "news"),
    ("S1_4", (0.93, 0.97), (0.6, 0.9), "news"),
    ("S1_5", (0.93, 0.97), (0.6, 0.9), "news"),
    ("S2", (0.93, 0.97), (1.2, 1.8), "news"),
    ("S3a", (0.85, 0.90), (0.7, 1.0), "low"),
    ("S3b", (0.85, 0.90), (1.2, 1.8), "low"),
    ("S3c", (0.85, 0.90), (1.0, 1.5), "none"),
    ("S3d", (0.85, 0.90), (1.2, 1.8), "low"),
    ("S3e", (0.85, 0.90), (1.2, 1.8), "low"),
    ("S3f", (0.83, 0.87), (1.0, 1.5), "low"),
    ("S3g", (0.85, 0.90), (1.5, 2.0), "none"),
    ("S4a", (0.88, 0.92), (2.0, 2.6), "none"),
    ("S4b", (0.88, 0.92), (0.0, 0.0), "none"),
]
ROLE_IDS = [r[0] for r in ROLES]
POLICY = {r[0]: {"speed": r[1], "pause": r[2], "bed": r[3]} for r in ROLES}

TARGET_CHARS = {
    "S0a": (190, 220), "S0b": (200, 230),
    "S1_1": (250, 290), "S1_2": (250, 290), "S1_3": (250, 290),
    "S1_4": (250, 290), "S1_5": (250, 290),
    "S2": (190, 230),
    "S3a": (240, 280), "S3b": (330, 380), "S3c": (70, 100),
    "S3d": (260, 300), "S3e": (260, 300), "S3f": (300, 340),
    "S3g": (130, 160),
    "S4a": (100, 130), "S4b": (70, 90),
}

# Executor-side pronunciation dictionary: appended no matter what Luna
# returns (dedup by word). Format: word/(pin1)(yin1) with tone numbers.
MUST_TONE = [
    "兹韦列夫/(zi1)(wei2)(lie4)(fu1)",
    "阿尔卡拉斯/(a1)(er3)(ka3)(la1)(si1)",
    "德米纳尔/(de2)(mi3)(na4)(er3)",
    "瓦舍罗/(wa3)(she4)(luo2)",
    "莱赫奇卡/(lai2)(he4)(qi2)(ka3)",
    "施耐德/(shi1)(nai4)(de2)",
    "费尔南德斯/(fei4)(er3)(nan2)(de2)(si1)",
    "阿特马纳/(a1)(te4)(ma3)(na4)",
    "黄泽林/(huang2)(ze2)(lin2)",
    "孙心然/(sun1)(xin1)(ran2)",
    "霍达尔/(huo4)(da2)(er3)",
    "德约科维奇/(de2)(yue1)(ke1)(wei2)(qi2)",
    "辛纳/(xin1)(na4)",
    "贝克尔/(bei4)(ke4)(er3)",
    "蒂姆/(di4)(mu3)",
    "穆塞蒂/(mu4)(sai4)(di4)",
    "塔格尔/(ta3)(ge2)(er3)",
    "达特/(da2)(te4)",
    "格里科斯普尔/(ge2)(li3)(ke1)(si1)(pu3)(er3)",
    "抢七/(qiang3)(qi1)",
    "都灵/(du1)(ling2)",
]

FACT_CARD = """
事实卡（唯一事实源；只许用这些事实与数字，不许另编任何比分、积分、排名、人名；
信源点名克制：每条赛果至多点一次信源，话题段不必点名）：

【定调】本期是 2026 年 11 月 2 日星期一早晨的节目；「昨天」=11 月 1 日星期日；
「明天」=11 月 3 日星期二。节目名《网球时差》，这是早间档。

【S0 导览材料】
- 昨天一天打完五站决赛：维也纳、巴塞尔、广州、东京、首尔。
- 阿尔卡拉斯全周不失一盘夺冠；达特从资格赛一路杀到生涯首冠。
- 兹韦列夫：等了十年、大满贯决赛三连败，今天成为世界第一；
  52 周积分 9,550 分，只比辛纳的 9,450 分多 100 分；
  辛纳自 7 月温网之后因膝伤没再打过球。核心问题：加冕，还是捡漏？

【S1 昨日赛果（每条五步式：标题结论句→时间+事件→2-3 个关键数字→背景/信源→一句落点）】
1. 维也纳 ATP500 决赛（信源：路透社）：阿尔卡拉斯 6-1、6-4 胜德米纳尔；
   赛季第 4 冠、生涯第 28 冠；全周不失一盘；对德米纳尔七战全胜；
   德米纳尔是半决赛淘汰兹韦列夫的人（半决赛比分 6-4、1-6、7-6(4)，10 月 31 日打的）；
   落点示例：输了决赛的德米纳尔，把都灵门票的悬念带进了巴黎。
2. 巴塞尔 ATP500 决赛（信源：美联社）：非种子选手瓦舍罗 2-6、6-3、6-3 逆转
   8 号种子莱赫奇卡；生涯第 2 冠、第一个 ATP500 冠军、第一位赢得 ATP500 冠军的
   摩纳哥球员；本周排名回到第 27 位；落点：他明天在巴黎大师赛首轮就打德约科维奇。
3. 广州 WTA250 决赛：资格赛选手达特 4-6、6-3、6-4 胜 4 号种子塔格尔，用时 2 小时 18 分；
   30 岁，生涯第一个 WTA 巡回赛单打冠军；从资格赛打起共 7 场、6 场打满三盘；
   半决赛她挽救多个赛点（只说「挽救多个赛点」，不许报具体个数），
   逆转 16 岁的中国外卡小将孙心然，比分 5-7、7-6(1)、6-0；
   她赛前排名第 115 位，实时排名升到约第 83 位。
4. 东京 WTA500 决赛：3 号种子施耐德 6-4、5-7、6-2 胜费尔南德斯；
   施耐德第二盘一度 4-0 领先被拖入决胜盘；这是她赛季首冠、生涯第 6 冠；
   费尔南德斯连续两周屈居亚军。
5. 首尔挑战赛 125 决赛（信源：南华早报）：4 号种子阿特马纳 7-6(3)、3-6、7-6(9)
   胜 3 号种子黄泽林，用时 2 小时 04 分；决赛因雨移师室内；
   决胜盘抢七，阿特马纳用到第 5 个赛点才锁定胜局；
   黄泽林连续两周打进挑战赛决赛都失利，生涯挑战赛决赛战绩 1 胜 7 负；
   黄泽林排名升至第 85 位。

【S2 今日看点材料（一条桥段）】
- 巴黎大师赛正赛今天（11 月 2 日）开打；卫冕冠军辛纳因膝伤退赛，他已经赛季报销。
- 都灵年终总决赛门票（维也纳站之后的年度积分净值）：霍达尔 3,194 分守住资格线；
  德米纳尔 3,170 分，只差 24 分；39 岁的德约科维奇 2,900 分，差 294 分；
  媒体共识：德约至少要打进巴黎四强才有机会。
- 明天（11 月 3 日）巴黎首轮：德约科维奇对瓦舍罗——昨天刚在巴塞尔夺冠的那个人。
- 可一句带过：兹韦列夫今天以新科世界第一的身份在巴黎首战穆塞蒂。

【S3 话题材料：兹韦列夫登顶世界第一】
- 入场点名：今天的主角是亚历山大·兹韦列夫。
- 画像：今天是他生涯第一周世界第一；ATP 历史上第 30 位世界第一；
  德国第二人，上一位是 1991 年的贝克尔，时隔 35 年；
  他 29 岁 6 个月，是 1974 年纽康姆之后、52 年来最年长的新科世界第一。
- 时间线：他此前三次打进大满贯决赛全败，最痛的是 2020 年美网对蒂姆，
  两盘领先被逆转；2026 年他连夺法网、美网两座大满贯，大满贯决赛战绩变成 2 胜 3 负；
  还打进了今年温网决赛（输给辛纳）；本赛季 65 胜 17 负；
  2026 年他的冠军就是这两座大满贯；此前奥运金牌、两届总决赛冠军他都有了，
  就差大满贯和世界第一，2026 年一次补齐。
- 登顶方式：他在维也纳打进八强（10 月 29 日）就锁定了世界第一；
  半决赛输给德米纳尔也不影响；11 月 2 日新榜正式登顶。
- 重提问题：等了十年、今年又拿了两座大满贯，这个第一为什么还会有人觉得「水」？
- 原因之一（他自己的兑现是真的）：两座大满贯加 65 胜 17 负，
  放在任何年代都是世界第一的成绩单；三连败之后连拿两冠，是心态上的跨越。
- 原因之二（窗口也是真的）：辛纳从 4 月 13 日起就坐在第一的位置上，
  温网决赛后膝伤、赛季报销；阿尔卡拉斯年中因手腕伤缺阵约四个月，
  52 周积分只有 6,100 分；同代最强的两个人同时倒下，这个窗口十年一遇。
- 原因之三（规则奖励稳定输出）：52 周积分他 9,550 分对辛纳 9,450 分，只多 100 分；
  但看年度积分（Race），他 9,350 分，辛纳 7,950 分（且不再增加），
  阿尔卡拉斯 5,110 分；赛季剩余赛事（巴黎加都灵）最多还能拿 2,500 分，
  阿尔卡拉斯在年度积分上还差 4,240 分，追不上——年终第一已经数学锁定，
  他将成为德国网球史上第一位年终第一。
- 结局+反差钩子：只领先一个四个月没打球的人 100 分；
  等辛纳明年回来，这个第一是「借来的」还是「挣来的」，明年一月见分晓。

【S4 收尾材料】
- 互动问题：兹韦列夫这个世界第一，你服不服？如果辛纳今年不受伤，
  这个位置还有他的份吗？评论区聊聊。
- 明日看点一句：明天巴黎，德约科维奇对瓦舍罗，都灵门票的第一道关。
- 告别句（display 原样）：「好了，这就是今天的网球时差，我们明天一早再见。」
- AI 标注句（display 原样）：「本节目由 AI 语音播报，赛果与数据经人工核对。」
  （reading 里把 AI 写成「人工智能」。）
"""

SEG_BRIEF = """
分段表（id 与顺序不许改；每段给 display 与 reading 两版文本）：
- S0a 导览上：问候+日期（2026 年 11 月 2 日，星期一）+自报家门「这里是网球时差」
  → 钩子一：昨天五站决赛打完，有人全周不失一盘，有人从资格赛杀到生涯首冠
  ——「昨天的冠军里，哪个最出乎意料？」190-220 字。
- S0b 导览下：用约 45 秒讲完兹韦列夫梗概（十年、三连败、今天第一、只多 100 分、
  对手四个月没打球），落在核心问题「这个第一，是加冕，还是捡漏？」，
  然后一句「稍后我们就来回答这个问题」，再过渡「先来快速过一遍昨天的赛果」。
  200-230 字。
- S1_1..S1_5 昨日赛果五条，顺序：维也纳、巴塞尔、广州、东京、首尔。
  每条严格五步式：第一句是标题式结论句（点出冠军与看点），接着时间+事件、
  2-3 个关键数字、背景或信源（一句以内）、一句落点。每条 250-290 字。
  条目之间不要写串场句（不要出现「接下来」「再看」这类过渡）。
- S2 今日看点：巴黎今天开打+辛纳退赛赛季报销+都灵门票三人积分形势
  +媒体共识德约至少四强+明天德约对瓦舍罗+可一句带过兹韦列夫首战穆塞蒂。
  190-230 字。
- S3a 话题入场+画像：「今天我们的主角，是亚历山大·兹韦列夫」开场；
  第一周第一、第 30 位、德国第二人（1991 年贝克尔、时隔 35 年）、
  29 岁 6 个月 52 年来最年长新科第一。240-280 字。
- S3b 时间线背景：三连败旧账（2020 美网对蒂姆最痛）→今年法网美网两连冠
  （决赛战绩 2 胜 3 负）→温网决赛→65 胜 17 负→冠军就这两座→
  登顶方式（维也纳八强即锁定、半决赛输球不影响、今天新榜登顶）。330-380 字。
- S3c 转折重提问题：短段。等了十年、今年两座大满贯，为什么还会有人觉得水？
  下面拆三个原因。70-100 字。
- S3d 原因之一：结论先行「原因之一，他自己的兑现是真的」→证据链
  （两座大满贯、65 胜 17 负、任何年代都是第一的成绩单、三连败后连冠是心态跨越）。
  260-300 字。
- S3e 原因之二：结论先行「原因之二，窗口也是真的」→证据链
  （辛纳 4 月 13 日起居首、温网后膝伤报销；阿尔卡拉斯手腕伤缺四个月、
  52 周积分 6,100；同代双子星同时倒下、窗口十年一遇）。260-300 字。
- S3f 原因之三：结论先行「原因之三，积分规则奖励的是活得久、打得多、稳定输出」
  →证据链（52 周 9,550 对 9,450 只多 100；年度积分 9,350 对 7,950 对 5,110；
  剩余上限 2,500 追不上 4,240；年终第一数学锁定、德国史上首位年终第一）。
  数据最密，句子要短。300-340 字。
- S3g 结局+反差钩子：只领先四个月没打球的人 100 分；
  辛纳明年回来，这个第一是借来的还是挣来的，明年一月见分晓（不下结论）。
  130-160 字。
- S4a 互动问题+明日看点：兹韦列夫这个第一你服不服？辛纳不受伤还有他的份吗？
  评论区聊聊。然后一句明日看点：明天巴黎德约对瓦舍罗，都灵门票第一道关。
  100-130 字。
- S4b 告别+AI 标注：严格用事实卡给的两个原句（reading 里 AI 写成人工智能）。
  70-90 字。
"""

STYLE_RULES = """
写稿铁律（文案与声音匹配，音色是「温润男声」，强项亲近感，弱项播报腔与书面长句）：
1. 句子短、口语、有画面感，一句一口气。不要新闻联播腔，不要堆形容词。
2. 每段同时输出两版：
   - display：给人看的文本，可以用阿拉伯数字与英文缩写（比分写 6-1 这种形态）。
   - reading：真正念出来的文本。只许中文汉字口语形态——不许出现任何阿拉伯
     数字、英文、百分号、斜杠。比分读法：「6-1」读「六比一」；
     抢七盘「7-6(3)」读「七比六，抢七小分七比三」；「7-6(9)」读「七比六，
     抢七小分十一比九」；「7-6(1)」读「七比六，抢七小分七比一」；
     「7-6(4)」读「七比六，抢七小分七比四」。
     积分千分位读全：9,550 读「九千五百五十」；3,194 读「三千一百九十四」；
     294 读「二百九十四」；24 读「二十四」；100 读「一百」。
     年份逐字读：2026 读「二零二六」，1991 读「一九九一」，2020 读「二零二零」，
     1974 读「一九七四」。日期读「十一月二日」「十月三十一日」。
     「第 30 位」读「第三十位」；「2 小时 18 分」读「两小时十八分钟」；
     「65 胜 17 负」读「六十五胜十七负」；「1 胜 7 负」读「一胜七负」；
     「第 5 个赛点」读「第五个赛点」；「约第 83 位」读「大约第八十三位」。
3. 每段的声音指令：
   - speed：S0 两段 0.90-0.95；S1 五条与 S2 0.93-0.97；S3 各段 0.85-0.90
     （S3f 数据段 0.83-0.87）；S4 两段 0.88-0.92。
   - pause_after（秒）：S0a 0.5-0.8；S0b 0.8-1.2；S1 每条 0.6-0.9；
     S2 1.2-1.8；S3a 0.7-1.0；S3b 1.2-1.8；S3c 1.0-1.5；S3d、S3e 1.2-1.8；
     S3f 1.0-1.5；S3g 1.5-2.0；S4a 2.0-2.6（互动问题后留思考时间）；S4b 填 0。
   - emotion：只能从 calm、surprised、happy 里选或填 null，多数段填 null；
     S0a、S3g 可用 happy，S3c 可用 surprised，其余克制。
4. 数字与事实只许来自事实卡，一个都不许自己加。信源点名：每条赛果至多一次。
5. tone 发音词典：把 reading 里易读错的多音字词、球员名按 "词/(pin1)(yin1)"
   格式列出（声调数字 1-5），最多 14 条，只列真的出现的。

只输出一个 JSON 对象，不要解释、不要 markdown 代码块：
{"segments": [{"id": "S0a", "display": "...", "reading": "...",
               "speed": 0.92, "pause_after": 0.7, "emotion": null}],
 "tone": ["词/(pin1)(yin1)"]}
"""

PROMPT = f"""你是中文网球播客《网球时差》的写稿人。这次写的不是文章，
是给一个具体音色念的稿子——音色是「温润男声」：强项是像朋友讲故事的亲近感，
弱项是播报腔、书面长句和生僻词。文案必须和声音匹配。
{FACT_CARD}
{SEG_BRIEF}
{STYLE_RULES}"""


def post_json(url, headers, body, timeout=300):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"HTTP {e.code} from {url}: {e.read().decode('utf-8', 'replace')[:500]}") from e


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def luna(messages):
    """One Luna call. NOTE: never send temperature -- Luna-class reasoning
    models reject a non-default temperature with HTTP 400."""
    key = os.environ["OPENAI_API_KEY"]
    auth = {"Authorization": f"Bearer {key}"}
    errors = []
    for model in ["gpt-6-luna", "gpt-5.6-luna"]:
        try:
            data = post_json("https://api.openai.com/v1/chat/completions", auth,
                             {"model": model, "messages": messages})
            print(f"brain used: {model}")
            return parse_json(data["choices"][0]["message"]["content"])
        except Exception as e:  # noqa: BLE001
            print(f"{model} failed: {e}", file=sys.stderr)
            errors.append(str(e))
    raise SystemExit("brain failed: " + " | ".join(errors))


def write_spec():
    obj = luna([{"role": "system", "content": "你只输出 JSON。"},
                {"role": "user", "content": PROMPT}])
    total = sum(len(s.get("display", "")) for s in obj["segments"])
    print(f"draft chars: {total}")
    if total > 4100:
        print("draft too long, asking Luna to compress once")
        obj = luna([{"role": "system", "content": "你只输出 JSON。"},
                    {"role": "user", "content":
                     "下面这份播客分段稿太长了。请压缩到总字数 4000 字以内："
                     "删冗词与重复表述、缩短背景句，但不许删任何事实点、"
                     "不许改任何数字与比分、不许改分段 id 与顺序，"
                     "保持每段 display/reading 双版与声音指令字段，"
                     "reading 仍须全中文口语形态（无阿拉伯数字与英文）。"
                     "只输出同样结构的 JSON 对象：\n"
                     + json.dumps(obj, ensure_ascii=False)}])
        total = sum(len(s.get("display", "")) for s in obj["segments"])
        print(f"compressed chars: {total}")
    short = []
    for s in obj["segments"]:
        lo, hi = TARGET_CHARS.get(s["id"], (0, 0))
        if len(s.get("display", "")) < lo - 20:
            short.append(f"{s['id']}（现 {len(s.get('display', ''))} 字，目标 {lo}-{hi} 字）")
    if total < 3550 or short:
        print(f"draft too short (total {total}); short segments: {short}")
        obj = luna([{"role": "system", "content": "你只输出 JSON。"},
                    {"role": "user", "content":
                     "下面这份播客分段稿有几段写得太短。请只把这些段扩写到"
                     "目标字数区间：" + "、".join(short) +
                     "。扩写只许使用原稿事实卡里已有的事实做背景铺陈与语气连接，"
                     "不许新增任何数字、比分、排名或人名，不许改动其他段，"
                     "不许改分段 id 与顺序，保持每段 display/reading 双版与"
                     "声音指令字段，reading 仍须全中文口语形态"
                     "（无阿拉伯数字与英文）。只输出同样结构的 JSON 对象：\n"
                     + json.dumps(obj, ensure_ascii=False)}])
        total = sum(len(s.get("display", "")) for s in obj["segments"])
        print(f"expanded chars: {total}")
    return obj


def clamp_spec(obj):
    raw = {s["id"]: s for s in obj["segments"]}
    missing = [i for i in ROLE_IDS if i not in raw]
    if missing:
        raise SystemExit(f"spec missing segments: {missing}")
    segs = []
    for rid in ROLE_IDS:
        s = raw[rid]
        pol = POLICY[rid]
        display = str(s["display"]).strip()
        reading = str(s["reading"]).strip()
        if re.search(r"[0-9A-Za-z%]", reading):
            raise SystemExit(
                f"{rid} reading contains digits/latin (TTS-unsafe): {reading[:80]}")
        if not display or not reading:
            raise SystemExit(f"{rid} empty text")
        emo = s.get("emotion")
        if emo not in EMOTIONS:
            emo = None
        segs.append({
            "id": rid,
            "display": display,
            "reading": reading,
            "speed": min(pol["speed"][1], max(pol["speed"][0],
                                              float(s.get("speed", pol["speed"][0])))),
            "pause_after": min(pol["pause"][1], max(pol["pause"][0],
                                                    float(s.get("pause_after", pol["pause"][0])))),
            "emotion": emo,
            "bed": pol["bed"],
        })
    words = {}
    for t in list(obj.get("tone", [])) + MUST_TONE:
        if "/" in t:
            words.setdefault(t.split("/")[0], t)
    tone = list(words.values())[:30]
    return segs, tone


def synth(idx, seg, tone):
    vs = {"voice_id": VOICE, "speed": seg["speed"], "vol": 1, "pitch": 0}
    if seg["emotion"]:
        vs["emotion"] = seg["emotion"]
    body = {"model": MODEL, "text": seg["reading"], "stream": False,
            "voice_setting": vs,
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000,
                              "format": "mp3", "channel": 1},
            "pronunciation_dict": {"tone": tone}}
    data = post_json("https://api.minimax.cn/v1/t2a_v2",
                     {"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}"}, body)
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax error seg {seg['id']}: {base}")
    path = f"{WORK}/seg_{seg['id']}.mp3"
    with open(path, "wb") as f:
        f.write(bytes.fromhex(data["data"]["audio"]))
    print(f"synth {seg['id']} speed={seg['speed']} pause={seg['pause_after']} "
          f"emotion={seg['emotion']} chars={len(seg['display'])}")
    return path


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def probe_seconds(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def silence(dst, secs):
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{secs:.2f}", dst)


def main():
    mode = os.environ.get("MODE", "full")
    if mode == "from_spec":
        with open(os.environ["SPEC_PATH"], encoding="utf-8") as f:
            obj = json.load(f)
        print(f"loaded spec from {os.environ['SPEC_PATH']}")
    else:
        obj = write_spec()
    segs, tone = clamp_spec(obj)
    total = sum(len(s["display"]) for s in segs)
    print(f"segments: {len(segs)} | display chars: {total} | tone entries: {len(tone)}")
    for s in segs:
        lo, hi = TARGET_CHARS[s["id"]]
        flag = "" if lo - 40 <= len(s["display"]) <= hi + 40 else "  <-- off target"
        print(f"  {s['id']}: {len(s['display'])} chars (target {lo}-{hi}){flag}")

    # Dump the spec immediately: if anything later fails, the artifact
    # still carries it and the fix iteration can run MODE=from_spec.
    with open(f"{OUT}/spec_ep001.json", "w", encoding="utf-8") as f:
        json.dump({"title": TITLE, "episode": "EP001",
                   "date": "2026-11-02", "segments": segs, "tone": tone},
                  f, ensure_ascii=False, indent=2)

    # ---- synthesize + assemble narration with spec pauses ----------------
    parts = []
    report = []
    cursor = 0.0
    for i, seg in enumerate(segs):
        mp3 = synth(i, seg, tone)
        wav = f"{WORK}/seg_{seg['id']}.wav"
        run("ffmpeg", "-y", "-i", mp3, "-ar", "44100", "-ac", "2", wav)
        dur = probe_seconds(wav)
        report.append({"id": seg["id"], "chars": len(seg["display"]),
                       "speed": seg["speed"], "pause_after": seg["pause_after"],
                       "emotion": seg["emotion"], "bed": seg["bed"],
                       "seg_seconds": round(dur, 2),
                       "start": round(cursor, 2),
                       "end": round(cursor + dur, 2)})
        parts.append(wav)
        cursor += dur
        if seg["pause_after"] > 0:
            sil = f"{WORK}/sil_{seg['id']}.wav"
            silence(sil, seg["pause_after"])
            parts.append(sil)
            cursor += seg["pause_after"]
    narration_seconds = cursor

    listfile = f"{WORK}/concat.txt"
    with open(listfile, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    narration = f"{WORK}/narration.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, narration)
    # QC byproduct: small mono copy of the pre-bed narration.
    run("ffmpeg", "-y", "-i", narration, "-ar", "22050", "-ac", "1",
        f"{OUT}/narration_mix.wav")

    # ---- music bed: loudness-anchor the loop, tile it, zone gains --------
    bed_norm = f"{WORK}/bed_norm.wav"
    run("ffmpeg", "-y", "-i", BGM, "-af", "loudnorm=I=-26:TP=-3:LRA=20",
        "-ar", "44100", "-ac", "2", bed_norm)
    bed_full = f"{WORK}/bed_full.wav"
    args = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", bed_norm,
            "-t", f"{narration_seconds:.2f}"]
    # Base layer is silent (-60 dB); each segment's zone boosts its window
    # (speech + trailing pause, up to the next segment's start) back up:
    # news -> -7 dB effective, low -> -13 dB, none -> stays silent.
    filters = ["volume=volume=-60dB"]
    zone_boost = {"news": 53.0, "low": 47.0}
    for i, r in enumerate(report):
        if r["bed"] not in zone_boost:
            continue
        end_ext = (report[i + 1]["start"] if i + 1 < len(report)
                   else narration_seconds)
        filters.append(
            f"volume=volume={zone_boost[r['bed']]}dB:"
            f"enable='between(t,{r['start']:.2f},{end_ext:.2f})'")
    filters.append("afade=t=in:st=0:d=1.5")
    filters.append(f"afade=t=out:st={max(0.0, narration_seconds - 3):.2f}:d=3")
    args += ["-af", ",".join(filters), "-ar", "44100", "-ac", "2", bed_full]
    run(*args)

    # ---- duck bed under voice, mix, prepend intro, master ----------------
    mixed = f"{WORK}/mixed.wav"
    run("ffmpeg", "-y", "-i", narration, "-i", bed_full,
        "-filter_complex",
        "[1:a][0:a]sidechaincompress=threshold=0.02:ratio=6:attack=40:"
        "release=400:makeup=1[bed];"
        "[0:a][bed]amix=inputs=2:duration=first:normalize=0[out]",
        "-map", "[out]", mixed)
    intro_wav = f"{WORK}/intro.wav"
    run("ffmpeg", "-y", "-i", INTRO, "-ar", "44100", "-ac", "2", intro_wav)
    gap = f"{WORK}/gap.wav"
    silence(gap, 0.6)
    full_list = f"{WORK}/full_concat.txt"
    with open(full_list, "w") as f:
        for p in [intro_wav, gap, mixed]:
            f.write(f"file '{os.path.abspath(p)}'\n")
    full = f"{WORK}/full.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", full_list, full)
    run("ffmpeg", "-y", "-i", full, "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
        "-codec:a", "libmp3lame", "-b:a", "160k", f"{OUT}/ep001.mp3")
    total_seconds = probe_seconds(f"{OUT}/ep001.mp3")
    print(f"narration: {narration_seconds:.1f}s | episode total: {total_seconds:.1f}s")

    # ---- deliverables -----------------------------------------------------
    spec_out = {"title": TITLE, "episode": "EP001",
                "date": "2026-11-02", "segments": segs, "tone": tone}
    with open(f"{OUT}/spec_ep001.json", "w", encoding="utf-8") as f:
        json.dump(spec_out, f, ensure_ascii=False, indent=2)
    with open(f"{OUT}/mix_report.json", "w", encoding="utf-8") as f:
        json.dump({"narration_seconds": round(narration_seconds, 1),
                   "episode_seconds": round(total_seconds, 1),
                   "segments": report}, f, ensure_ascii=False, indent=2)
    with open(f"{OUT}/script.md", "w", encoding="utf-8") as f:
        f.write(f"# {TITLE}\n\n")
        f.write("《网球时差》EP001 · 早间档「早班车」 · 2026-11-02（试听版，未发布）\n\n")
        f.write("简介：一期看完周一早晨的网球世界——昨日五站决赛赛果速览；"
                "兹韦列夫登顶世界第一的三个原因；明天巴黎，德约科维奇迎战"
                "新科巴塞尔冠军瓦舍罗。本节目由 AI 语音播报，赛果与数据经人工核对。\n\n")
        f.write("## 逐字稿（display 版；reading 版与声音指令见 spec_ep001.json）\n\n")
        for s in segs:
            f.write(f"**{s['id']}** [{s['speed']}x · 停 {s['pause_after']}s"
                    f"{' · ' + s['emotion'] if s['emotion'] else ''}"
                    f" · 乐床 {s['bed']}] {s['display']}\n\n")
        f.write("## 发音词典\n\n")
        for t in tone:
            f.write(f"- `{t}`\n")
    print("done")


if __name__ == "__main__":
    main()
