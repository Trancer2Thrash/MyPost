#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
偏执病患 · 静态站点生成器
========================
把仓库根目录下的 Markdown 乐评文章转换成黑暗哥特风格的静态网站，
输出到 _site/，由 GitHub Actions 部署到 GitHub Pages。

用法（本地预览）：
    pip install markdown pypinyin
    python scripts/build_site.py
    # 然后用浏览器打开 _site/index.html
"""

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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
POSTS_OUT = OUT / "posts"

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
    # 给正文第一个段落加首字下沉
    body = re.sub(r"<p>", '<p class="lead">', body, count=1)
    return body


# ────────────────────────── 样式与模板 ──────────────────────────

CSS = r"""
/* Paranoidpatients —— / 金属 / 哥特 / 摇滚 */
:root {
  --bg: #07060a;
  --panel: #100d15;
  --panel-2: #16121d;
  --line: #2b2433;
  --text: #cfc8ba;
  --text-dim: #8d8577;
  --gold: #c9a45c;
  --gold-bright: #e8c987;
  --blood: #8a1f2b;
  --blood-bright: #c0303f;
  --silver: #a9a4b4;
  --font-serif-han: "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif;
  --font-black-letter: "Pirata One", "UnifrakturMaguntia", "Cinzel", var(--font-serif-han), serif;
  --font-caps: "Cinzel", "Times New Roman", var(--font-serif-han), serif;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }

body {
  margin: 0;
  background-color: var(--bg);
  background-image:
    radial-gradient(ellipse 90% 55% at 50% -10%, rgba(138, 31, 43, 0.16), transparent 70%),
    radial-gradient(ellipse 70% 50% at 50% 115%, rgba(90, 60, 130, 0.10), transparent 70%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
  background-attachment: fixed;
  color: var(--text);
  font-family: var(--font-serif-han);
  font-size: 17px;
  line-height: 1.9;
  border-top: 3px solid transparent;
  border-image: linear-gradient(90deg, transparent, var(--blood) 25%, var(--gold) 50%, var(--blood) 75%, transparent) 1;
}

::selection { background: var(--blood); color: #f5e9d0; }

::-webkit-scrollbar { width: 10px; }
::-webkit-scrollbar-track { background: #0b0910; }
::-webkit-scrollbar-thumb { background: #332a3f; border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #4a3d59; }

a { color: var(--gold); text-decoration: none; transition: color .25s ease; }
a:hover { color: var(--gold-bright); }

.container { max-width: 880px; margin: 0 auto; padding: 0 22px; }

/* ── 站首 ── */
.site-header { text-align: center; padding: 72px 0 30px; }

.sigil {
  color: var(--blood-bright);
  letter-spacing: 1.2em;
  text-indent: 1.2em;
  font-size: 15px;
  margin-bottom: 14px;
  animation: flicker 4.5s ease-in-out infinite;
}
@keyframes flicker {
  0%, 100% { opacity: .85; text-shadow: 0 0 6px rgba(192, 48, 63, .35); }
  50% { opacity: .45; text-shadow: none; }
}

.site-title {
  margin: 0;
  font-family: var(--font-serif-han);
  font-weight: 900;
  font-size: clamp(38px, 7vw, 58px);
  letter-spacing: .22em;
  text-indent: .22em;
  background: linear-gradient(180deg, #f0dcae 0%, var(--gold) 45%, #8a6c33 80%, #c9a45c 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  filter: drop-shadow(0 2px 14px rgba(201, 164, 92, .18));
}

.site-latin {
  margin: 10px 0 0;
  font-family: var(--font-black-letter);
  font-size: clamp(17px, 3vw, 24px);
  letter-spacing: .34em;
  text-indent: .34em;
  color: var(--silver);
  opacity: .85;
}

.rule {
  display: flex; align-items: center; gap: 14px;
  max-width: 460px; margin: 22px auto 14px;
  color: var(--gold);
}
.rule::before, .rule::after {
  content: ""; flex: 1; height: 1px;
  background: linear-gradient(90deg, transparent, var(--line));
}
.rule::after { background: linear-gradient(90deg, var(--line), transparent); }
.rule .orn { font-size: 14px; opacity: .9; }

.tagline {
  margin: 0 auto;
  max-width: 560px;
  color: var(--text-dim);
  font-size: 14.5px;
  letter-spacing: .14em;
}

/* ── 收录计数 ── */
.archive-count {
  text-align: center;
  margin: 44px 0 26px;
  font-family: var(--font-caps);
  font-size: 13px;
  letter-spacing: .45em;
  text-indent: .45em;
  color: var(--silver);
  text-transform: uppercase;
}

/* ── 文章卡片 ── */
.card {
  position: relative;
  display: block;
  margin: 0 0 22px;
  padding: 26px 30px 24px;
  background: linear-gradient(160deg, var(--panel) 0%, var(--panel-2) 100%);
  border: 1px solid var(--line);
  color: var(--text);
  transition: transform .3s ease, border-color .3s ease, box-shadow .3s ease;
}
.card::before {
  content: "";
  position: absolute; top: -1px; left: 12%; right: 12%; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(201, 164, 92, .55), transparent);
}
.card:hover {
  transform: translateY(-3px);
  border-color: rgba(201, 164, 92, .5);
  box-shadow: 0 10px 34px rgba(0, 0, 0, .55), 0 0 24px rgba(138, 31, 43, .14);
  color: var(--text);
}

.card h2 {
  margin: 0 0 8px;
  font-size: 23px;
  font-weight: 900;
  letter-spacing: .06em;
  line-height: 1.5;
  color: #e6d9bd;
}
.card:hover h2 { color: var(--gold-bright); }

.card .meta {
  font-family: var(--font-caps);
  font-size: 11.5px;
  letter-spacing: .22em;
  color: var(--silver);
  opacity: .8;
  margin-bottom: 12px;
}
.card .meta .sep { color: var(--blood-bright); padding: 0 7px; }

.card .excerpt {
  margin: 0;
  color: var(--text-dim);
  font-size: 15px;
  line-height: 1.95;
  text-align: justify;
}

.card .enter {
  display: inline-block;
  margin-top: 14px;
  font-family: var(--font-caps);
  font-size: 12px;
  letter-spacing: .3em;
  color: var(--gold);
}
.card:hover .enter { color: var(--blood-bright); }

/* ── 文章页 ── */
.back {
  display: inline-block;
  margin: 40px 0 6px;
  font-family: var(--font-caps);
  font-size: 12.5px;
  letter-spacing: .28em;
  color: var(--silver);
}
.back:hover { color: var(--gold-bright); }

.post-header { text-align: center; padding: 26px 0 8px; }
.post-header h1 {
  margin: 0;
  font-size: clamp(28px, 5.4vw, 40px);
  font-weight: 900;
  letter-spacing: .08em;
  line-height: 1.5;
  color: #efe3c6;
  text-shadow: 0 2px 18px rgba(201, 164, 92, .15);
}
.post-header .meta {
  margin-top: 14px;
  font-family: var(--font-caps);
  font-size: 12px;
  letter-spacing: .26em;
  color: var(--silver);
}
.post-header .meta .sep { color: var(--blood-bright); padding: 0 8px; }

.post-rule {
  text-align: center;
  color: var(--gold);
  margin: 26px 0 34px;
  letter-spacing: .8em;
  text-indent: .8em;
  font-size: 13px;
  opacity: .8;
}

.content { max-width: 760px; margin: 0 auto; }
.content p { margin: 0 0 1.35em; text-align: justify; }
.content p.lead::first-letter {
  float: left;
  font-size: 2.9em;
  line-height: 1;
  padding: 4px 10px 0 0;
  color: var(--blood-bright);
  font-weight: 900;
  text-shadow: 0 0 18px rgba(192, 48, 63, .35);
}

.content h2, .content h3, .content h4 {
  font-weight: 900;
  letter-spacing: .08em;
  color: #e6d9bd;
  margin: 2.2em 0 1em;
}
.content h2 {
  font-size: 24px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
  position: relative;
}
.content h2::after {
  content: "";
  position: absolute; left: 0; bottom: -1px;
  width: 74px; height: 1px;
  background: linear-gradient(90deg, var(--gold), transparent);
}
.content h3 { font-size: 20px; }

.content a { border-bottom: 1px dotted rgba(201, 164, 92, .5); }
.content a:hover { border-bottom-color: var(--blood-bright); }

.content blockquote {
  margin: 1.8em 0;
  padding: 14px 22px;
  border-left: 3px solid var(--gold);
  background: rgba(201, 164, 92, .05);
  color: var(--text-dim);
  font-size: 15.5px;
}
.content blockquote p { margin: .3em 0; }

.content img {
  display: block;
  max-width: 100%;
  margin: 2em auto;
  border: 1px solid var(--line);
  padding: 6px;
  background: #0c0a11;
  box-shadow: 0 8px 30px rgba(0, 0, 0, .6);
}

.content em { color: var(--silver); }
.content strong { color: #e6d9bd; }
.content hr {
  border: none;
  text-align: center;
  margin: 2.6em 0;
}
.content hr::after {
  content: "✠ ─── ✠ ─── ✠";
  color: var(--line);
  letter-spacing: .4em;
  font-size: 12px;
}

.content ol, .content ul { padding-left: 1.6em; }
.content li { margin-bottom: .45em; }
.content li::marker { color: var(--gold); }

.content code {
  background: #16121d;
  border: 1px solid var(--line);
  padding: 2px 6px;
  font-size: .9em;
  color: var(--gold-bright);
}
.content pre {
  background: #0c0a11;
  border: 1px solid var(--line);
  padding: 16px 18px;
  overflow-x: auto;
}
.content pre code { border: none; background: none; padding: 0; }

.content table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.8em 0;
  font-size: 15px;
}
.content th, .content td {
  border: 1px solid var(--line);
  padding: 8px 12px;
  text-align: left;
}
.content th { color: var(--gold); background: rgba(201, 164, 92, .06); }

/* ── 页脚 ── */
.site-footer {
  margin-top: 80px;
  padding: 34px 0 46px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
  letter-spacing: .12em;
  border-top: 1px solid #1a1620;
}
.site-footer .orn { color: var(--blood-bright); }
.site-footer a { color: var(--silver); border-bottom: 1px dotted #443c52; }
.site-footer a:hover { color: var(--gold-bright); }

@media (max-width: 620px) {
  body { font-size: 16px; }
  .card { padding: 20px 18px; }
  .content p:first-of-type::first-letter { font-size: 2.4em; }
}
"""

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
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90' fill='%23c9a45c'%3E%E2%9C%A0%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Pirata+One&family=Cinzel:wght@400;600&family=Noto+Serif+SC:wght@400;600;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="__CSS__">
</head>
<body>
"""

HEADER_TMPL = """
<header class="site-header">
  <div class="sigil">✠ ✠ ✠</div>
  <h1 class="site-title"><a href="__HOME__" style="color:inherit;-webkit-text-fill-color:inherit;">__SITENAME__</a></h1>
  <p class="site-latin">__SITELATIN__</p>
  <div class="rule"><span class="orn">☾ ✠ ☽</span></div>
  <p class="tagline">__TAGLINE__</p>
</header>
"""

FOOTER_TMPL = """
<footer class="site-footer">
  <div><span class="orn">✠</span>&nbsp;&nbsp;__SITENAME__ · __YEAR__&nbsp;&nbsp;<span class="orn">✠</span></div>
  <div style="margin-top:8px;">手稿存于 <a href="__GITHUB__" target="_blank" rel="noopener">GitHub</a> · 由 GitHub Actions 铸造</div>
</footer>
</body>
</html>
"""

INDEX_CARD_TMPL = """
<a class="card" href="posts/__SLUG__.html">
  <h2>__TITLE__</h2>
  <div class="meta">__DATE__<span class="sep">✠</span>约 __WORDS__ 字<span class="sep">✠</span>阅读约 __MINUTES__ 分钟</div>
  <p class="excerpt">__EXCERPT__</p>
  <span class="enter">推开此门 ▸</span>
</a>
"""

POST_TMPL = """
<main class="container">
  <a class="back" href="../index.html">◂ 返回__SITENAME__</a>
  <div class="post-header">
    <h1>__TITLE__</h1>
    <div class="meta">__DATE__<span class="sep">✠</span>约 __WORDS__ 字<span class="sep">✠</span>阅读约 __MINUTES__ 分钟</div>
  </div>
  <div class="post-rule">✠ ── ☾ ── ✠</div>
  <article class="content">
__BODY__
  </article>
</main>
"""


def fill(tmpl: str, **kw) -> str:
    for k, v in kw.items():
        tmpl = tmpl.replace("__" + k + "__", str(v))
    return tmpl


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


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    POSTS_OUT.mkdir(parents=True)

    # 图片目录整体拷贝
    if (ROOT / "images").exists():
        shutil.copytree(ROOT / "images", OUT / "images", dirs_exist_ok=True)

    (OUT / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")

    articles = collect_articles()
    year = datetime.now().year

    footer = fill(FOOTER_TMPL, SITENAME=SITE_NAME, YEAR=year, GITHUB=SITE_GITHUB)

    # ── 文章页 ──
    for a in articles:
        body = render_body(a["text"], a["title"])
        page = fill(HEAD_TMPL,
                    TITLE=html.escape(a["title"]) + " · " + SITE_NAME,
                    DESC=html.escape(a["excerpt"][:80]),
                    OGTYPE="article",
                    CSS="../style.css")
        page += fill(POST_TMPL,
                     SITENAME=SITE_NAME,
                     TITLE=html.escape(a["title"]),
                     DATE=a["date"].strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月"),
                     WORDS=f"{a['words']:,}",
                     MINUTES=a["minutes"],
                     BODY=body)
        page += footer
        (POSTS_OUT / f"{a['slug']}.html").write_text(page, encoding="utf-8")

    # ── 首页 ──
    cards = "".join(
        fill(INDEX_CARD_TMPL,
             SLUG=a["slug"],
             TITLE=html.escape(a["title"]),
             DATE=a["date"].strftime("%Y年%m月%d日").replace("年0", "年").replace("月0", "月"),
             WORDS=f"{a['words']:,}",
             MINUTES=a["minutes"],
             EXCERPT=html.escape(a["excerpt"]))
        for a in articles
    )
    index = fill(HEAD_TMPL,
                 TITLE=f"{SITE_NAME} · {SITE_LATIN}",
                 DESC=html.escape(SITE_TAGLINE),
                 OGTYPE="website",
                 CSS="style.css")
    index += fill(HEADER_TMPL, SITENAME=SITE_NAME, SITELATIN=SITE_LATIN,
                  TAGLINE=SITE_TAGLINE, HOME="index.html")
    index += f'<main class="container">\n<div class="archive-count">共收录 {len(articles)} 篇手稿</div>\n{cards}\n</main>\n'
    index += footer
    (OUT / "index.html").write_text(index, encoding="utf-8")

    print(f"[build] 生成 {len(articles)} 篇文章 → {OUT}")
    for a in articles:
        print(f"  - {a['date']:%Y-%m-%d}  {a['title']}  ({a['words']}字)  posts/{a['slug']}.html")


if __name__ == "__main__":
    build()
