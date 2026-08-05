#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
偏执病患 · 静态站点生成器（粗野主义 Brutalism 版）
====================================================
把仓库根目录下的 Markdown 乐评文章转换成粗野主义风格的静态网站，
输出到 _site/，由 GitHub Actions 部署到 GitHub Pages。

内置三套粗野主义主题，可在下方 THEME 常量或命令行切换：
    brutal-raw       灰纸单栏 · 仿 brutalistwebsites.com（等宽字体、无装饰、生硬反色）
    brutal-terminal  黑底绿字 · 终端机美学（等宽、命令行语感、暗调图片）
    brutal-zine      白纸印刷 · 新粗野主义印刷物（硬阴影、红黄撞色、歪斜贴纸感）

用法：
    pip install markdown pypinyin
    python scripts/build_site.py                  # 使用默认主题构建到 _site/
    python scripts/build_site.py --theme brutal-zine --out _preview/zine
"""

import argparse
import html
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("缺少依赖：请先运行  pip install markdown pypinyin")

try:
    from pypinyin import lazy_pinyin
except ImportError:
    lazy_pinyin = None  # 没有 pypinyin 时退化为纯 ASCII slug

# ────────────────────────── 站点信息（可自由修改） ──────────────────────────
SITE_NAME = "偏执病患"
SITE_LATIN = "Paranoid patients"
SITE_TAGLINE = "在失真的噪音里寻找文学"
SITE_GITHUB = "https://github.com/Trancer2Thrash/MyPost"

# 默认主题：brutal-raw / brutal-terminal / brutal-zine
THEME = "brutal-zine"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"

EXCLUDE_FILES = {"README.md", "AGENTS.md", "CLAUDE.md"}

# ────────────────────────── 工具函数 ──────────────────────────

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def slugify(text: str, maxlen: int = 72) -> str:
    """把标题转成 URL slug：英文保留，中文逐字转拼音。"""
    text = unicodedata.normalize("NFKC", text)
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text)
    parts = []
    for tok in tokens:
        if LATIN_TOKEN_RE.match(tok):
            parts.append(tok.lower())
        elif lazy_pinyin is not None:
            parts.extend(p for p in lazy_pinyin(tok) if p)
    slug = re.sub(r"-{2,}", "-", "-".join(parts)).strip("-")
    return slug[:maxlen].rstrip("-") or "article"


def count_words(text: str) -> int:
    """汉字按字计，英文按词计。"""
    hanzi = len(CJK_RE.findall(text))
    latin = len(LATIN_TOKEN_RE.findall(text))
    return hanzi + latin


def git_creation_date(path: Path):
    """取文件第一次被 git 提交的时间；失败返回 None。"""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        ).stdout.strip().splitlines()
        if out:
            return datetime.fromisoformat(out[-1].strip())
    except Exception:
        pass
    return None


def extract_title(text: str, fallback: str):
    """取第一个一级标题作为文章标题。"""
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if m:
        title = m.group(1).strip()
        title = re.sub(r"[*_`]", "", title)
        return title
    return fallback


def extract_excerpt(text: str, limit: int = 110) -> str:
    """取标题和封面图之后的第一段正文作为摘要。"""
    collected = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            if collected:
                break
            continue
        if s.startswith("#"):
            if collected:
                break
            continue
        if s.startswith(("![", "<", ">", "---", "|")):
            continue
        if re.match(r"^\*.*\*$", s):  # 斜体图注行
            continue
        collected.append(s)
    para = "".join(collected)
    para = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", para)
    para = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", para)
    para = re.sub(r"[*_`#]", "", para)
    # 只压缩/去除 CJK 旁的空白，保留英文单词之间的空格
    para = re.sub(r"(?<=[\u4e00-\u9fff])\s+|\s+(?=[\u4e00-\u9fff])", "", para)
    para = re.sub(r"[ \t]{2,}", " ", para)
    if len(para) > limit:
        return para[:limit] + "…"
    return para or "……"


def render_body(md_text: str, title: str) -> str:
    """Markdown → HTML，并把图片路径改成相对 posts/ 目录的形式。"""
    body = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "toc"],
        output_format="html5",
    )
    # 去掉由文内一级标题产生的第一个 h1（标题由模板单独渲染）
    body = re.sub(r"<h1[^>]*>.*?</h1>\s*", "", body, count=1, flags=re.S)
    body = body.replace('src="images/', 'src="../images/')
    body = body.replace("src='./images/", "src='../images/")
    return body


def fill(tmpl: str, **kw) -> str:
    for k, v in kw.items():
        tmpl = tmpl.replace("__" + k + "__", str(v))
    return tmpl


# ────────────────────────── 字体与图标 ──────────────────────────

FONT_MONO = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700'
    '&family=Noto+Sans+SC:wght@400;700&display=swap" rel="stylesheet">'
)

FONT_ZINE = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black'
    '&family=IBM+Plex+Mono:wght@400;700'
    '&family=Noto+Sans+SC:wght@400;700;900&display=swap" rel="stylesheet">'
)


def favicon(color: str) -> str:
    return ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
            "viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90' "
            f"fill='{color}'%3E%E2%9C%A0%3C/text%3E%3C/svg%3E")


# ────────────────────────── 主题一：brutal-raw ──────────────────────────
# 仿 brutalistwebsites.com：#eee 灰底、等宽字体、无阴影无圆角、老式链接蓝、
# 悬停时生硬反色，像一份未经排版的档案清单。

CSS_RAW = r"""
/* 偏执病患 —— BRUTALISM / brutal-raw：仿 brutalistwebsites.com */
:root {
  --bg: #eee;
  --paper: #fff;
  --ink: #000;
  --dim: #555;
  --accent: #0000ee;
  --mono: "IBM Plex Mono", "Courier New", "Courier", "Noto Sans SC", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--mono);
  font-size: 15px;
  line-height: 1.7;
}
::selection { background: #000; color: #eee; }
a { color: var(--accent); text-decoration: underline; }
a:hover { background: #000; color: #fff; }
.container { max-width: 980px; margin: 0 auto; padding: 0 20px; }

/* 站首 */
.site-header { padding: 46px 0 0; }
.sigil { font-size: 13px; letter-spacing: .6em; color: var(--dim); }
.site-title {
  margin: 6px 0 0;
  font-size: clamp(42px, 8vw, 72px);
  font-weight: 700;
  letter-spacing: -.02em;
  text-transform: uppercase;
  line-height: 1.05;
}
.site-title a { color: #000; text-decoration: none; }
.site-title a:hover { background: #000; color: #eee; }
.site-latin {
  margin: 6px 0 0;
  font-size: 13.5px;
  letter-spacing: .3em;
  text-transform: uppercase;
  color: var(--dim);
}
.rule { border-top: 4px solid #000; margin: 20px 0 12px; }
.rule .orn { display: none; }
.tagline { margin: 0 0 6px; font-size: 14px; color: var(--dim); max-width: 640px; }

.hero { margin: 24px 0 0; border: 3px solid #000; background: #fff; }
.hero img {
  display: block; width: 100%; height: 260px; object-fit: cover;
  filter: grayscale(1) contrast(1.15);
}
.hero figcaption {
  font-size: 11px; letter-spacing: .08em;
  padding: 6px 10px; border-top: 3px solid #000;
  background: #fff; color: var(--dim); text-transform: uppercase;
}

/* 首页卡片 */
.archive-count {
  margin: 36px 0 14px;
  font-size: 13px; letter-spacing: .2em; text-transform: uppercase;
  border-bottom: 2px solid #000; padding-bottom: 6px;
}
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.card {
  display: block;
  background: var(--paper);
  border: 3px solid #000;
  padding: 18px;
  color: #000;
  text-decoration: none;
}
.card:hover { background: #000; color: #fff; }
.card h2 { margin: 0 0 8px; font-size: 19px; line-height: 1.45; letter-spacing: 0; color: inherit; }
.card .meta {
  font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--dim); margin-bottom: 10px;
}
.card:hover .meta { color: #aaa; }
.card .meta .sep { padding: 0 6px; }
.card .excerpt { margin: 0; font-size: 13px; line-height: 1.75; color: inherit; }
.card:hover .excerpt { color: #ddd; }
.card .enter { display: inline-block; margin-top: 12px; font-size: 12px; letter-spacing: .2em; }

/* 文章页 */
.back { display: inline-block; margin: 34px 0 0; font-size: 13px; letter-spacing: .15em; }
.post-header { padding: 20px 0 0; }
.post-header h1 {
  margin: 8px 0 0;
  font-size: clamp(30px, 5.5vw, 46px);
  line-height: 1.3; font-weight: 700; color: #000;
}
.post-header .meta {
  font-size: 12px; color: var(--dim); letter-spacing: .12em;
  margin-top: 10px; text-transform: uppercase;
}
.post-header .meta .sep { padding: 0 6px; }
.post-rule {
  text-align: left; color: #000; margin: 18px 0 26px;
  letter-spacing: 0; font-size: 13px; opacity: 1;
  overflow: hidden; white-space: nowrap;
}

.content { max-width: 760px; margin: 0 auto; }
.content p { margin: 0 0 1.2em; }
.content h2, .content h3, .content h4 {
  font-weight: 700; letter-spacing: 0;
  margin: 2em 0 .8em; text-transform: uppercase; color: #000;
}
.content h2 { font-size: 20px; border-bottom: 3px solid #000; padding-bottom: 6px; }
.content h2::after { content: none; }
.content h3 { font-size: 17px; }
.content a { color: var(--accent); border-bottom: none; }
.content a:hover { background: #000; color: #fff; border-bottom: none; }
.content blockquote {
  margin: 1.6em 0; padding: 12px 18px;
  border-left: 6px solid #000; background: none;
  color: var(--dim); font-size: 14px;
}
.content blockquote p { margin: .3em 0; }
.content img {
  display: block; max-width: 100%; margin: 1.8em 0;
  border: 3px solid #000; padding: 0; background: none; box-shadow: none;
  filter: contrast(1.05);
}
.content em { color: inherit; }
.content strong { color: #000; }
.content hr { border: none; margin: 2em 0; text-align: left; }
.content hr::after { content: "————————————"; color: #000; letter-spacing: 0; font-size: 14px; }
.content ol, .content ul { padding-left: 1.5em; }
.content li { margin-bottom: .4em; }
.content li::marker { color: #000; }
.content code {
  background: #fff; border: 1px solid #000; padding: 1px 5px;
  font-family: var(--mono); font-size: .9em; color: #000;
}
.content pre {
  background: #000; color: #eee; border: 3px solid #000;
  padding: 14px; overflow-x: auto;
}
.content pre code { background: none; border: none; color: inherit; }
.content table { width: 100%; border-collapse: collapse; margin: 1.6em 0; font-size: 13.5px; }
.content th, .content td { border: 2px solid #000; padding: 6px 10px; text-align: left; }
.content th { background: #000; color: #eee; }

/* 页脚 */
.site-footer {
  margin-top: 70px; padding: 26px 0 40px;
  border-top: 4px solid #000;
  text-align: left; font-size: 12px; letter-spacing: .08em; color: var(--dim);
}
.site-footer a { color: var(--accent); border-bottom: none; }
.site-footer .orn { color: #000; }

@media (max-width: 700px) {
  .cards { grid-template-columns: 1fr; }
  .hero img { height: 180px; }
}
"""

# ────────────────────────── 主题二：brutal-terminal ──────────────────────────
# 黑底终端：等宽字体、白色/绿色文本、命令行语感、暗调灰阶图片。

CSS_TERMINAL = r"""
/* 偏执病患 —— BRUTALISM / brutal-terminal：黑底绿字终端机 */
:root {
  --bg: #000;
  --fg: #d8d8d8;
  --green: #00e05a;
  --dim: #6f6f6f;
  --line: #2a2a2a;
  --mono: "IBM Plex Mono", "Courier New", "Noto Sans SC", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: var(--mono);
  font-size: 15px;
  line-height: 1.75;
}
::selection { background: var(--green); color: #000; }
a { color: var(--green); text-decoration: underline; text-underline-offset: 2px; }
a:hover { background: var(--green); color: #000; }
.container { max-width: 900px; margin: 0 auto; padding: 0 20px; }

/* 站首 */
.site-header { padding: 52px 0 0; }
.sigil { color: var(--green); font-size: 13px; letter-spacing: .5em; }
.site-title {
  margin: 8px 0 0;
  font-size: clamp(40px, 7.5vw, 66px);
  font-weight: 700; color: #fff;
  text-transform: uppercase; letter-spacing: .02em; line-height: 1.08;
}
.site-title a { color: #fff; text-decoration: none; }
.site-title a:hover { color: var(--green); background: none; }
.site-title::after {
  content: "▮"; color: var(--green);
  animation: blink 1.1s steps(1) infinite;
  margin-left: 8px;
}
@keyframes blink { 50% { opacity: 0; } }
.site-latin {
  margin: 6px 0 0; color: var(--green);
  font-size: 13px; letter-spacing: .28em; text-transform: uppercase;
}
.rule { border-top: 1px dashed var(--line); margin: 22px 0 12px; }
.rule .orn { display: none; }
.tagline { margin: 0; color: var(--dim); font-size: 13.5px; }
.tagline::before { content: "$ "; color: var(--green); }

.hero { margin: 26px 0 0; border: 1px solid var(--line); }
.hero img {
  display: block; width: 100%; height: 240px; object-fit: cover;
  filter: grayscale(1) contrast(1.3) brightness(.8);
}
.hero figcaption {
  font-size: 11px; color: var(--dim);
  border-top: 1px dashed var(--line); padding: 6px 10px;
}
.hero figcaption::before { content: "// "; color: var(--green); }

/* 首页卡片 */
.archive-count {
  margin: 38px 0 12px;
  font-size: 12px; color: var(--green);
  letter-spacing: .18em; text-transform: uppercase;
}
.archive-count::before { content: "> "; }
.cards { display: block; }
.card {
  display: block;
  border: 1px solid var(--line);
  margin-bottom: 14px; padding: 16px 18px;
  color: var(--fg); text-decoration: none;
}
.card:hover { border-color: var(--green); background: #06130a; }
.card h2 {
  margin: 0 0 6px; font-size: 18px; color: #fff;
  letter-spacing: 0; line-height: 1.5;
}
.card h2::before { content: "# "; color: var(--green); }
.card:hover h2 { color: var(--green); }
.card .meta {
  font-size: 11px; color: var(--dim);
  letter-spacing: .1em; text-transform: uppercase; margin-bottom: 8px;
}
.card .meta .sep { color: var(--green); padding: 0 6px; }
.card .excerpt { margin: 0; font-size: 13px; color: #a8a8a8; }
.card .enter { display: inline-block; margin-top: 10px; font-size: 12px; color: var(--green); letter-spacing: .15em; }

/* 文章页 */
.back { display: inline-block; margin: 36px 0 0; font-size: 12.5px; letter-spacing: .12em; }
.post-header { padding: 18px 0 0; }
.post-header h1 { margin: 6px 0 0; font-size: clamp(28px, 5vw, 42px); color: #fff; line-height: 1.35; }
.post-header .meta {
  font-size: 11.5px; color: var(--dim); margin-top: 10px;
  letter-spacing: .1em; text-transform: uppercase;
}
.post-header .meta .sep { color: var(--green); padding: 0 6px; }
.post-rule { color: var(--green); margin: 20px 0 26px; letter-spacing: .3em; font-size: 12px; }

.content { max-width: 760px; margin: 0 auto; }
.content p { margin: 0 0 1.25em; }
.content h2, .content h3, .content h4 { color: #fff; font-weight: 700; }
.content h2 {
  font-size: 20px; text-transform: uppercase; letter-spacing: .04em;
  border-left: 4px solid var(--green); padding-left: 10px;
  margin: 2em 0 .9em;
}
.content h2::after { content: none; }
.content h3 { font-size: 17px; margin: 1.8em 0 .8em; }
.content h3::before { content: "## "; color: var(--green); }
.content a { border-bottom: none; }
.content a:hover { border-bottom: none; }
.content blockquote {
  border-left: 4px solid var(--green);
  background: rgba(0, 224, 90, .06);
  padding: 12px 18px; margin: 1.6em 0;
  color: #b8b8b8; font-size: 14px;
}
.content blockquote p { margin: .3em 0; }
.content img {
  display: block; max-width: 100%; margin: 1.8em 0;
  border: 1px solid var(--line); padding: 0; background: none; box-shadow: none;
  filter: grayscale(1) contrast(1.25) brightness(.85);
}
.content strong { color: #fff; }
.content em { color: var(--green); font-style: normal; }
.content hr { border: none; margin: 2.2em 0; }
.content hr::after { content: "✠ ──────────── ✠"; color: var(--line); font-size: 12px; letter-spacing: .3em; }
.content ol, .content ul { padding-left: 1.5em; }
.content li { margin-bottom: .4em; }
.content li::marker { color: var(--green); }
.content code {
  background: #0a0a0a; border: 1px solid var(--line);
  color: var(--green); padding: 1px 5px;
  font-family: var(--mono); font-size: .9em;
}
.content pre { background: #050505; border: 1px solid var(--line); padding: 14px; overflow-x: auto; }
.content pre code { border: none; background: none; }
.content table { width: 100%; border-collapse: collapse; margin: 1.6em 0; font-size: 13.5px; }
.content th, .content td { border: 1px solid var(--line); padding: 7px 10px; text-align: left; }
.content th { color: var(--green); text-transform: uppercase; font-size: 12px; letter-spacing: .08em; }

/* 页脚 */
.site-footer {
  margin-top: 72px; padding: 24px 0 40px;
  border-top: 1px dashed var(--line);
  text-align: left; font-size: 12px; color: var(--dim);
}
.site-footer .orn { color: var(--green); }
.site-footer a { border-bottom: none; }

@media (max-width: 700px) {
  .hero img { height: 170px; }
}
"""

# ────────────────────────── 主题三：brutal-zine ──────────────────────────
# 新粗野主义印刷物：白纸、粗黑边框、硬投影、红黄撞色、歪斜贴纸感。

CSS_ZINE = r"""
/* 偏执病患 —— BRUTALISM / brutal-zine：新粗野主义印刷物 */
:root {
  --bg: #f2f0e9;
  --ink: #111;
  --red: #ff2d1a;
  --blue: #1b3cff;
  --yellow: #ffe600;
  --display: "Archivo Black", "Arial Black", "Noto Sans SC", sans-serif;
  --body-font: "Noto Sans SC", Arial, sans-serif;
  --mono: "IBM Plex Mono", "Courier New", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--body-font);
  font-size: 16px;
  line-height: 1.8;
}
::selection { background: var(--red); color: #fff; }
a { color: var(--blue); text-decoration: underline; text-decoration-thickness: 2px; }
a:hover { background: var(--yellow); color: #000; }
.container { max-width: 960px; margin: 0 auto; padding: 0 20px; }

/* 站首 */
.site-header { padding: 54px 0 0; }
.sigil { font-size: 14px; letter-spacing: .7em; color: var(--red); }
.site-title {
  margin: 10px 0 0;
  font-family: var(--display);
  font-size: clamp(46px, 9vw, 84px);
  line-height: 1; text-transform: uppercase; letter-spacing: -.01em;
  font-weight: 400;
}
.site-title a { color: var(--ink); text-decoration: none; }
.site-title a:hover { background: var(--red); color: #fff; }
.site-latin {
  display: inline-block; margin-top: 12px;
  font-family: var(--display); font-weight: 400;
  font-size: 13px; letter-spacing: .3em; text-transform: uppercase;
  background: var(--ink); color: var(--bg);
  padding: 4px 10px; transform: rotate(-1deg);
}
.rule { margin: 26px 0 14px; border-top: 5px solid var(--ink); position: relative; }
.rule .orn {
  position: absolute; top: -13px; left: 24px;
  background: var(--bg); padding: 0 8px;
  color: var(--red); font-size: 15px;
}
.tagline { margin: 0; font-size: 15px; font-weight: 700; max-width: 620px; }

.hero {
  margin: 28px 0 0;
  border: 4px solid var(--ink);
  box-shadow: 10px 10px 0 var(--ink);
  background: #fff;
  transform: rotate(-.4deg);
}
.hero img {
  display: block; width: 100%; height: 280px; object-fit: cover;
  filter: grayscale(1) contrast(1.2);
}
.hero figcaption {
  font-size: 12px; font-weight: 700;
  padding: 8px 12px; border-top: 4px solid var(--ink);
  background: var(--yellow);
}

/* 首页卡片 */
.archive-count {
  display: inline-block; margin: 42px 0 20px;
  font-family: var(--display); font-weight: 400;
  font-size: 14px; letter-spacing: .12em; text-transform: uppercase;
  background: var(--red); color: #fff;
  padding: 6px 14px; transform: rotate(.6deg);
}
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }
.card {
  display: block;
  background: #fff;
  border: 4px solid var(--ink);
  box-shadow: 8px 8px 0 var(--ink);
  padding: 20px;
  color: var(--ink); text-decoration: none;
  transform: rotate(-.3deg);
}
.cards .card:nth-child(even) { transform: rotate(.4deg); }
.card:hover {
  transform: translate(-3px, -3px) rotate(0deg);
  box-shadow: 12px 12px 0 var(--red);
  color: var(--ink);
}
.card h2 {
  margin: 0 0 8px;
  font-family: var(--display); font-weight: 400;
  font-size: 19px; line-height: 1.4; text-transform: uppercase; letter-spacing: 0;
  color: inherit;
}
.card:hover h2 { color: var(--red); }
.card .meta {
  font-size: 11.5px; letter-spacing: .08em; text-transform: uppercase;
  color: #666; margin-bottom: 10px; font-weight: 700;
}
.card .meta .sep { color: var(--red); padding: 0 6px; }
.card .excerpt { margin: 0; font-size: 13.5px; line-height: 1.8; }
.card .enter {
  display: inline-block; margin-top: 14px;
  font-family: var(--display); font-weight: 400;
  font-size: 12px; letter-spacing: .14em;
  background: var(--ink); color: #fff;
  padding: 4px 10px;
}
.card:hover .enter { background: var(--red); color: #fff; }

/* 文章页 */
.back {
  display: inline-block; margin: 40px 0 0;
  font-family: var(--display); font-weight: 400;
  font-size: 13px; letter-spacing: .1em; text-transform: uppercase;
  background: var(--ink); color: #fff;
  padding: 6px 12px; text-decoration: none;
}
.back:hover { background: var(--red); color: #fff; }
.post-header { padding: 22px 0 0; }
.post-header h1 {
  margin: 8px 0 0;
  font-family: var(--display); font-weight: 400;
  font-size: clamp(30px, 6vw, 52px);
  line-height: 1.18; text-transform: uppercase; color: var(--ink);
}
.post-header .meta {
  font-size: 12px; font-weight: 700; letter-spacing: .1em;
  text-transform: uppercase; color: #555; margin-top: 14px;
}
.post-header .meta .sep { color: var(--red); padding: 0 6px; }
.post-rule { color: var(--red); margin: 22px 0 28px; letter-spacing: .5em; font-size: 14px; }

.content { max-width: 760px; margin: 0 auto; }
.content p { margin: 0 0 1.25em; }
.content h2, .content h3, .content h4 { color: var(--ink); }
.content h2 {
  font-family: var(--display); font-weight: 400;
  font-size: 21px; margin: 2.1em 0 .9em; text-transform: uppercase;
  background: var(--yellow); display: inline-block; padding: 2px 10px;
  box-shadow: 4px 4px 0 var(--ink);
}
.content h2::after { content: none; }
.content h3 {
  font-family: var(--display); font-weight: 400;
  font-size: 17px; margin: 1.9em 0 .8em; text-transform: uppercase;
  border-left: 8px solid var(--red); padding-left: 10px;
}
.content a { border-bottom: none; color: var(--blue); }
.content a:hover { background: var(--yellow); color: #000; border-bottom: none; }
.content blockquote {
  margin: 1.7em 0; padding: 14px 20px;
  border: 3px solid var(--ink); background: #fff;
  box-shadow: 6px 6px 0 var(--ink);
  color: var(--ink); font-size: 15px;
}
.content blockquote p { margin: .3em 0; }
.content img {
  display: block; max-width: 100%; margin: 2em 0;
  border: 4px solid var(--ink); padding: 0;
  box-shadow: 8px 8px 0 var(--ink); background: none;
  filter: contrast(1.08) saturate(1.05);
}
.content em { color: inherit; }
.content strong { background: var(--yellow); padding: 0 3px; color: var(--ink); }
.content hr { border: none; margin: 2.4em 0; }
.content hr::after { content: "✠ ✠ ✠"; color: var(--ink); font-size: 15px; letter-spacing: .8em; }
.content ol, .content ul { padding-left: 1.6em; }
.content li { margin-bottom: .45em; }
.content li::marker { color: var(--red); font-weight: 900; }
.content code {
  background: #fff; border: 2px solid var(--ink); padding: 1px 5px;
  font-family: var(--mono); font-size: .88em; color: var(--ink);
}
.content pre {
  background: var(--ink); color: #f5f2e8;
  border: 4px solid var(--ink); padding: 16px; overflow-x: auto;
}
.content pre code { background: none; border: none; color: inherit; }
.content table {
  width: 100%; border-collapse: collapse; margin: 1.7em 0;
  font-size: 14px; background: #fff;
}
.content th, .content td { border: 3px solid var(--ink); padding: 7px 11px; text-align: left; }
.content th {
  background: var(--yellow); text-transform: uppercase;
  font-size: 12.5px; letter-spacing: .06em;
}

/* 页脚 */
.site-footer {
  margin-top: 80px; padding: 28px 0 44px;
  border-top: 5px solid var(--ink);
  text-align: left; font-size: 13px; font-weight: 700;
  color: var(--ink);
}
.site-footer .orn { color: var(--red); }
.site-footer a { border-bottom: none; }

@media (max-width: 700px) {
  .cards { grid-template-columns: 1fr; }
  .hero { transform: none; }
  .hero img { height: 190px; }
}
"""

# ────────────────────────── 主题注册表 ──────────────────────────

HERO_TMPL = (
    '<figure class="hero">'
    '<img src="images/brutal/__IMG__" alt="粗野主义混凝土建筑">'
    '<figcaption>__CAP__</figcaption>'
    '</figure>'
)

THEMES = {
    "brutal-raw": {
        "label": "RAW 灰纸档案 · 仿 brutalistwebsites.com",
        "css": CSS_RAW,
        "fonts": FONT_MONO,
        "favicon": favicon("%23000000"),
        "sigil": "✠ ✠ ✠",
        "rule_orn": "",
        "enter": "✠ ▸",
        "post_rule": "─" * 46,
        "hero": fill(HERO_TMPL, IMG="concrete-03.jpg",
                     CAP="FIG.01 // 清水混凝土住宅 · 重复的阳台板"),
        "footnote": ('手稿存于 <a href="' + SITE_GITHUB +
                     '" target="_blank" rel="noopener">GitHub</a> · 由 GitHub Actions 构建'),
    },
    "brutal-terminal": {
        "label": "黑底终端 · 绿字等宽命令行",
        "css": CSS_TERMINAL,
        "fonts": FONT_MONO,
        "favicon": favicon("%2300e05a"),
        "sigil": "✠ ✠ ✠",
        "rule_orn": "",
        "enter": ">> ✠ >>",
        "post_rule": "✠ ────── ✠",
        "hero": fill(HERO_TMPL, IMG="concrete-02.jpg",
                     CAP="img/002.raw — 混凝土中庭"),
        "footnote": ('manuscripts @ <a href="' + SITE_GITHUB +
                     '" target="_blank" rel="noopener">github</a> // built by github actions'),
    },
    "brutal-zine": {
        "label": "白纸印刷 · 新粗野主义撞色",
        "css": CSS_ZINE,
        "fonts": FONT_ZINE,
        "favicon": favicon("%23ff2d1a"),
        "sigil": "✠ ✠ ✠",
        "rule_orn": "✠",
        "enter": "✠ ➔",
        "post_rule": "✠ ── ✠ ── ✠",
        "hero": fill(HERO_TMPL, IMG="concrete-01.jpg",
                     CAP="混凝土 × 空中连桥 — 粗野主义档案 No.1"),
        "footnote": ('手稿存于 <a href="' + SITE_GITHUB +
                     '" target="_blank" rel="noopener">GitHub</a> — GitHub Actions 构建'),
    },
}

# ────────────────────────── 模板 ──────────────────────────

HEAD_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="__OGTYPE__">
<link rel="icon" href="__FAVICON__">
__FONTS__
<link rel="stylesheet" href="__CSS__">
</head>
<body>
"""

HEADER_TMPL = """
<header class="site-header">
  <div class="container">
  <div class="sigil">__SIGIL__</div>
  <h1 class="site-title"><a href="__HOME__" style="color:inherit;">__SITENAME__</a></h1>
  <p class="site-latin">__SITELATIN__</p>
  <div class="rule"><span class="orn">__RULE_ORN__</span></div>
  <p class="tagline">__TAGLINE__</p>
  __HERO__
  </div>
</header>
"""

FOOTER_TMPL = """
<footer class="site-footer">
  <div class="container">
  <div><span class="orn">✠</span>&nbsp;&nbsp;__SITENAME__ · __YEAR__&nbsp;&nbsp;<span class="orn">✠</span></div>
  <div style="margin-top:8px;">__FOOTNOTE__</div>
  </div>
</footer>
</body>
</html>
"""

INDEX_CARD_TMPL = """
<a class="card" href="posts/__SLUG__.html">
  <h2>__TITLE__</h2>
  <div class="meta">__DATE__<span class="sep">✠</span>约 __WORDS__ 字<span class="sep">✠</span>阅读约 __MINUTES__ 分钟</div>
  <p class="excerpt">__EXCERPT__</p>
  <span class="enter">__ENTER__</span>
</a>
"""

POST_TMPL = """
<main class="container">
  <a class="back" href="../index.html">◂ 返回__SITENAME__</a>
  <div class="post-header">
    <h1>__TITLE__</h1>
    <div class="meta">__DATE__<span class="sep">✠</span>约 __WORDS__ 字<span class="sep">✠</span>阅读约 __MINUTES__ 分钟</div>
  </div>
  <div class="post-rule">__POST_RULE__</div>
  <article class="content">
__BODY__
  </article>
</main>
"""


# ────────────────────────── 构建 ──────────────────────────

def collect_articles():
    articles = []
    for md_file in sorted(ROOT.glob("*.md")):
        if md_file.name in EXCLUDE_FILES:
            continue
        text = md_file.read_text(encoding="utf-8")
        if not text.strip():
            continue
        title = extract_title(text, md_file.stem)
        date = git_creation_date(md_file) or datetime.fromtimestamp(md_file.stat().st_mtime).astimezone()
        words = count_words(text)
        articles.append({
            "path": md_file,
            "text": text,
            "title": title,
            "slug": slugify(title) or md_file.stem,
            "date": date,
            "words": words,
            "minutes": max(1, round(words / 400)),
            "excerpt": extract_excerpt(text),
        })
    # slug 去重
    seen = {}
    for a in articles:
        base = a["slug"]
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            a["slug"] = f"{base}-{n + 1}"
    articles.sort(key=lambda a: a["date"], reverse=True)
    return articles


def build(theme_name: str = None, out_dir: Path = None):
    theme_name = theme_name or THEME
    if theme_name not in THEMES:
        sys.exit(f"未知主题：{theme_name}（可选：{' / '.join(THEMES)}）")
    theme = THEMES[theme_name]
    out = Path(out_dir) if out_dir else OUT
    posts_out = out / "posts"

    if out.exists():
        shutil.rmtree(out)
    posts_out.mkdir(parents=True)

    # 图片目录整体拷贝
    if (ROOT / "images").exists():
        shutil.copytree(ROOT / "images", out / "images", dirs_exist_ok=True)

    (out / "style.css").write_text(theme["css"].strip() + "\n", encoding="utf-8")

    articles = collect_articles()
    year = datetime.now().year

    footer = fill(FOOTER_TMPL, SITENAME=SITE_NAME, YEAR=year, FOOTNOTE=theme["footnote"])

    # ── 文章页 ──
    for a in articles:
        body = render_body(a["text"], a["title"])
        page = fill(HEAD_TMPL,
                    TITLE=html.escape(a["title"]) + " · " + SITE_NAME,
                    DESC=html.escape(a["excerpt"][:80]),
                    OGTYPE="article",
                    FAVICON=theme["favicon"],
                    FONTS=theme["fonts"],
                    CSS="../style.css")
        page += fill(POST_TMPL,
                     SITENAME=SITE_NAME,
                     TITLE=html.escape(a["title"]),
                     DATE=a["date"].strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月"),
                     WORDS=f"{a['words']:,}",
                     MINUTES=a["minutes"],
                     POST_RULE=theme["post_rule"],
                     BODY=body)
        page += footer
        (posts_out / f"{a['slug']}.html").write_text(page, encoding="utf-8")

    # ── 首页 ──
    cards = "".join(
        fill(INDEX_CARD_TMPL,
             SLUG=a["slug"],
             TITLE=html.escape(a["title"]),
             DATE=a["date"].strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月"),
             WORDS=f"{a['words']:,}",
             MINUTES=a["minutes"],
             ENTER=theme["enter"],
             EXCERPT=html.escape(a["excerpt"]))
        for a in articles
    )
    index = fill(HEAD_TMPL,
                 TITLE=f"{SITE_NAME} · {SITE_LATIN}",
                 DESC=html.escape(SITE_TAGLINE),
                 OGTYPE="website",
                 FAVICON=theme["favicon"],
                 FONTS=theme["fonts"],
                 CSS="style.css")
    index += fill(HEADER_TMPL,
                  SITENAME=SITE_NAME, SITELATIN=SITE_LATIN,
                  TAGLINE=SITE_TAGLINE, HOME="index.html",
                  SIGIL=theme["sigil"], RULE_ORN=theme["rule_orn"],
                  HERO=theme["hero"])
    index += (f'<main class="container">\n'
              f'<div class="archive-count">共收录 {len(articles)} 篇手稿</div>\n'
              f'<div class="cards">\n{cards}\n</div>\n</main>\n')
    index += footer
    (out / "index.html").write_text(index, encoding="utf-8")

    print(f"[build:{theme_name}] {theme['label']} → {out}")
    for a in articles:
        print(f"  - {a['date']:%Y-%m-%d}  {a['title']}  ({a['words']}字)  posts/{a['slug']}.html")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="偏执病患 · 粗野主义静态站点生成器")
    ap.add_argument("--theme", default=THEME, choices=list(THEMES),
                    help="选择主题（默认见脚本内 THEME 常量）")
    ap.add_argument("--out", default=None, help="输出目录（默认 _site/）")
    args = ap.parse_args()
    build(args.theme, Path(args.out) if args.out else None)
