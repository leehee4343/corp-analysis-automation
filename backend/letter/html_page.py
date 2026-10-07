"""공문(HTML): 기업 담당자에게 보내는 반응형 공문 화면 (/l/{code}, 로그인 없이 열림).

- 넓은 화면·인쇄: A4 공문과 같은 2쪽 배치 / 휴대폰: 한 줄 배치(지표 2열, 점검 결과는 항목별 카드)
- 기업별 값은 generator.build_letter_data(PPTX·이미지와 같은 계산), 고정 문구·아이콘은 공문 템플릿에서 읽는다
  (템플릿 읽기는 mobile.py와 공유)
- 상단 도구: 인쇄, URL 복사(이 화면의 짧은 주소)
"""
from __future__ import annotations

import base64
import io
import math
from functools import lru_cache
from html import escape

from . import generator as g
from . import mobile as m

FONT_CSS = "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"


def _e(s) -> str:
    return escape(str(s), quote=True)


def _runs_html(runs) -> str:
    """템플릿 문단의 run → span. 굵은 글씨는 strong, 기본 본문색이 아니면 색을 지정한다."""
    out = []
    for text, bold, color in runs:
        style = f' style="color:{color}"' if color.upper() not in (m.TEXT, "#2A3240", "#1E2430") else ""
        tag = "strong" if bold else "span"
        out.append(f"<{tag}{style}>{_e(text)}</{tag}>")
    return "".join(out)


def _paras_html(si, name, cls="") -> str:
    return "".join(f'<p class="{cls}">{_runs_html(p)}</p>' for p in m._paras(si, name))


@lru_cache(maxsize=8)
def _img(si: int, name: str) -> str:
    blob = m._template()[(si, name)].image.blob
    return "data:image/png;base64," + base64.b64encode(blob).decode()


@lru_cache(maxsize=1)
def _sprouts_uri() -> str:
    buf = io.BytesIO()
    m._sprouts(120).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def radar_svg(d: g.LetterData) -> str:
    cx, cy, r, n = 160, 128, 82, len(d.radar)

    def pt(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * frac * math.cos(ang), cy + r * frac * math.sin(ang)

    def poly(points):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    parts = [f'<svg class="radar" viewBox="0 0 320 262" role="img" aria-label="재무진단 5개 항목 그래프">']
    for frac in (0.25, 0.5, 0.75, 1.0):
        parts.append(f'<polygon points="{poly(pt(i, frac) for i in range(n))}" fill="none" stroke="#D5DCE5" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, 1)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#E3E8EF" stroke-width="1"/>')
    has = any(a.score for a in d.radar)
    if has:
        comp = [pt(i, a.score / 100) for i, a in enumerate(d.radar)]
        parts.append(f'<polygon points="{poly(comp)}" fill="rgba(30,140,90,.14)" stroke="none"/>')
    avg = [pt(i, g.INDUSTRY_AVG_SCORE / 100) for i in range(n)]
    parts.append(f'<polygon points="{poly(avg)}" fill="none" stroke="{m.PURPLE}" stroke-width="2" stroke-dasharray="5 4"/>')
    parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{m.PURPLE}"/>' for x, y in avg]
    if has:
        parts.append(f'<polygon points="{poly(comp)}" fill="none" stroke="{m.GREEN}" stroke-width="3" stroke-linejoin="round"/>')
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{m.GREEN}"/>' for x, y in comp]
    for i, a in enumerate(d.radar):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        x, y = cx + (r + 20) * math.cos(ang), cy + (r + 20) * math.sin(ang)
        anchor = "middle" if abs(math.cos(ang)) < 0.3 else ("start" if math.cos(ang) > 0 else "end")
        if i == 0:
            y -= 12
        parts.append(f'<text x="{x:.1f}" y="{y - 3:.1f}" text-anchor="{anchor}" class="ax">{_e(a.label)}</text>'
                     f'<text x="{x:.1f}" y="{y + 13:.1f}" text-anchor="{anchor}" class="gr">({_e(a.grade or "자료없음")})</text>')
    if not has:
        parts.append(f'<rect x="{cx - 70}" y="{cy - 15}" width="140" height="30" rx="8" fill="#fff" stroke="#DDE5EE"/>'
                     f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" class="ax" fill="{m.MUTED}">재무진단 자료 없음</text>')
    parts.append("</svg>")
    return "".join(parts)


def _judge_pill(judgment: str) -> str:
    fill, color, label = g.JUDGE_STYLE[judgment]
    return f'<span class="pill" style="background:#{fill};color:#{color}">{_e(label)}</span>'


def render_letter_html(d: g.LetterData, *, expires_text: str) -> str:
    t = m._text
    kpi1 = "".join(
        f'<div class="kcard"><div class="kl">{_e(t(1, a))}</div><div class="kv" style="color:{m._paras(1, b)[0][0][2]}">{_e(t(1, b))}</div>'
        f'<div class="ks">{_e(t(1, c))}</div></div>'
        for a, b, c in (("Text 23", "Text 24", "Text 25"), ("Text 27", "Text 28", "Text 29"),
                        ("Text 31", "Text 32", "Text 33"), ("Text 35", "Text 36", "Text 37")))
    info_rows = "".join(f'<div class="ir"><div class="il">{_runs_html(row[0])}</div><div class="iv">{_runs_html(row[1])}</div></div>'
                        for row in m._table(1, "Table 0"))
    kpi2 = "".join(
        f'<div class="fcard{" wide" if i == 4 else ""}"><div class="fl">{_e(k.label)}</div>'
        f'<div class="fv" style="color:#{k.color}">{_e(k.value)}'
        f'{f"<small>{_e(k.unit)}</small>" if k.unit and k.value != "-" else ""}</div><div class="fs">{_e(k.sub)}</div></div>'
        for i, k in enumerate(d.kpis))
    counts = "".join(f'<span class="pill" style="background:#{g.JUDGE_STYLE[k][0]};color:#{g.JUDGE_STYLE[k][1]}">'
                     f'{sym} {_e(k)} {d.counts[k]}</span>' for k, sym in (("충족", "✓"), ("확인 필요", "?"), ("보완 필요", "!")))
    checks = "".join(
        f'<div class="ck" style="--jc:#{g.JUDGE_STYLE[c.judgment][1]}"><div class="cl">{_e(c.label)}</div>'
        f'<div class="cs">{_e(c.status)}</div><div class="cj">{_judge_pill(c.judgment)}</div>'
        f'<div class="cn"><span class="m-only">다음 단계 </span>{_e(c.next_step)}</div></div>'
        for c in d.checks)
    vstyle = {"normal": "", "bold": "<strong>{}</strong>", "green": '<strong class="g">{}</strong>'}
    verdict = "".join((vstyle[s].format(_e(x)) if vstyle[s] else _e(x)) for x, s in d.verdict)
    steps = "".join(
        f'<div class="step"><div class="sh"><span class="sn">{_e(t(2, a))}</span><strong>{_e(t(2, b))}</strong></div>'
        f'<div class="sd">{_e(t(2, c))}</div><div class="sw">{_e(t(2, w))}</div></div>'
        for a, b, c, w in (("Text 65", "Text 66", "Text 67", "Text 68"), ("Text 72", "Text 73", "Text 74", "Text 75"),
                           ("Text 79", "Text 80", "Text 81", "Text 82"), ("Text 86", "Text 87", "Text 88", "Text 89")))
    contact = [x.strip() for x, _, _ in m._paras(2, "Text 91")[0]]
    if len(contact) >= 6:
        tel = contact[2]
        mobile_no = contact[4]
        contact_html = (f'<a href="tel:{_e(tel)}">전화 <strong>{_e(tel)}</strong></a>'
                        f'<a href="tel:{_e(mobile_no)}">{_e(contact[3])} <strong>{_e(mobile_no)}</strong></a>'
                        f'<span class="who">{_e(contact[5])}</span>')
    else:
        contact_html = f'<span>{_e(" ".join(contact[1:]))}</span>'
    slogan = "<br>".join(_e("".join(x for x, _, _ in p)) for p in m._paras(1, "Text 2"))
    scale = " · ".join(f'<span class="nw">{_e(k)} {v}</span>' for k, v in g.GRADE_SCORE.items())
    logo = (f'<div class="brand"><img src="{_img(1, "Image 0")}" alt=""><div><b>FARMSCOPE</b>'
            f'<span>AGRI BUSINESS PARTNER</span></div></div>')
    footer_brand = _runs_html(m._paras(1, "Text 40")[0])

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<title>{_e(d.name)} · {_e(t(1, "Text 11"))}</title>
<link rel="stylesheet" href="{FONT_CSS}">
<style>{CSS}</style>
</head>
<body>
<header class="toolbar">
  <div class="tb-in">
    <div class="tb-title"><b>FARMSCOPE</b> 공문 <span class="tb-exp">· {_e(expires_text)}까지 열람 가능</span></div>
    <div class="tb-btns">
      <button type="button" id="btnPrint" aria-label="인쇄"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/></svg><span>인쇄</span></button>
      <button type="button" id="btnCopy" class="primary" aria-label="URL 복사"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg><span>URL 복사</span></button>
    </div>
  </div>
</header>
<main class="doc">
<article class="page">
  <div class="head">{logo}<div class="slogan">{slogan}</div></div>
  <dl class="meta">
    <dt>문서번호</dt><dd>{_e(d.doc_no)}</dd>
    <dt>시행일자</dt><dd>{_e(d.issued_text)}</dd>
    <dt>수<i></i>신</dt><dd><strong>{_e(d.recipient_name)}</strong>{_e(d.recipient_suffix)}</dd>
    <dt>제<i></i>목</dt><dd class="title">{_e(t(1, "Text 11"))}</dd>
  </dl>
  <div class="intro">{_paras_html(1, "Text 13")}</div>
  <div class="promise"><img src="{_img(1, "Image 1")}" alt=""><div>{_paras_html(1, "Text 15")}</div></div>

  <section>
    <h2><span class="num">1</span>{_e(t(1, "Text 18"))}<small>{_e(t(1, "Text 19"))}</small></h2>
    <div class="banner" style="--sprouts:url('{_sprouts_uri()}')"><b>{_e(t(1, "Text 20"))}</b><span>{_e(t(1, "Text 21"))}</span></div>
    <div class="kgrid">{kpi1}</div>
    <div class="info">{info_rows}</div>
    <div class="notice"><img src="{_img(1, "Image 3")}" alt=""><div>{_paras_html(1, "Text 38")}</div></div>
  </section>
  <footer class="pfoot"><span>{footer_brand}</span><span>1 / 2</span></footer>
</article>

<article class="page">
  <div class="head">{logo}<div class="slogan doc-name">{_e(t(2, "Text 2"))}</div></div>
  <section>
    <h2><span class="num">2</span>{_e(t(2, "Text 6"))}<small>{_e(d.basis_text)}</small></h2>
    <div class="diag">
      <div class="profile"><b>{_e(d.name)}</b>
        <dl><dt>주요사업</dt><dd>{_e(d.industry)}</dd><dt>설립연도</dt><dd>{_e(d.founded_text)}</dd><dt>소재지</dt><dd>{_e(d.location)}</dd></dl>
      </div>
      <div class="chart">{radar_svg(d)}
        <div class="legend"><span><i class="ln"></i>{_e(d.name)}</span><span><i class="ln dash"></i>동종업종 평균</span></div>
        <div class="scale"><b>KODATA 등급 환산</b> {scale}</div>
      </div>
    </div>
    <div class="fgrid">{kpi2}</div>
  </section>
  <section>
    <h2><span class="num">3</span>{_e(t(2, "Text 44"))}<span class="counts">{counts}</span></h2>
    <div class="checks">
      <div class="ck th"><div>구분</div><div>귀사 현황</div><div>판정</div><div>다음 단계</div></div>
      {checks}
    </div>
    <div class="verdict"><span class="vl">종합 의견</span><p>{verdict}</p></div>
  </section>
  <section>
    <h2><span class="num">4</span>{_e(t(2, "Text 57"))}<small>{_e(t(2, "Text 58"))}</small></h2>
    <div class="onestop">
      <div class="os-head"><span class="os-tag">ONE-STOP</span><b>{_e(t(2, "Text 62"))}</b></div>
      <div class="steps">{steps}</div>
      <div class="contact"><img src="{_img(2, "Image 1")}" alt=""><b>문의</b>{contact_html}</div>
    </div>
  </section>
  <footer class="pfoot"><span>{_e(t(2, "Text 93"))}</span><span>{_e(d.issued_text)} <b>FARMSCOPE</b></span></footer>
</article>
</main>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>{JS}</script>
</body>
</html>"""


def render_message_html(title: str, message: str, status_label: str) -> str:
    """만료·없는 링크 안내 화면."""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>{_e(title)}</title><link rel="stylesheet" href="{FONT_CSS}">
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#F3F6FA;font-family:'Pretendard Variable',Pretendard,'Malgun Gothic',sans-serif;color:#1E2430;padding:16px;box-sizing:border-box}}
.box{{background:#fff;border:1px solid #DDE5EE;border-radius:14px;padding:32px 28px;max-width:420px;text-align:center}}
.box small{{display:inline-block;color:#6B7A8E;font-size:13px;margin-bottom:8px}}h1{{font-size:20px;color:#16325C;margin:0 0 10px}}p{{margin:0;line-height:1.7;color:#5A6B82}}</style>
</head><body><div class="box"><small>{_e(status_label)}</small><h1>{_e(title)}</h1><p>{_e(message)}</p></div></body></html>"""


CSS = """
:root{--navy:#16325C;--text:#1E2430;--sub:#5A6B82;--muted:#6B7A8E;--green:#1E8C5A;--dgreen:#1E4D3A;--orange:#B26A00;
  --light:#EEF3F8;--line:#DDE5EE;--card:#E2E8F0;--purple:#7A6FB8}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#F3F6FA;color:var(--text);font-family:'Pretendard Variable',Pretendard,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
  font-size:15px;line-height:1.65;word-break:keep-all;overflow-wrap:anywhere}
img{display:block}
p{margin:0}
/* 상단 도구 */
.toolbar{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-bottom:1px solid var(--line)}
.tb-in{max-width:840px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.tb-title{font-size:14px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tb-title b{color:var(--navy)}
.tb-btns{display:flex;gap:8px;flex-shrink:0}
.tb-btns button{display:inline-flex;align-items:center;gap:6px;height:38px;padding:0 14px;border:1px solid #CBD5E1;border-radius:8px;background:#fff;
  color:var(--navy);font:inherit;font-size:14px;cursor:pointer}
.tb-btns button.primary{background:var(--navy);border-color:var(--navy);color:#fff}
.tb-btns button:focus-visible{outline:3px solid #93C5FD;outline-offset:2px}
.tb-btns svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(20px);background:#1E2430;color:#fff;padding:10px 18px;border-radius:999px;
  font-size:14px;opacity:0;pointer-events:none;transition:.2s}
.toast.show{opacity:1;transform:translateX(-50%)}
/* 문서 */
.doc{max-width:840px;margin:0 auto;padding:16px 16px 40px}
.page{background:#fff;border-radius:14px;padding:22px 18px;margin-bottom:16px;border:1px solid var(--line)}
.head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding-bottom:14px;border-bottom:2px solid var(--navy)}
.brand{display:flex;align-items:center;gap:8px;flex-shrink:0}
.brand img{width:30px;height:30px}
.brand b{display:block;font-size:22px;letter-spacing:.5px;color:var(--navy);line-height:1.1}
.brand span{display:block;font-size:8.5px;letter-spacing:2.6px;color:var(--muted);font-weight:700}
.slogan{min-width:0;text-align:right;font-weight:700;color:var(--dgreen);font-size:13px;line-height:1.45}
.slogan.doc-name{color:var(--navy);font-size:12.5px}
.meta{display:grid;grid-template-columns:64px minmax(0,1fr);gap:6px 10px;margin:16px 0 0;padding-bottom:16px;border-bottom:1px solid var(--line)}
.meta dt{color:var(--sub);font-weight:700;display:flex;justify-content:space-between}
.meta dt i{flex:1;max-width:1.2em}
.meta dd{margin:0}
.meta dd.title{font-weight:700;color:var(--navy);font-size:16px}
.intro{margin:18px 0}
.intro p+p{margin-top:8px}
.promise{display:flex;gap:14px;align-items:center;background:#E9F4EC;border-radius:12px;padding:16px}
.promise img{width:44px;height:44px;flex-shrink:0}
.promise p:nth-child(-n+2){font-size:16.5px;line-height:1.5}
.promise p:last-child{font-size:13px;margin-top:4px}
section{margin-top:30px}
h2{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 14px;font-size:20px;color:var(--navy)}
h2 .num{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:7px;background:var(--navy);color:#fff;font-size:16px}
h2 small{flex-basis:100%;font-size:12.5px;font-weight:400;color:var(--sub)}
h2 .counts{flex-basis:100%;display:flex;flex-wrap:wrap;gap:6px}
.pill{display:inline-flex;align-items:center;height:26px;padding:0 11px;border-radius:999px;font-size:13px;font-weight:700;white-space:nowrap}
.banner{position:relative;border-radius:12px;padding:20px 18px 46px;color:#fff;overflow:hidden;
  background:var(--sprouts) right 8px bottom/auto 46px no-repeat,linear-gradient(90deg,#14462D,#5AA578)}
.banner b{display:block;font-size:21px;line-height:1.35}
.banner span{display:block;font-size:13px;color:#E8F5EC;margin-top:4px}
.kgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0 14px}
.kcard{border:1.5px solid #CFE6D8;border-radius:10px;padding:14px 8px;text-align:center}
.kl{font-size:13px;color:var(--sub)}
.kv{font-size:24px;font-weight:800;line-height:1.3;margin:4px 0 2px}
.ks{font-size:11.5px;color:var(--muted)}
.info{border-top:1px solid var(--line)}
.ir{display:grid;grid-template-columns:78px minmax(0,1fr);border-bottom:1px solid var(--line)}
.il{background:var(--light);padding:12px;display:flex;align-items:center}
.il strong{color:var(--navy)!important}
.iv{padding:12px 12px 12px 14px;font-size:14.5px}
.notice{display:flex;gap:10px;margin-top:16px;font-size:14px}
.notice img{width:22px;height:22px;flex-shrink:0;margin-top:2px}
.pfoot{display:flex;justify-content:space-between;gap:12px;margin-top:28px;padding-top:12px;border-top:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.pfoot b,.pfoot strong{color:var(--navy)}
/* 2쪽 */
.diag{display:grid;gap:12px}
.profile{background:var(--light);border-radius:12px;padding:18px}
.profile>b{display:block;font-size:20px;color:var(--navy);margin-bottom:8px}
.profile dl{display:grid;grid-template-columns:66px minmax(0,1fr);gap:6px 8px;margin:0}
.profile dt{color:var(--sub);font-weight:700}
.profile dd{margin:0}
.chart{text-align:center}
.radar{width:100%;max-width:400px;height:auto;margin:0 auto}
.radar .ax{font-size:13px;font-weight:700;fill:var(--navy)}
.radar .gr{font-size:12px;fill:var(--sub)}
.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:6px 18px;font-size:13.5px;font-weight:700}
.legend span{display:inline-flex;align-items:center;gap:8px}
.ln{display:inline-block;width:24px;height:3px;background:var(--green);border-radius:2px}
.ln.dash{background:repeating-linear-gradient(90deg,var(--purple) 0 6px,transparent 6px 10px)}
.scale{font-size:12px;color:var(--muted);margin-top:6px}
.nw{white-space:nowrap}
.fgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:16px}
.fcard{border:1px solid var(--card);border-radius:10px;overflow:hidden;text-align:center}
.fcard.wide{grid-column:1/-1}
.fl{background:var(--light);font-weight:700;color:var(--navy);font-size:13.5px;padding:7px}
.fv{font-size:25px;font-weight:800;line-height:1.2;padding:12px 4px 2px}
.fv small{font-size:13px;margin-left:3px}
.fs{font-size:12px;color:var(--muted);padding-bottom:12px}
.checks{display:grid;gap:8px}
.ck{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;border:1px solid var(--card);border-radius:10px;padding:14px 14px 14px 18px}
.ck::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:4px;border-radius:0 3px 3px 0;background:var(--jc)}
.ck.th{display:none}
.cl{font-weight:700;color:var(--navy);font-size:16px;align-self:center}
.cj{grid-column:2;grid-row:1;align-self:center}
.cs{grid-column:1/-1;font-size:14.5px}
.cn{grid-column:1/-1;font-size:13.5px;color:var(--sub)}
.cn .m-only{font-weight:700}
.verdict{margin-top:14px;background:#F2F8F4;border:1.5px solid #A9D5B9;border-radius:12px;padding:16px}
.vl{display:inline-block;background:var(--dgreen);color:#fff;font-weight:700;font-size:13.5px;border-radius:999px;padding:3px 14px;margin-bottom:8px}
.verdict p{font-size:15.5px;line-height:1.75}
.verdict .g{color:var(--green)}
.onestop{background:var(--navy);border-radius:14px;padding:18px;color:#fff}
.os-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.os-tag{background:#8FE0B4;color:var(--navy);font-weight:800;font-size:12px;letter-spacing:1px;border-radius:999px;padding:3px 12px}
.os-head b{font-size:16px;line-height:1.45}
.steps{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 16px}
.step{background:#fff;border-radius:10px;padding:12px;color:var(--text)}
.sh{display:flex;align-items:center;gap:8px;color:var(--navy)}
.sn{flex-shrink:0;white-space:nowrap;background:var(--navy);color:#fff;font-weight:700;font-size:12px;border-radius:4px;padding:1px 6px}
.sd{font-size:13px;color:#3A4555;margin-top:6px}
.sw{font-size:13.5px;font-weight:700;color:var(--orange);margin-top:4px}
.contact{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;border-top:1px solid #3B5378;padding-top:14px;color:#DCE5F0;font-size:14.5px}
.contact img{width:22px;height:22px}
.contact>b{color:#fff;font-size:16px;margin-left:-8px}
.contact a{color:#DCE5F0;text-decoration:none}
.contact a strong{color:#fff}
.contact .who{flex-basis:100%;font-size:13.5px}
/* 넓은 화면·인쇄: A4 공문 배치 */
@media (min-width:760px),print{
  .doc{padding:28px 16px 48px}
  .page{width:794px;max-width:100%;margin:0 auto 24px;padding:48px 52px;border-radius:2px;box-shadow:0 4px 24px rgba(15,23,42,.08);border:0}
  .meta{grid-template-columns:80px minmax(0,1fr)}
  h2 small{flex-basis:auto;margin-left:auto}
  h2 .counts{flex-basis:auto;margin-left:auto}
  .kgrid{grid-template-columns:repeat(4,minmax(0,1fr))}
  .diag{grid-template-columns:260px minmax(0,1fr);align-items:center}
  .fgrid{grid-template-columns:repeat(5,minmax(0,1fr))}
  .fcard.wide{grid-column:auto}
  .fv{font-size:24px}
  .checks{gap:0;border-top:2px solid var(--navy)}
  .ck,.ck.th{display:grid;grid-template-columns:110px minmax(0,1.35fr) 108px minmax(0,1.25fr);gap:0;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:0}
  .ck::before{display:none}
  .ck>div{padding:9px 12px;align-self:stretch;display:flex;align-items:center}
  .ck.th{background:var(--navy);color:#fff;font-weight:700}
  .cl{font-size:15px}
  .cs{grid-column:auto;font-size:14px}
  .cj{grid-column:auto;grid-row:auto;justify-content:center;background:color-mix(in srgb,var(--jc) 12%,#fff)}
  .cn{grid-column:auto;font-size:14px;color:var(--text)}
  .cn .m-only{display:none}
  .ck:nth-child(odd):not(.th){background:#F7F9FB}
  .verdict{display:flex;gap:16px;align-items:center}
  .vl{flex-shrink:0;margin:0;border-radius:6px;padding:6px 14px}
  .steps{grid-template-columns:repeat(4,minmax(0,1fr))}
}
@media print{
  @page{size:A4;margin:0}
  body{background:#fff;font-size:13.5px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .toolbar,.toast{display:none!important}
  .doc{padding:0;max-width:none}
  .page{width:210mm;height:296mm;margin:0;padding:12mm 14mm;box-shadow:none;overflow:hidden;break-after:page;page-break-after:always;display:flex;flex-direction:column}
  .page:last-child{break-after:auto;page-break-after:auto}
  .pfoot{margin-top:auto;padding-top:8px}
  /* A4 한 쪽에 들어가도록 인쇄에서만 간격·크기를 줄인다 */
  .page{padding:10mm 14mm 9mm}
  .head{padding-bottom:10px}
  section{margin-top:12px}
  .pill{height:20px;font-size:12px;padding:0 9px}
  h2 .counts .pill{height:22px}
  h2{font-size:18px;margin-bottom:10px}
  h2 .num{width:26px;height:26px;font-size:14px}
  .intro{margin:12px 0}
  .kv{font-size:21px}
  .kgrid{margin:10px 0}
  .diag{grid-template-columns:250px minmax(0,1fr);gap:8px}
  .profile{padding:14px}
  .radar{max-width:225px}
  .legend{font-size:12px}.scale{font-size:11px;margin-top:2px}
  .fgrid{margin-top:10px;gap:8px}
  .fl{padding:4px;font-size:12.5px}.fv{font-size:19px;padding:6px 4px 0}.fs{padding-bottom:7px;font-size:11px}
  .ck>div{padding:4px 10px}
  .cl,.cs,.cn{font-size:13px}
  .verdict{margin-top:10px;padding:11px 14px}
  .verdict p{font-size:13.5px;line-height:1.6}
  .onestop{padding:13px 14px}
  .steps{margin:10px 0 10px;gap:8px}
  .step{padding:9px 10px}
  .contact{padding-top:9px;font-size:13px}
  .contact a{color:#DCE5F0}
}
@media (max-width:380px){
  .tb-btns button span{display:none}
  .tb-btns button{padding:0 10px}
  .kv{font-size:21px}
}
"""

JS = """
(function(){
  var toast = document.getElementById('toast'), timer;
  function show(msg){ toast.textContent = msg; toast.classList.add('show'); clearTimeout(timer); timer = setTimeout(function(){ toast.classList.remove('show'); }, 2200); }
  document.getElementById('btnPrint').addEventListener('click', function(){ window.print(); });
  document.getElementById('btnCopy').addEventListener('click', function(){
    var url = location.origin + location.pathname;  // 짧은 주소 /l/코드 (쿼리·해시 제외)
    function fallback(){
      var ta = document.createElement('textarea'); ta.value = url; ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select();
      var ok = false; try{ ok = document.execCommand('copy'); }catch(e){}
      ta.remove(); show(ok ? 'URL을 복사했습니다' : url);
    }
    if(navigator.clipboard && window.isSecureContext){
      navigator.clipboard.writeText(url).then(function(){ show('URL을 복사했습니다'); }, fallback);
    }else{ fallback(); }
  });
})();
"""
