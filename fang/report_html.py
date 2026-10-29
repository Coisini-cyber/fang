from __future__ import annotations

import html
import json
import os
from typing import List

from .models import MutantResult, RunReport
from .scoring import grade, grade_word
from .util import human_duration, human_int, pct, truncate

STYLE = """
:root{
  --bg:#080a0f; --panel:#0f1219; --panel2:#141925; --line:rgba(255,255,255,.075);
  --text:#e9ecf4; --muted:#8d94a7; --acid:#c8ff4d; --red:#ff6b6b; --amber:#ffc857;
  --green:#5ee39a; --blue:#6cc7ff; --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
html{color-scheme:dark}
body{margin:0;background:
  radial-gradient(1100px 520px at 12% -12%,rgba(200,255,77,.10),transparent 62%),
  radial-gradient(900px 520px at 96% 0%,rgba(108,199,255,.07),transparent 60%),
  var(--bg);
  color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--acid)}
.wrap{max-width:1120px;margin:0 auto;padding:34px 24px 70px}
header.top{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:34px}
.brand{display:flex;align-items:center;gap:14px}
.mark{width:42px;height:42px;border-radius:12px;background:var(--acid);display:grid;place-items:center;color:#080a0f;font-family:var(--mono);font-weight:800;font-size:21px;box-shadow:0 0 40px rgba(200,255,77,.28)}
.wordmark{font-family:var(--mono);font-size:20px;font-weight:700;letter-spacing:.16em}
.tagline{color:var(--muted);font-size:12.5px;letter-spacing:.04em}
.meta{font-family:var(--mono);font-size:11.5px;color:var(--muted);text-align:right;line-height:1.7}
.meta strong{color:var(--text);font-weight:500}
h1{font-size:clamp(28px,4vw,44px);line-height:1.1;margin:0 0 8px;letter-spacing:-.02em;font-weight:650}
.sub{color:var(--muted);margin:0 0 30px;max-width:70ch}
.hero{display:grid;grid-template-columns:270px 1fr;gap:18px;align-items:stretch;margin-bottom:18px}
.scorecard{background:linear-gradient(160deg,rgba(255,255,255,.045),rgba(255,255,255,.012));border:1px solid var(--line);border-radius:20px;padding:26px 22px;display:grid;place-items:center;text-align:center;position:relative;overflow:hidden}
.scorecard:after{content:"";position:absolute;inset:auto -40px -70px -40px;height:120px;background:radial-gradient(closest-side,rgba(200,255,77,.18),transparent)}
.ring{position:relative;width:196px;height:196px}
.ring svg{transform:rotate(-90deg);width:196px;height:196px}
.ring .track{stroke:rgba(255,255,255,.07);stroke-width:10;fill:none}
.ring .value{stroke:var(--acid);stroke-width:10;fill:none;stroke-linecap:round;stroke-dasharray:0 999;transition:stroke-dasharray 1.2s cubic-bezier(.2,.7,.2,1)}
.ring .center{position:absolute;inset:0;display:grid;place-content:center;gap:2px}
.big{font-family:var(--mono);font-size:42px;font-weight:700;letter-spacing:-.04em;line-height:1}
.big span{font-size:18px;color:var(--muted);margin-left:2px}
.grade{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px 16px 14px;min-width:0}
.stat .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.13em;color:var(--muted);text-transform:uppercase}
.stat .v{font-family:var(--mono);font-size:27px;font-weight:650;margin-top:6px;letter-spacing:-.03em}
.stat .n{font-size:11.5px;color:var(--muted);margin-top:2px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin:18px 0}
.panel h2{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 14px;font-weight:600}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:26px 0 14px}
.chip{appearance:none;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:7px 12px;font-family:var(--mono);font-size:11.5px;cursor:pointer;transition:.15s}
.chip:hover{border-color:rgba(255,255,255,.22);color:var(--text)}
.chip[aria-pressed="true"]{background:var(--text);color:#080a0f;border-color:var(--text)}
.chip .c{opacity:.55;margin-left:4px}
.search{margin-left:auto;display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:6px 10px;min-width:230px}
.search span{color:var(--muted);font-family:var(--mono);font-size:12px}
.search input{all:unset;color:var(--text);font-family:var(--mono);font-size:12px;width:100%}
.search input::placeholder{color:#5c6273}
.list{display:grid;gap:12px}
.mutant{background:linear-gradient(180deg,rgba(255,255,255,.028),rgba(255,255,255,.008));border:1px solid var(--line);border-radius:15px;padding:15px 17px}
.mutant[data-status="survived"]{border-left:3px solid var(--red)}
.mutant[data-status="killed"]{border-left:3px solid rgba(94,227,154,.55)}
.mutant[data-status="timeout"]{border-left:3px solid var(--amber)}
.m-head{display:flex;flex-wrap:wrap;align-items:center;gap:9px;margin-bottom:10px}
.loc{font-family:var(--mono);font-size:12.5px;font-weight:600;color:var(--text)}
.ctx{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.op{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue);border:1px solid rgba(108,199,255,.25);background:rgba(108,199,255,.07);border-radius:6px;padding:2px 6px}
.status{margin-left:auto;font-family:var(--mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;border-radius:999px}
.status.survived{color:var(--red);background:rgba(255,107,107,.09);border:1px solid rgba(255,107,107,.3)}
.status.killed{color:var(--green);background:rgba(94,227,154,.07);border:1px solid rgba(94,227,154,.24)}
.status.timeout{color:var(--amber);background:rgba(255,200,87,.08);border:1px solid rgba(255,200,87,.28)}
.status.error,.status.worker_error{color:var(--muted);background:rgba(255,255,255,.04);border:1px solid var(--line)}
pre.diff{margin:0 0 10px;background:#07090d;border:1px solid rgba(255,255,255,.05);border-radius:10px;padding:11px 13px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.7}
.del{display:block;color:#ff8b8b;white-space:pre-wrap;word-break:break-word}
.add{display:block;color:#8dffc0;white-space:pre-wrap;word-break:break-word}
body[data-filter="survived"] .mutant:not([data-status="survived"]),
body[data-filter="killed"] .mutant:not([data-status="killed"]),
body[data-filter="timeout"] .mutant:not([data-status="timeout"]),
body[data-filter="error"] .mutant:not([data-status="error"]),
body[data-filter="worker_error"] .mutant:not([data-status="worker_error"]){display:none}
.desc{font-family:var(--mono);font-size:12px;color:#c3c9d8;margin:0 0 5px;word-break:break-word}
.hint{font-size:13px;color:var(--muted);margin:0}
.m-foot{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:11px;font-family:var(--mono);font-size:11px;color:#697086}
.copy{appearance:none;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:6px;padding:3px 7px;font-family:var(--mono);font-size:10.5px;cursor:pointer}
.copy:hover{color:var(--text);border-color:rgba(255,255,255,.24)}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
th{color:var(--muted);font-weight:500;text-align:left;letter-spacing:.06em;text-transform:uppercase;font-size:10px;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:8px;border-bottom:1px solid rgba(255,255,255,.04)}
td.num{text-align:right}
.fbar{height:7px;background:rgba(255,255,255,.07);border-radius:99px;overflow:hidden;min-width:90px}
.fbar i{display:block;height:100%;background:var(--acid);border-radius:99px}
details.learn{margin-top:18px;color:var(--muted);font-size:13.5px}
details.learn summary{cursor:pointer;color:var(--text);font-family:var(--mono);font-size:12px;letter-spacing:.06em}
details.learn p{max-width:85ch}
footer.end{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;color:#5f6575;font-family:var(--mono);font-size:10.5px}
.note{font-size:12.5px;color:var(--muted);margin:8px 0 0}
.note b{color:var(--amber);font-weight:500}
@media(max-width:860px){.hero{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.search{margin-left:0;width:100%}.wrap{padding:22px 16px 50px}}
@media print{body{background:#fff;color:#111}.mutant,.panel,.stat{break-inside:avoid}.toolbar,.copy{display:none}}
"""

SCRIPT = """
(function(){
  var body=document.body, cards=Array.prototype.slice.call(document.querySelectorAll('.mutant'));
  var chips=Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  var q=document.getElementById('q'), count=document.getElementById('visible-count');
  function apply(){
    var term=(q.value||'').toLowerCase().trim(), visible=0;
    cards.forEach(function(card){
      var okStatus=body.dataset.filter==='all'||card.dataset.status===body.dataset.filter;
      var okText=!term||card.dataset.search.indexOf(term)!==-1;
      card.hidden=!(okStatus&&okText);
      if(okStatus&&okText) visible++;
    });
    if(count) count.textContent=String(visible);
  }
  chips.forEach(function(chip){
    chip.addEventListener('click',function(){
      body.dataset.filter=chip.dataset.filter;
      chips.forEach(function(c){c.setAttribute('aria-pressed',String(c===chip));});
      apply();
    });
  });
  if(q) q.addEventListener('input',apply);
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus();}
    if(e.key==='Escape'){q.value='';apply();q.blur();}
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-copy]'),function(btn){
    btn.addEventListener('click',function(){
      var text=btn.getAttribute('data-copy');
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){
          var old=btn.textContent;btn.textContent='copied';setTimeout(function(){btn.textContent=old;},1200);
        }).catch(function(){});
      }
    });
  });
  apply();
})();
"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _display_root(root: str) -> str:
    try:
        relative = os.path.relpath(root, os.getcwd())
    except ValueError:
        return root
    if relative == ".":
        return "repository root"
    if relative.startswith(".."):
        return root
    return relative.replace(os.sep, "/")


def _status_label(status: str) -> str:
    return "worker error" if status == "worker_error" else status


def _search_blob(result: MutantResult) -> str:
    mutant = result.mutant
    return " ".join(
        [
            mutant.path,
            str(mutant.line),
            mutant.context,
            mutant.operator,
            result.status,
            mutant.description,
            mutant.hint,
            mutant.source_line,
            mutant.mutated_line or "",
            result.killer or "",
        ]
    ).lower()


def _card(result: MutantResult) -> str:
    mutant = result.mutant
    source = mutant.source_line.strip()
    mutated = (mutant.mutated_line or "").strip()
    if mutated:
        diff = (
            '<pre class="diff"><span class="del">- %s</span><span class="add">+ %s</span></pre>'
            % (_esc(source), _esc(mutated))
        )
    else:
        diff = (
            '<pre class="diff"><span class="del">- %s</span><span class="add">+ %s</span></pre>'
            % (_esc(mutant.expression_before), _esc(mutant.expression_after))
        )
    killer = ""
    if result.killer:
        killer = '<span>killed by <b>%s</b></span>' % _esc(result.killer)
    duration = '<span>%.2fs</span>' % result.duration
    cached = "<span>cached</span>" if result.cached else ""
    return """
<article class="mutant" data-status="%s" data-search="%s">
  <div class="m-head">
    <span class="loc">%s:%d</span>
    <span class="ctx">%s</span>
    <span class="op">%s</span>
    <span class="status %s">%s</span>
  </div>
  %s
  <p class="desc">%s</p>
  <p class="hint">%s</p>
  <div class="m-foot">%s %s %s <button class="copy" data-copy="%s">copy hint</button></div>
</article>""" % (
        _esc(result.status),
        _esc(_search_blob(result)),
        _esc(mutant.path),
        mutant.line,
        _esc(mutant.context or "module"),
        _esc(mutant.operator),
        _esc(result.status),
        _esc(_status_label(result.status)),
        diff,
        _esc(mutant.description),
        _esc(mutant.hint),
        killer,
        duration,
        cached,
        _esc(mutant.hint),
    )


def _file_rows(report: RunReport) -> str:
    stats = {}
    for result in report.results:
        if result.status == "worker_error":
            continue
        killed, survived = stats.get(result.mutant.path, (0, 0))
        if result.status == "survived":
            survived += 1
        else:
            killed += 1
        stats[result.mutant.path] = (killed, survived)
    rows: List[str] = []
    for path in sorted(stats):
        killed, survived = stats[path]
        total = killed + survived
        score = 100.0 * killed / total if total else 0.0
        rows.append(
            "<tr><td>%s</td><td class=\"num\">%d</td><td class=\"num\">%d</td>"
            "<td class=\"num\">%s</td><td><div class=\"fbar\"><i style=\"width:%.1f%%\"></i></div></td></tr>"
            % (_esc(path), killed, survived, pct(score, 0), score)
        )
    return "".join(rows)


def render_html(report: RunReport) -> str:
    score = report.score
    score_text = pct(score)
    score_value = 0.0 if score is None else score
    grade_text = "%s %s %s" % (grade(score), "\u00b7", grade_word(score))
    survivors = [result for result in report.results if result.status == "survived"]
    default_filter = "survived" if survivors else "all"

    ordered = sorted(
        report.results,
        key=lambda result: (
            {"survived": 0, "timeout": 1, "error": 2, "worker_error": 3, "killed": 4}.get(result.status, 5),
            result.mutant.path,
            result.mutant.line,
        ),
    )
    cards = "".join(_card(result) for result in ordered)
    initial_visible = len(survivors) if default_filter == "survived" else len(report.results)

    counts = {
        "survived": len(survivors),
        "killed": report.killed,
        "timeout": report.timeouts,
        "error": report.errors,
        "worker_error": report.worker_errors,
    }
    chips = ['<button class="chip" data-filter="all" aria-pressed="%s">all<span class="c">%d</span></button>'
             % ("true" if default_filter == "all" else "false", len(report.results))]
    for status in ("survived", "killed", "timeout", "error", "worker_error"):
        if counts.get(status):
            chips.append(
                '<button class="chip" data-filter="%s" aria-pressed="%s">%s<span class="c">%d</span></button>'
                % (
                    status,
                    "true" if default_filter == status else "false",
                    _status_label(status),
                    counts[status],
                )
            )
    chips_html = "".join(chips)

    sample_note = ""
    if report.sampled and report.score_ci:
        sample_note = "Sampled %d of %d mutants. The score is an estimate; the 95%% Wilson interval is %s to %s." % (
            report.mutants_considered,
            report.mutants_total,
            pct(report.score_ci[0]),
            pct(report.score_ci[1]),
        )
    elif score is None:
        sample_note = "No mutants were evaluated in this scope."

    notes = ""
    if report.notes:
        notes = '<div class="panel"><h2>Notes</h2>' + "".join(
            "<p class=\"note\">%s</p>" % _esc(note) for note in report.notes
        ) + "</div>"

    payload = report.to_dict()
    payload["root"] = _display_root(report.root)
    # The HTML cards never render raw test output; leaving it in the embedded
    # data would bloat the file and could leak values from CI logs.
    for item in payload.get("results", []):
        item.pop("output", None)
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    mode = report.mode
    if report.mode == "diff" and report.diff_base:
        mode = "diff vs %s" % report.diff_base
    meta = [
        "<strong>%s</strong>" % _esc(_display_root(report.root)),
        "%s &middot; %s" % (_esc(mode), _esc(report.started_at)),
        ("%s tests &middot; %s suite" % (
            human_int(report.tests_collected) if report.tests_collected is not None else "?",
            human_duration(report.baseline_duration),
        )),
    ]
    if report.cache_hits:
        meta.append("%d cached" % report.cache_hits)
    scope_text = "all files" if report.mode == "all" else (
        "diff vs %s" % report.diff_base if report.mode == "diff" else "selected lines"
    )
    sub_text = "Scope: %s %s %s mutants generated %s %s tests collected" % (
        scope_text,
        "\u00b7",
        human_int(report.mutants_total),
        "\u00b7",
        human_int(report.tests_collected) if report.tests_collected is not None else "?",
    )
    ring_color = "#5ee39a" if score_value >= 80 else ("#ffc857" if score_value >= 60 else "#ff6b6b")
    circumference = 2 * 3.141592653589793 * 82
    dash = circumference * score_value / 100.0

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fang %s mutation report</title>
<style>%s</style>
</head>
<body data-filter="%s">
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="mark">F</div>
      <div>
        <div class="wordmark">FANG</div>
        <div class="tagline">your tests pass. do they bite?</div>
      </div>
    </div>
    <div class="meta">%s</div>
  </header>

  <h1>%s mutation score</h1>
  <p class="sub">%s</p>

  <section class="hero">
    <div class="scorecard">
      <div class="ring">
        <svg viewBox="0 0 196 196" aria-hidden="true">
          <circle class="track" cx="98" cy="98" r="82"></circle>
          <circle class="value" cx="98" cy="98" r="82" style="stroke:%s;stroke-dasharray:%.1f %.1f"></circle>
        </svg>
        <div class="center"><div class="big">%s<span>%%</span></div><div class="grade">%s</div></div>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><div class="k">killed</div><div class="v" style="color:var(--green)">%d</div><div class="n">mutants your tests noticed</div></div>
      <div class="stat"><div class="k">survived</div><div class="v" style="color:var(--red)">%d</div><div class="n">behaviour changes left unchecked</div></div>
      <div class="stat"><div class="k">mutants</div><div class="v">%d</div><div class="n">of %d generated</div></div>
      <div class="stat"><div class="k">run time</div><div class="v">%s</div><div class="n">%s baseline</div></div>
    </div>
  </section>

  <section class="toolbar" aria-label="Filters">
    %s
    <label class="search"><span>/</span><input id="q" type="search" placeholder="filter by file, function, test..." autocomplete="off"></label>
  </section>
  <p class="note" style="margin:-4px 0 14px">Showing <b id="visible-count">%d</b> mutants. Press <code>/</code> to search, <code>Esc</code> to reset.</p>

  <section class="list" aria-label="Mutants">%s</section>

  <section class="panel">
    <h2>Files</h2>
    <table><thead><tr><th>file</th><th class="num">killed</th><th class="num">survived</th><th class="num">score</th><th></th></tr></thead>
    <tbody>%s</tbody></table>
  </section>

  %s

  <details class="learn">
    <summary>How to read this report</summary>
    <p><strong>Mutation score</strong> is the share of generated mutants your suite detected. A mutant is a small, syntactically valid change to your code: a flipped comparison, a changed constant, a removed return value. If the suite still passes, the mutant <em>survived</em>, which means no test observed that behaviour.</p>
    <p>Survivors are not automatically bugs. Some mutants are <em>equivalent</em> (the change cannot alter observable behaviour, such as changing the rounding precision of a value that is already exact). Treat survivors as questions, not verdicts. The hint on each card suggests the kind of assertion that would settle it.</p>
    <p>Fang only mutates the lines in scope, runs the suite with fail-fast, and treats a timeout or a crash caused by the mutant as detection. A green baseline is required; a red suite cannot distinguish a surviving mutant from a pre-existing failure.</p>
    <p>%s</p>
  </details>

  <footer class="end">
    <span>generated by fang %s &middot; zero runtime dependencies</span>
    <span>%s</span>
  </footer>
</div>
<script id="fang-data" type="application/json">%s</script>
<script>%s</script>
</body>
</html>""" % (
        _esc(score_text),
        STYLE,
        default_filter,
        "<br>".join(meta),
        _esc(score_text),
        _esc(sub_text),
        ring_color,
        dash,
        circumference - dash,
        "n/a" if score is None else ("%.1f" % score),
        _esc(grade_text),
        report.killed,
        report.survived,
        report.mutants_considered,
        report.mutants_total,
        _esc(human_duration(report.duration)),
        _esc(human_duration(report.baseline_duration)),
        chips_html,
        initial_visible,
        cards,
        _file_rows(report),
        notes,
        _esc(sample_note),
        _esc(report.version),
        _esc(report.test_command),
        data_json,
        SCRIPT,
    )


def render_badge(report: RunReport) -> str:
    score = report.score
    label = "n/a" if score is None else "%.1f%%" % score
    color = "#c8ff4d" if (score or 0) >= 80 else ("#ffc857" if (score or 0) >= 60 else "#ff6b6b")
    return """<svg xmlns="http://www.w3.org/2000/svg" width="190" height="28" role="img" aria-label="fang mutation score: %s">
  <rect width="190" height="28" rx="6" fill="#0b0d12"/>
  <rect width="62" height="28" rx="6" fill="%s"/>
  <rect x="56" width="6" height="28" fill="%s"/>
  <text x="31" y="18" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11" font-weight="700" fill="#080a0f">fang</text>
  <text x="124" y="18" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11" fill="#e9ecf4">%s</text>
</svg>""" % (_esc(label), color, color, _esc(label))


def render_markdown(report: RunReport) -> str:
    survivors = [result for result in report.results if result.status == "survived"]
    lines = [
        "## Fang mutation report",
        "",
        "**%s** mutation score %s %d killed %s %d survived"
        % (
            pct(report.score),
            "\u00b7",
            report.killed,
            "\u00b7",
            report.survived,
        ),
        "",
    ]
    if report.sampled and report.score_ci:
        lines.append(
            "_Sampled %d of %d mutants; 95%% CI %s-%s._"
            % (
                report.mutants_considered,
                report.mutants_total,
                pct(report.score_ci[0]),
                pct(report.score_ci[1]),
            )
        )
        lines.append("")
    lines.append(
        "Suite: %s tests, %s baseline. Scope: %s."
        % (
            human_int(report.tests_collected) if report.tests_collected is not None else "?",
            human_duration(report.baseline_duration),
            report.mode if report.mode != "diff" else "diff vs `%s`" % report.diff_base,
        )
    )
    lines.append("")
    if survivors:
        lines.append("<details><summary>Surviving mutants (%d)</summary>" % len(survivors))
        lines.append("")
        for result in survivors[:40]:
            mutant = result.mutant
            lines.append(
                "- `%s:%d` **%s** %s `%s` %s `%s`  \n  %s"
                % (
                    mutant.path,
                    mutant.line,
                    mutant.context or "module",
                    "\u00b7",
                    truncate(mutant.original, 48),
                    "\u2192",
                    truncate(mutant.replacement, 48),
                    mutant.hint,
                )
            )
        if len(survivors) > 40:
            lines.append("- ... and %d more" % (len(survivors) - 40))
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("No surviving mutants in scope.")
    lines.append("")
    return "\n".join(lines)
