#!/usr/bin/env python3
"""Build the podcast RSS feed (feed/feed.xml) from feed/episodes.json.

Single source of truth: episodes.json holds channel + episode metadata.
The generated feed.xml is published to GitHub Pages together with the
audio files and cover; Xiaoyuzhou / Apple Podcasts / Spotify all sync
from this one feed.

Usage: python3 tools/build_feed.py
"""
import json
import os
from email.utils import format_datetime
from datetime import datetime, timezone
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "feed", "episodes.json")
OUT = os.path.join(ROOT, "feed", "feed.xml")


def el(tag, text, **attrs):
    a = "".join(f' {k}="{escape(str(v), {chr(34): "&quot;"})}"' for k, v in attrs.items())
    return f"<{tag}{a}>{escape(str(text))}</{tag}>"


def main():
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    ch = data["channel"]
    base = ch["base_url"].rstrip("/")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        '     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"',
        '     xmlns:atom="http://www.w3.org/2005/Atom"',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        "  <channel>",
        f"    {el('title', ch['title'])}",
        f"    {el('link', ch['link'])}",
        f"    {el('language', ch['language'])}",
        f"    {el('description', ch['description'])}",
        f"    <atom:link href=\"{escape(ch['feed_url'])}\" rel=\"self\" type=\"application/rss+xml\"/>",
        f"    {el('itunes:author', ch['author'])}",
        f"    {el('itunes:summary', ch['description'])}",
        '    <itunes:owner>',
        f"      {el('itunes:name', ch['author'])}",
        f"      {el('itunes:email', ch['email'])}",
        '    </itunes:owner>',
        f"    <itunes:image href=\"{escape(ch['image_url'])}\"/>",
        f"    <itunes:category text=\"{escape(ch['category'])}\">",
        f"      <itunes:category text=\"{escape(ch['subcategory'])}\"/>",
        "    </itunes:category>",
        f"    {el('itunes:type', 'episodic')}",
        f"    {el('itunes:explicit', 'false')}",
    ]
    for ep in data["episodes"]:
        pub = datetime.fromisoformat(ep["pub_date"])
        audio_url = ep["audio_url"]
        lines += [
            "    <item>",
            f"      {el('title', ep['title'])}",
            f"      {el('description', ep['description'])}",
            f"      {el('pubDate', format_datetime(pub.astimezone(timezone.utc), usegmt=True))}",
            f'      <guid isPermaLink="false">{escape(ep["guid"])}</guid>',
            f'      <enclosure url="{escape(audio_url)}" length="{ep["audio_bytes"]}" type="audio/mpeg"/>',
            f"      {el('itunes:duration', ep['duration'])}",
            f"      {el('itunes:summary', ep['description'])}",
            f"      {el('itunes:explicit', 'false')}",
            f"      {el('itunes:episodeType', ep.get('episode_type', 'full'))}",
            "    </item>",
        ]
    lines += ["  </channel>", "</rss>", ""]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {OUT} with {len(data['episodes'])} episode(s)")


if __name__ == "__main__":
    main()
