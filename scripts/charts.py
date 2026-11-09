# Build the chart HTML from agg/study_aggregates.json.  python3 charts.py  -> WORK/charts/*.html and agg/chart_data.json
# Rerun change (5 Nov 2026): the footer's push window comes from agg/run_config.json instead of being typed in,
# and every value drawn is also written to agg/chart_data.json.
import json, os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import STUDY, AGG, RUN_DATE, PUSH_FROM

WINDOW = f"{PUSH_FROM.day} {PUSH_FROM.strftime('%b')} to {RUN_DATE.day} {RUN_DATE.strftime('%b')} {RUN_DATE.year}"
DATA = {'push_window_label': WINDOW}

A = json.load(open(os.path.join(AGG, 'study_aggregates.json')))
OUT = os.path.join(STUDY, 'charts'); os.makedirs(OUT, exist_ok=True)

FONTS = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=block" rel="stylesheet">'
BASE_CSS = '''
:root { --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835;
        --s1:#3987e5; --s2:#d95926; }
* { box-sizing:border-box; margin:0; padding:0; }
html, body { background:var(--surface); color:var(--ink); font-family:Inter, system-ui, -apple-system, sans-serif;
             -webkit-font-smoothing:antialiased; }
.mono { font-family:"JetBrains Mono", ui-monospace, monospace; }
'''


def pct(x):
    # one decimal (9 Nov 2026), so a group's rows visibly add up to its header
    return f"{x:.1f}%"


def relationship_chart():
    P = A['pairs']; K = P['kinds']; n = P['n']
    g = lambda k: K.get(k, {'k': 0, 'pct': 0})
    imp_k = g('import-shim')['k'] + g('import-plus')['k']
    rows_conn = [
        ('CLAUDE.md imports <span class="mono">@AGENTS.md</span>', imp_k),
        ('One file is a symlink to the other', g('symlink')['k']),
    ]
    rows_not = [
        ('A sentence points to the other file', g('pointer')['k']),
        ('Two separate files', g('separate')['k']),
        ('Copies: identical or near-copies', g('identical')['k'] + g('near-copy')['k']),
    ]
    other = g('symlink-other')['k']
    total = n
    mx = max(k for _, k in rows_conn + rows_not)

    def bar_rows(rows, color):
        out = []
        for label, k in rows:
            p = 100 * k / total
            w = 100 * k / mx
            out.append(f'''<div class="row"><div class="lab">{label}</div>
              <div class="track"><div class="bar" style="width:{w * 0.80:.2f}%;background:{color}"></div>
              <div class="val"><b>{pct(p)}</b><span>{k:,} repos</span></div></div></div>''')
        return '\n'.join(out)

    # headers from the classification itself (9 Nov 2026): "no import or symlink" also holds the other symlink
    # setups the footer mentions, so the header matches the post's share
    conn_p = 100 * P['wired']['k'] / total
    not_p = 100 * P['not_wired']['k'] / total
    doc = f'''<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
body {{ width:1200px; height:675px; padding:52px 64px 0 64px; }}
.kicker {{ color:var(--muted); font-size:17px; }}
h1 {{ font-size:38px; font-weight:600; letter-spacing:-0.01em; margin-top:8px; }}
.group {{ margin-top:40px; }}
.gh {{ display:flex; align-items:center; gap:10px; font-size:17px; color:var(--ink2); font-weight:500; margin-bottom:12px; }}
.gh i {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
.gh b {{ color:var(--ink); font-weight:600; }}
.row {{ display:grid; grid-template-columns:420px 1fr; align-items:center; height:54px; }}
.lab {{ font-size:19px; color:var(--ink); }}
.lab .mono {{ font-size:17.5px; }}
.track {{ position:relative; display:flex; align-items:center; height:24px; border-left:1px solid var(--axis); }}
.bar {{ height:22px; border-radius:0 4px 4px 0; }}
.val {{ margin-left:12px; font-size:18px; color:var(--ink); white-space:nowrap; }}
.val b {{ font-weight:600; margin-right:8px; }}
.val span {{ color:var(--muted); font-size:16px; }}
.foot {{ position:absolute; left:64px; right:64px; bottom:36px; display:flex; justify-content:space-between; color:var(--muted); font-size:15px; }}
</style></head><body>
<div class="kicker">{n:,} public GitHub repos with a root CLAUDE.md and a root AGENTS.md</div>
<h1>How repos with both files link them</h1>
<div class="group"><div class="gh"><i style="background:var(--s1)"></i><b>Linked, {pct(conn_p)}.</b> An import or a symlink gives both agents one file's text</div>
{bar_rows(rows_conn, 'var(--s1)')}</div>
<div class="group"><div class="gh"><i style="background:var(--s2)"></i><b>No import or symlink found, {pct(not_p)}.</b> By default, each agent loads only its own file</div>
{bar_rows(rows_not, 'var(--s2)')}</div>
<div class="foot"><span>Repos with 10+ stars, pushed {WINDOW}, sampled by creation day{f". {other} other symlink setup not shown" if other == 1 else (f". {other} other symlink setups not shown" if other else "")}</span><span>pulore.com</span></div>
</body></html>'''
    open(os.path.join(OUT, 'relationship.html'), 'w').write(doc)
    strip = lambda t: t.replace('<span class="mono">', '').replace('</span>', '')
    DATA['relationship'] = {'repos_with_both_files': n, 'connected_pct': round(conn_p, 1), 'not_connected_pct': round(not_p, 1),
                            'other_symlink_setups_not_shown': other,
                            'connected': [{'label': strip(l), 'repos': k, 'pct': round(100 * k / total, 1)} for l, k in rows_conn],
                            'not_connected': [{'label': strip(l), 'repos': k, 'pct': round(100 * k / total, 1)} for l, k in rows_not]}


def size_chart():
    S = A['size']; bins = S['root_AGENTS.md_bins']; n = S['root_AGENTS.md_known_size']
    over = S['root_AGENTS.md_over_32KiB']; comb = S['repos_over_32KiB_only_when_combined']
    labels = ['up to 1 KiB', '1-4 KiB', '4-8 KiB', '8-16 KiB', '16-32 KiB', '32-64 KiB', 'over 64 KiB']
    nice = {'up to 1 KiB': 'Up to 1 KiB', '1-4 KiB': '1 to 4 KiB', '4-8 KiB': '4 to 8 KiB', '8-16 KiB': '8 to 16 KiB',
            '16-32 KiB': '16 to 32 KiB', '32-64 KiB': '32 to 64 KiB', 'over 64 KiB': 'Over 64 KiB'}
    mx = max(bins[l] for l in labels)
    rows = []
    for i, l in enumerate(labels):
        k = bins[l]; is_over = i >= 5
        if i == 5:
            rows.append('<div class="limit"><span>Codex\'s default limit: 32 KiB (32,768 bytes)</span></div>')
        rows.append(f'''<div class="row"><div class="lab">{nice[l]}</div><div class="track">
          <div class="bar" style="width:{78 * k / mx:.2f}%;background:{'var(--s2)' if is_over else 'var(--s1)'}"></div>
          <div class="val"><b>{100 * k / n:.1f}%</b><span>{k:,} files</span></div></div></div>''')
    doc = f'''<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{BASE_CSS}
body {{ width:1200px; height:675px; padding:52px 64px 0 64px; }}
.kicker {{ color:var(--muted); font-size:17px; }}
h1 {{ font-size:36px; font-weight:600; letter-spacing:-0.01em; margin-top:8px; }}
.legend {{ display:flex; gap:28px; margin:26px 0 20px; font-size:17px; color:var(--ink2); }}
.legend i {{ width:12px; height:12px; border-radius:3px; display:inline-block; margin-right:9px; vertical-align:-1px; }}
.row {{ display:grid; grid-template-columns:220px 1fr; align-items:center; height:50px; }}
.lab {{ font-size:19px; color:var(--ink); }}
.track {{ position:relative; display:flex; align-items:center; height:24px; border-left:1px solid var(--axis); }}
.bar {{ height:22px; border-radius:0 4px 4px 0; min-width:3px; }}
.val {{ margin-left:12px; font-size:18px; color:var(--ink); white-space:nowrap; }}
.val b {{ font-weight:600; margin-right:8px; }}
.val span {{ color:var(--muted); font-size:16px; }}
.limit {{ position:relative; height:30px; margin-left:220px; border-top:1px solid var(--ink2); margin-top:6px; }}
.limit span {{ position:absolute; top:5px; left:12px; font-size:15px; color:var(--ink2); }}
.foot {{ position:absolute; left:64px; right:64px; bottom:36px; display:flex; justify-content:space-between; color:var(--muted); font-size:15px; }}
</style></head><body>
<div class="kicker">{n:,} root AGENTS.md files from the same sample of public repos, by size</div>
<h1>{over['pct']:.1f}% of root AGENTS.md files are over the default limit</h1>
<div class="legend"><span><i style="background:var(--s1)"></i>Codex loads the whole file</span><span><i style="background:var(--s2)"></i>Codex cuts it off, with no warning</span></div>
{''.join(rows)}
<div class="foot"><span>Another {comb['k']} repos ({comb['pct']:.1f}%) go over only once nested AGENTS.md files on the same path are added</span><span>pulore.com</span></div>
</body></html>'''
    open(os.path.join(OUT, 'size.html'), 'w').write(doc)
    DATA['size'] = {'root_AGENTS.md_files_with_known_size': n, 'over_32KiB_pct': over['pct'], 'over_32KiB': over['k'],
                    'over_only_when_nested_files_added': {'repos': comb['k'], 'pct': comb['pct'], 'of_trees_checked': comb['n']},
                    'bins': [{'label': nice[l], 'files': bins[l], 'pct': round(100 * bins[l] / n, 1), 'over_limit': i >= 5} for i, l in enumerate(labels)]}


if __name__ == '__main__':
    relationship_chart()
    size_chart()
    json.dump(DATA, open(os.path.join(AGG, 'chart_data.json'), 'w'), indent=1)
    print('ok')
