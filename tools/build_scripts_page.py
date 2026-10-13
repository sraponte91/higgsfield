"""Build the scripts hub page (one card per video, click for the full script) from scripts/FF-short-form-scripts.md.

Usage: python tools/build_scripts_page.py [out.html]      (needs the `markdown` package)
"""
import html
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'scripts' / 'FF-short-form-scripts.md'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'scripts' / 'ff-scripts-hub.html'
WPS = 2.8                                   # spoken words per second, for running-time estimates

md = markdown.Markdown(extensions=['tables', 'sane_lists'])


def strike(text):
    return re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)


def block(text):
    md.reset()
    out = md.convert(strike(text))
    # <details> blocks: render their inside as Markdown too
    return out


def inline(text):
    md.reset()
    out = md.convert(strike(text.strip()))
    return re.sub(r'^<p>(.*)</p>$', r'\1', out, flags=re.S)


def render_md(text):
    """Markdown with <details><summary>…</summary> … </details> blocks rendered inside."""
    parts = re.split(r'(<details>\s*<summary>.*?</summary>.*?</details>)', text, flags=re.S)
    out = []
    for p in parts:
        m = re.match(r'<details>\s*<summary>(.*?)</summary>(.*)</details>', p, flags=re.S)
        if m:
            out.append(f'<details class="orig"><summary>{inline(m.group(1))}</summary><div class="md">{block(m.group(2))}</div></details>')
        elif p.strip():
            out.append(f'<div class="md">{block(p)}</div>')
    return '\n'.join(out)


def words(text):
    text = re.sub(r'~~.*?~~', '', text)
    text = re.sub(r'\*\(.*?\)\*', '', text)
    return len(re.findall(r"[A-Za-z0-9'’]+", text))


SCENE = re.compile(r'^\*\*(\d+[A-Z]?)\. ([^*]+)\*\*\s*(.*)$')


def kind_of(rest, name):
    r = (rest + ' ' + name).lower()
    if '[camera]' in r or '(camera' in r:
        return 'cam'
    if '[screen]' in r or 'screen recording' in r:
        return 'scr'
    if 'animation' in r:
        return 'anim'
    return 'scr'


def parse_screenplay(text):
    lines = text.strip('\n').split('\n')
    pre, scenes, extra = [], [], []
    cur = None
    for ln in lines:
        m = SCENE.match(ln)
        if m:
            cur = {'n': m.group(1), 'name': m.group(2).strip(), 'rest': m.group(3).strip(), 'pic': [], 'dlg': [], 'speaker': ''}
            scenes.append(cur)
            continue
        if ln.startswith('**') and not m and scenes:          # a block after the scenes (e.g. "**Looping option**")
            cur = None
        if cur is None:
            (extra if scenes else pre).append(ln)
            continue
        if ln.startswith('>'):
            t = ln[1:].strip()
            sm = re.match(r'^(EMILIANN(?: \(VO\))?):\s*(.*)$', t)
            if sm:
                cur['speaker'] = sm.group(1)
                t = sm.group(2)
            cur['dlg'].append(t)
        elif ln.strip():
            cur['pic'].append(ln.strip())
    for s in scenes:
        paras, buf = [], []
        for t in s['dlg']:
            if t:
                buf.append(t)
            elif buf:
                paras.append(' '.join(buf)); buf = []
        if buf:
            paras.append(' '.join(buf))
        s['paras'] = paras
        s['kind'] = kind_of(s['rest'], s['name'])
        s['words'] = sum(words(p) for p in paras)
        s['secs'] = s['words'] / WPS if s['words'] else 2.0
    return '\n'.join(pre), scenes, '\n'.join(extra)


def parse_index(text):
    rows = {}
    for ln in text.split('\n'):
        m = re.match(r'^\| \[(\d{3})\]\(.*?\) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|$', ln)
        if m:
            rows[m.group(1)] = {'location': m.group(6).strip()}
    return rows


def status_class(status):
    s = status.lower()
    if 'skip' in s:
        return 'skip', 'Skip for now'
    if 'ready' in s:
        return 'ready', 'Ready to shoot'
    if 'in post' in s:
        return 'post', 'In post'
    return 'spec', 'Spec'


src = SRC.read_text()
index = parse_index(src)
gspec = src[src.index('## Global spec'):]
gspec = gspec[gspec.index('\n') + 1:gspec.index('\n---', 1)]
videos = []
for chunk in re.split(r'\n(?=## Video )', src)[1:]:
    head, body = chunk.split('\n', 1)
    m = re.match(r'## Video (\d{4})-(\d{3}): (.*)', head)
    year, num, title = m.groups()
    title = re.sub(r'\s*\(skip for now\)$', '', title, flags=re.I)
    body = body.rsplit('\n---', 1)[0] if body.rstrip().endswith('---') else body
    status = re.search(r'^\*\*Status:\*\* (.*)$', body, flags=re.M).group(1)
    tl = re.search(r'^\*\*Target length:\*\* (.*)$', body, flags=re.M)
    sp_m = re.search(r'^### Screenplay[^\n]*\n(.*?)(?=^### )', body, flags=re.S | re.M)
    sp_title = re.search(r'^### (Screenplay[^\n]*)', body, flags=re.M).group(1)
    pre, scenes, extra = parse_screenplay(sp_m.group(1))
    rest = body[sp_m.end():]
    secs = sum(s['secs'] for s in scenes)
    hook = next((s['paras'][0] for s in scenes if s['paras']), '')
    videos.append(dict(id=num, code=f'{year}-{num}', title=title, status=status, tl=tl.group(1) if tl else '',
                       sp_title=sp_title, pre=pre, scenes=scenes, extra=extra, rest=rest, secs=secs,
                       words=sum(s['words'] for s in scenes), hook=hook,
                       location=index.get(num, {}).get('location', '')))

KIND = {'cam': 'Camera', 'scr': 'Screen', 'anim': 'Animation'}


def card(v):
    cls, label = status_class(v['status'])
    kinds = [s['kind'] for s in v['scenes']]
    strip = ''.join(f'<i class="k-{s["kind"]}" style="flex:{s["secs"]:.1f}"></i>' for s in v['scenes'])
    return f'''<a class="card s-{cls}" href="#v{v['id']}">
  <div class="card-top"><span class="code">{v['code']}</span><span class="chip c-{cls}">{label}</span></div>
  <h3>{html.escape(v['title'])}</h3>
  <p class="hook">“{inline(v['hook'])}”</p>
  <div class="mini">{strip}</div>
  <div class="card-meta"><span>~{round(v['secs'])} s</span><span>{kinds.count('cam')} camera</span><span>{kinds.count('scr')} screen</span>{'<span>' + str(kinds.count('anim')) + ' animation</span>' if 'anim' in kinds else ''}</div>
</a>'''


def scene_html(s):
    pic = []
    if s['rest']:
        r = re.sub(r'`\[(CAMERA|SCREEN)\]`\s*', '', s['rest']).strip()
        r = re.sub(r'^\((.*)\)$', r'\1', r)
        if r and r.lower() not in ('camera', 'screen recording', 'animation', 'camera, same setup as 1'):
            pic.append(f'<p>{inline(r[0].upper() + r[1:])}</p>')
        elif r.lower() == 'camera, same setup as 1':
            pic.append('<p class="dim">Same setup as 1</p>')
    pic += [f'<p>{inline(p)}</p>' for p in s['pic']]
    if s['paras']:
        spk = s['speaker'] or 'EMILIANN'
        spk = spk.replace(' (VO)', ' <small>(voice-over)</small>')
        snd = f'<div class="speaker">{spk}</div>' + ''.join(f'<p class="line">{inline(p)}</p>' for p in s['paras'])
        snd += f'<div class="dur">~{s["secs"]:.0f} s · {s["words"]} words</div>'
    else:
        snd = '<p class="dim">No dialogue</p><div class="dur">~2 s</div>'
    return f'''<div class="scene">
  <div class="pic"><div class="slug"><span class="n">{s['n']}</span><h4>{html.escape(s['name'].title())}</h4><span class="tag t-{s['kind']}">{KIND[s['kind']]}</span></div>{''.join(pic)}</div>
  <div class="snd">{snd}</div>
</div>'''


def detail(v, prev, nxt):
    cls, label = status_class(v['status'])
    strip = ''.join(f'<div class="seg k-{s["kind"]}" style="flex:{s["secs"]:.1f}" title="{html.escape(s["name"].title())}">{html.escape(s["name"].title())}</div>' for s in v['scenes'])
    status_note = re.sub(r'^[^.]*\.\s*', '', v['status'])
    nav = (f'<a href="#v{prev["id"]}">← {prev["code"]}</a>' if prev else '<span></span>') + \
          (f'<a href="#v{nxt["id"]}">{nxt["code"]} →</a>' if nxt else '<span></span>')
    return f'''<article class="view" id="view-v{v['id']}" hidden>
  <div class="topbar"><a class="back" href="#all">← All videos</a><div class="pn">{nav}</div></div>
  <header class="vhead">
    <div class="eyebrow">Video {v['code']}</div>
    <h2>{html.escape(v['title'])}</h2>
    <div class="meta"><span class="chip c-{cls}">{label}</span><span>Running time <b>~{round(v['secs'])} s</b></span><span>Voice <b>{v['words']} words</b></span><span>Scenes <b>{len(v['scenes'])}</b></span>{f'<span>Location <b>{html.escape(v["location"])}</b></span>' if v['location'] else ''}</div>
    {f'<p class="note">{inline(status_note)}</p>' if status_note and status_note != v['status'] else ''}
  </header>
  <div class="strip"><div class="bar">{strip}</div><div class="ticks"><span>0 s</span><span>~{round(v['secs'])} s</span></div></div>
  <h3 class="sec">{html.escape(v['sp_title'])}</h3>
  {f'<div class="pre">{render_md(v["pre"])}</div>' if v['pre'].strip() else ''}
  <section class="script"><div class="av-head"><div>Picture</div><div>Sound</div></div>{''.join(scene_html(s) for s in v['scenes'])}</section>
  {f'<div class="extra">{render_md(v["extra"])}</div>' if v['extra'].strip() else ''}
  <div class="rest">{render_md(v['rest'])}</div>
  <div class="bottomnav pn">{nav}</div>
</article>'''


CSS = r'''
/* Layout: a contact sheet of video cards; each opens a two-column AV script (picture | sound). */
:root {
  --bg: #f4f5f3; --paper: #ffffff; --fg: #17201c; --muted: #5d6a63; --rule: #dfe3df;
  --accent: #2b8a3e;
  --cam: #c4610f; --cam-soft: #fbeadb;
  --scr: #3d5a80; --scr-soft: #e3eaf3;
  --anim: #7b4fa0; --anim-soft: #efe6f6;
  --spec: #8a6d00; --spec-soft: #f8f0cf;
  --skip: #6b6f6d; --skip-soft: #e8eae9;
  --font-display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --font-body: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --font-line: "Courier Prime", "Courier New", Courier, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #121614; --paper: #1a1f1c; --fg: #e8ece9; --muted: #9aa69f; --rule: #2c3430; --accent: #5cc46f;
    --cam: #f0954a; --cam-soft: #3a2616; --scr: #8fb0d8; --scr-soft: #1f2a38; --anim: #c49ae6; --anim-soft: #2e2238;
    --spec: #e3c45a; --spec-soft: #33300f; --skip: #a3a8a5; --skip-soft: #272b29; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #121614; --paper: #1a1f1c; --fg: #e8ece9; --muted: #9aa69f; --rule: #2c3430; --accent: #5cc46f;
  --cam: #f0954a; --cam-soft: #3a2616; --scr: #8fb0d8; --scr-soft: #1f2a38; --anim: #c49ae6; --anim-soft: #2e2238;
  --spec: #e3c45a; --spec-soft: #33300f; --skip: #a3a8a5; --skip-soft: #272b29; color-scheme: dark;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.55; }
a { color: var(--accent); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { max-width: 1000px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 64px; }
.view { display: grid; gap: 26px; }
.view[hidden] { display: none; }
.eyebrow { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); font-weight: 600; }
h1, h2 { font-family: var(--font-display); font-weight: 800; line-height: 1.1; margin: 0; text-wrap: balance; }
h1 { font-size: clamp(28px, 5vw, 40px); }
h2 { font-size: clamp(24px, 4.4vw, 34px); }
.home-head, .vhead { display: grid; gap: 10px; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }
.meta b { color: var(--fg); font-weight: 600; }
.note { margin: 0; color: var(--muted); font-size: 14px; max-width: 70ch; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px; }
.card { display: grid; gap: 10px; align-content: start; background: var(--paper); border: 1px solid var(--rule); border-radius: 10px; padding: 16px; color: inherit; text-decoration: none; transition: border-color .15s, transform .15s; }
.card:hover { border-color: var(--accent); transform: translateY(-2px); }
.card.s-skip { opacity: .65; }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.code { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--muted); font-size: 13px; }
.card h3 { margin: 0; font-size: 18px; font-weight: 800; line-height: 1.25; text-wrap: balance; }
.hook { margin: 0; font-family: var(--font-line); font-size: 14px; line-height: 1.45; color: var(--fg); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.mini { display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 2px; }
.mini i { display: block; min-width: 3px; }
.card-meta { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.k-cam { background: var(--cam-soft); color: var(--cam); }
.k-scr { background: var(--scr-soft); color: var(--scr); }
.k-anim { background: var(--anim-soft); color: var(--anim); }
.mini .k-cam { background: var(--cam); } .mini .k-scr { background: var(--scr); } .mini .k-anim { background: var(--anim); }

.chip { display: inline-block; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.c-ready { background: var(--accent); color: var(--paper); }
.c-post { background: var(--scr-soft); color: var(--scr); }
.c-spec { background: var(--spec-soft); color: var(--spec); }
.c-skip { background: var(--skip-soft); color: var(--skip); }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
.tag { display: inline-block; font-size: 11px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; padding: 2px 8px; border-radius: 4px; }
.t-cam { background: var(--cam-soft); color: var(--cam); }
.t-scr { background: var(--scr-soft); color: var(--scr); }
.t-anim { background: var(--anim-soft); color: var(--anim); }

.topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.back { font-weight: 600; text-decoration: none; }
.pn { display: flex; gap: 16px; }
.pn a { text-decoration: none; font-weight: 600; font-variant-numeric: tabular-nums; }
.bottomnav { justify-content: space-between; border-top: 1px solid var(--rule); padding-top: 16px; }

.strip { display: grid; gap: 6px; }
.bar { display: flex; height: 32px; border-radius: 6px; overflow: hidden; border: 1px solid var(--rule); }
.seg { display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; border-right: 1px solid var(--paper); padding-inline: 4px; }
.seg:last-child { border-right: 0; }
.ticks { display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }

h3.sec, .md h3 { font-family: var(--font-display); font-size: 19px; font-weight: 800; margin: 0; }
.script { background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; }
.av-head, .scene { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); }
.av-head { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--rule); }
.av-head div { padding: 10px 20px; }
.scene + .scene { border-top: 1px solid var(--rule); }
.pic, .snd { padding: 16px 20px; min-width: 0; display: grid; gap: 8px; align-content: start; }
.pic { border-right: 1px solid var(--rule); }
.slug { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.slug .n { font-variant-numeric: tabular-nums; color: var(--muted); font-weight: 600; }
.slug h4 { margin: 0; font-size: 15px; font-weight: 800; letter-spacing: .02em; text-transform: uppercase; }
.pic p { margin: 0; color: var(--muted); font-size: 14px; }
.dim { color: var(--muted); font-size: 14px; margin: 0; }
.speaker { font-family: var(--font-line); font-weight: 700; font-size: 13px; letter-spacing: .06em; }
.speaker small { font-weight: 400; color: var(--muted); letter-spacing: 0; }
.line { font-family: var(--font-line); font-size: 17px; line-height: 1.5; margin: 0; }
.line del { color: var(--muted); }
.dur { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }

.md { display: grid; gap: 12px; max-width: 80ch; }
.md p, .md ul, .md ol { margin: 0; }
.md ul, .md ol { padding-left: 20px; display: grid; gap: 5px; }
.md blockquote { margin: 0; padding-left: 12px; border-left: 2px solid var(--rule); font-family: var(--font-line); }
.md code { font-size: .92em; background: var(--scr-soft); color: var(--scr); padding: 1px 5px; border-radius: 3px; }
.md table { border-collapse: collapse; font-size: 14px; }
.md th, .md td { border-bottom: 1px solid var(--rule); padding: 6px 10px; text-align: left; vertical-align: top; }
.rest, .extra, .pre { display: grid; gap: 18px; }
.rest h3 { padding-top: 6px; }
details { background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; }
summary { cursor: pointer; padding: 12px 16px; font-weight: 600; }
details > .md { padding: 0 16px 16px; }

@media (max-width: 640px) {
  .scene, .av-head { grid-template-columns: minmax(0, 1fr); }
  .av-head { display: none; }
  .pic { border-right: 0; padding-bottom: 4px; }
  .snd { padding-top: 4px; }
  .seg { font-size: 0; }
}
@media (prefers-reduced-motion: reduce) { .card { transition: none; } .card:hover { transform: none; } }
'''

JS = r'''
(function () {
  function show() {
    var id = (location.hash || '').slice(1);
    var target = document.getElementById('view-' + id);
    if (!target) target = document.getElementById('view-all');
    document.querySelectorAll('.view').forEach(function (v) { v.hidden = v !== target; });
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', show);
  show();
})();
'''

total = len(videos)
ready = sum(status_class(v['status'])[0] == 'ready' for v in videos)
page = f'''<title>FF Short-Form Scripts</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;800&family=Courier+Prime:wght@400;700&display=swap">
<style>{CSS}</style>
<div class="wrap">
<section class="view" id="view-all">
  <header class="home-head">
    <div class="eyebrow">Forex Factory · Short-form instructional videos</div>
    <h1>Video scripts</h1>
    <div class="meta"><span>Videos <b>{total}</b></span><span>Ready to shoot <b>{ready}</b></span><span>Presenter <b>Emiliann</b></span><span>Format <b>9:16</b></span></div>
    <div class="legend"><span><span class="tag t-cam">Camera</span> Emiliann on screen</span><span><span class="tag t-scr">Screen</span> phone screen, her voice over it</span><span><span class="tag t-anim">Animation</span></span></div>
  </header>
  <div class="grid">{''.join(card(v) for v in videos)}</div>
  <details><summary>Global spec (applies to every video)</summary><div class="md">{block(gspec)}</div></details>
</section>
{''.join(detail(v, videos[i - 1] if i else None, videos[i + 1] if i + 1 < total else None) for i, v in enumerate(videos))}
</div>
<script>{JS}</script>
'''
OUT.write_text(page)

# Standalone copy for static hosting (e.g. Netlify Drop): a full HTML document, not indexed by search engines.
DEPLOY = ROOT / 'deploy' / 'ff-scripts'
DEPLOY.mkdir(parents=True, exist_ok=True)
head, body = page.split('<div class="wrap">', 1)
(DEPLOY / 'index.html').write_text(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<meta name="robots" content="noindex, nofollow">\n'
    '<style>body{margin:0} img{max-width:100%} [hidden]{display:none!important}</style>\n'
    + head + '</head>\n<body>\n<div class="wrap">' + body + '</body>\n</html>\n')
print(f'{DEPLOY / "index.html"}')
print(f'{OUT}: {total} videos, {len(page) // 1024} KB')
for v in videos:
    print(v['code'], len(v['scenes']), 'scenes', round(v['secs']), 's', [s['kind'] for s in v['scenes']])
