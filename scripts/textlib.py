# Text helpers: relationship classification, similarity, and conflict extraction for CLAUDE.md / AGENTS.md pairs.
import hashlib, json, os, posixpath, re, subprocess

GQL_SYMLINK = 40960       # GraphQL TreeEntry.mode for 120000
LIMIT = 32768             # Codex project_doc_max_bytes default (32 KiB)


# ---------- normalisation ----------
def norm_lines(t):
    out = []
    for l in (t or '').replace('\r\n', '\n').split('\n'):
        s = re.sub(r'\s+', ' ', l.strip())
        if s:
            out.append(s)
    return out


def mask_tools(s):
    s = re.sub(r'(?i)\.?/?\b(?:claude|agents|gemini|copilot-instructions)\.md\b', 'FILE.md', s)
    s = re.sub(r'(?i)\bclaude[ -]code\b|\bcodex(?: cli)?\b|\bclaude\b|\bopenai\b|\banthropic\b|\bgemini(?: cli)?\b|\bcursor\b|\bcopilot\b', 'AGENT', s)
    return s.lower()


def strip_code(t):
    t = re.sub(r'```.*?(```|\Z)', ' ', t or '', flags=re.S)
    t = re.sub(r'~~~.*?(~~~|\Z)', ' ', t, flags=re.S)
    t = re.sub(r'`[^`\n]*`', ' ', t)
    return t


def similarity(ct, at):
    cl = {mask_tools(x) for x in norm_lines(ct)}
    al = {mask_tools(x) for x in norm_lines(at)}
    if not cl or not al:
        return 0.0, 0.0, 0, 0, 0
    inter = len(cl & al)
    return inter / len(cl | al), inter / min(len(cl), len(al)), len(cl - al), len(al - cl), inter


def identical(ct, at):
    return '\n'.join(norm_lines(ct)) == '\n'.join(norm_lines(at))


# ---------- Claude Code @-imports (9 Nov 2026) ----------
# Imports come from claude_imports.mjs, which applies Claude Code's own rule with marked. LOOSE_IMPORT_A is a looser
# pattern: @AGENTS.md outside code, ending at a word boundary. It also matches "@AGENTS.md.backup", "@AGENTS.md-old",
# "@AGENTS.md." and "(@AGENTS.md)", none of which Claude Code imports. It is kept only to count how many pairs it
# would classify differently.
LOOSE_IMPORT_A = re.compile(r'(?<![\w@./-])@(?:\./)?AGENTS\.md\b')
# An @AGENTS.md / @CLAUDE.md written the way an import is written: "@" at a line start or after whitespace, and the
# name ending at whitespace (an optional #fragment allowed). Used to find such tokens where Claude Code doesn't read
# them (in code or HTML) and to cut the import out of a CLAUDE.md before comparing the rest with AGENTS.md.
IMPORT_TOKEN_A = re.compile(r'(?:(?<=\s)|^)@(?:\./)?AGENTS\.md(?:#\S*)?(?=\s|$)', re.M)
IMPORT_TOKEN_C = re.compile(r'(?:(?<=\s)|^)@(?:\./)?CLAUDE\.md(?:#\S*)?(?=\s|$)', re.M)

_HERE = os.path.dirname(os.path.abspath(__file__))
_IMP = {}


def _ikey(t):
    return hashlib.sha1((t or '').encode('utf-8', 'surrogatepass')).hexdigest()


def _imports_tmp():
    work = os.environ.get('STUDY_WORK')
    if not work:
        d = _HERE
        while d != os.path.dirname(d) and not os.path.exists(os.path.join(d, '.git')):
            d = os.path.dirname(d)
        work = os.path.join(d, '.claude', 'work', 'agents-md-study', 'pipeline')
    return os.path.join(work, 'raw', 'tmp')   # inside raw/, so the texts are deleted with it


def prime_imports(texts):
    """Parse many files in one Node call. Results are cached by text hash."""
    todo = {}
    for t in texts:
        k = _ikey(t)
        if k not in _IMP:
            todo[k] = t or ''
    if not todo:
        return
    tmp = _imports_tmp(); os.makedirs(tmp, exist_ok=True)
    src, dst = os.path.join(tmp, 'imports_in.json'), os.path.join(tmp, 'imports_out.json')
    json.dump(todo, open(src, 'w'))
    subprocess.run([os.environ.get('NODE', 'node'), os.path.join(_HERE, 'claude_imports.mjs'), src, dst], check=True)
    _IMP.update(json.load(open(dst)))
    os.remove(src); os.remove(dst)


def imports_of(text):
    """The @-import paths Claude Code reads in this file, as written."""
    k = _ikey(text)
    if k not in _IMP:
        prime_imports([text])
    return _IMP[k]


def import_targets(text, base=''):
    """Repo paths the file's imports resolve to; base is the file's folder ('' for the repo root)."""
    out = set()
    for p in imports_of(text):
        if p.startswith('~/') or p.startswith('/'):
            continue   # outside the repo
        out.add(posixpath.normpath(posixpath.join(base, p)))
    return out


def link_target(text):
    t = (text or '').strip()
    return re.sub(r'^\./', '', t)


def classify_pair(c_sym, a_sym, ct, at):
    """Return (kind, detail dict). ct/at are texts (for a symlink: the link target)."""
    d = {}
    if c_sym and link_target(ct) == 'AGENTS.md':
        return 'symlink', {'dir': 'CLAUDE->AGENTS'}
    if a_sym and link_target(at) == 'CLAUDE.md':
        return 'symlink', {'dir': 'AGENTS->CLAUDE'}
    if c_sym and a_sym and link_target(ct) == link_target(at):
        return 'symlink', {'dir': 'both->third'}
    if c_sym or a_sym:
        return 'symlink-other', {'c_sym': c_sym, 'a_sym': a_sym}
    nonempty = len(norm_lines(ct))
    loose_import = bool(LOOSE_IMPORT_A.search(strip_code(ct)))
    if 'AGENTS.md' in import_targets(ct):
        d['nonempty'] = nonempty
        d['loose_regex_import'] = loose_import
        return ('import-shim' if nonempty <= 10 else 'import-plus'), d
    d['loose_regex_import'] = loose_import   # the looser pattern calls this an import; Claude Code doesn't
    # an @AGENTS.md written as an import, but where Claude Code doesn't read it: in code or in HTML
    d['broken_import_in_code'] = bool(IMPORT_TOKEN_A.search(ct or ''))
    # "@AGENTS.md" followed by more characters ("@AGENTS.md.", "@AGENTS.md.backup") or after "(": Claude Code
    # reads a different file name there, or nothing
    d['near_miss_import'] = not d['broken_import_in_code'] and bool(re.search(r'@(?:\./)?AGENTS\.md', ct or ''))
    # a regular file whose whole text is the other file's name. It may be a symlink checked out without symlink
    # support and committed that way, or a deliberate one-line pointer; the data can't tell which.
    d['symlink_as_text'] = link_target(ct) == 'AGENTS.md' or link_target(at) == 'CLAUDE.md'
    d['agents_imports_claude'] = 'CLAUDE.md' in import_targets(at)  # Codex reads this as text
    if identical(ct, at):
        return 'identical', d
    jac, cont, only_c, only_a, inter = similarity(ct, at)
    d.update(jaccard=round(jac, 3), containment=round(cont, 3), only_c=only_c, only_a=only_a, shared=inter)
    if jac >= 0.5:
        return 'near-copy', d
    c_ptr = bool(re.search(r'(?i)\bagents\.md\b', ct or ''))
    a_ptr = bool(re.search(r'(?i)\bclaude\.md\b', at or ''))
    d.update(c_ptr=c_ptr, a_ptr=a_ptr, c_lines=nonempty)
    if c_ptr or a_ptr:
        return 'pointer', d
    return 'separate', d


# ---------- conflict extraction ----------
NEG_BEFORE = re.compile(r"(?:\bnot|\bnever|n't|\bno|\binstead of|\bavoid|\brather than|\bover|\bwithout|\bnor|\bthan)\W+(?:\w+\W+){0,2}$", re.I)

JS_PM = {
    'pnpm': r'\bpnpm\b',
    'yarn': r'\byarn\b',
    'bun': r'\bbunx?\b',
    'npm': r'\bnpm\s+(?:install|i|ci|run|test|start|exec|uninstall|link|init|add|run-script|t)\b|\buse\s+npm\b|\bnpm\b(?=\s+(?:is|as)\s+(?:the\s+)?package\s+manager)',
}
PY_PM = {
    'uv': r'\buvx\b|\buv\s+(?:run|sync|add|pip|venv|lock|tool|init|remove|python)\b',
    'poetry': r'\bpoetry\b',
    'pip': r'\bpip3?\s+install\b',
    'pipenv': r'\bpipenv\b',
    'conda': r'\b(?:conda|mamba|micromamba)\b',
    'pdm': r'\bpdm\b',
}


def pm_counts(text, table):
    counts = {}
    for name, pat in table.items():
        n = 0
        for m in re.finditer(pat, text or '', re.I):
            if not NEG_BEFORE.search((text or '')[max(0, m.start() - 40):m.start()]):
                n += 1
        if n:
            counts[name] = n
    return counts


def dominant(c):
    if not c:
        return None
    top = max(c.values())
    tops = [k for k, v in c.items() if v == top]
    return tops[0] if len(tops) == 1 else None


TEST_RULES = [
    # (regex, ecosystem, canonical runner)
    (r'\b(npm|pnpm|yarn|bun)\s+(?:run\s+)?test(?::[\w:-]+)?\b', 'js', lambda m: m.group(1).lower() + ' test'),
    (r'\b(?:npx|pnpm\s+exec|pnpm\s+dlx|bunx|yarn)\s+(vitest|jest|mocha|playwright\s+test)\b', 'js', lambda m: m.group(1).split()[0].lower()),
    (r'(?<![\w/.-])(vitest|jest)(?:\s+run)?\b(?!\.config|\.setup|-dom|\s+config)', 'js', lambda m: m.group(1).lower()),
    (r'\b(uv\s+run|poetry\s+run|pdm\s+run|hatch\s+run|pipenv\s+run|python3?\s+-m)\s+pytest\b', 'py', lambda m: re.sub(r'\s+', ' ', m.group(1).lower()).replace('python3', 'python') + ' pytest'),
    (r'(?<![\w/.@-])(?<!run )(?<!-m )pytest\b(?!\.ini|-|\.fixture|\.mark|\.raises|\.param|\.approx|\.skip)', 'py', lambda m: 'pytest'),
    (r'\bpython3?\s+-m\s+unittest\b', 'py', lambda m: 'unittest'),
    (r'\btox\b(?:\s+-e)?', 'py', lambda m: 'tox'),
    (r'\bgo\s+test\b', 'go', lambda m: 'go test'),
    (r'\bcargo\s+(test|nextest)\b', 'rust', lambda m: 'cargo ' + m.group(1)),
    (r'\bdotnet\s+test\b', 'dotnet', lambda m: 'dotnet test'),
    (r'\b(?:bundle\s+exec\s+)?rspec\b', 'ruby', lambda m: 'rspec'),
    (r'\b(?:bin/)?rails\s+test\b|\brake\s+test\b', 'ruby', lambda m: 'rails test'),
    (r'\bmix\s+test\b', 'elixir', lambda m: 'mix test'),
    (r'\bphp\s+artisan\s+test\b', 'php', lambda m: 'artisan test'),
    (r'(?:vendor/bin/)?\bphpunit\b', 'php', lambda m: 'phpunit'),
    (r'\bdeno\s+test\b', 'deno', lambda m: 'deno test'),
    (r'\bswift\s+test\b', 'swift', lambda m: 'swift test'),
    (r'\bflutter\s+test\b', 'dart', lambda m: 'flutter test'),
    (r'(?:\./)?\bgradlew?\s+(?:[\w:-]+:)?test\b', 'jvm', lambda m: 'gradle test'),
    (r'\bmvnw?\s+(?:[\w.-]+\s+)?test\b', 'jvm', lambda m: 'mvn test'),
]


def test_cmds(text):
    out = {}
    for pat, eco, canon in TEST_RULES:
        for m in re.finditer(pat, text or '', re.I):
            if NEG_BEFORE.search((text or '')[max(0, m.start() - 40):m.start()]):
                continue
            out.setdefault(eco, set()).add(canon(m))
    # 'npx vitest' and 'vitest' are the same runner
    return out


FORMATTER_RULES = {
    'js': {'prettier': r'\bprettier\b', 'biome': r'\bbiome\b', 'dprint': r'\bdprint\b', 'oxfmt': r'\boxfmt\b'},
    'py': {'black': r'\bblack\s+(?:\.|--|-l\b|src|[\w-]+/)|\b(?:run|use|using|with|via)\s+black\b|\bblack\b(?=\s*(?:formatter|formatting|code style|-formatted))|\(black\)',
           'ruff': r'\bruff\s+format\b|\bruff\b(?=\s*(?:formatter|for formatting))', 'autopep8': r'\bautopep8\b', 'yapf': r'\byapf\b'},
}


def formatters(text):
    out = {}
    for eco, table in FORMATTER_RULES.items():
        for name, pat in table.items():
            for m in re.finditer(pat, text or '', re.I):
                if not NEG_BEFORE.search((text or '')[max(0, m.start() - 40):m.start()]):
                    out.setdefault(eco, set()).add(name); break
    return out


def style_values(text):
    vals = {}
    for line in (text or '').splitlines():
        low = line.lower()
        if 'indent' in low:
            m = re.search(r'\b([248])[- ]?spaces?\b', low)
            if m:
                vals.setdefault('indent', set()).add(m.group(1) + ' spaces')
            elif re.search(r'\btabs?\b(?! (?:key|bar|component|panel))', low) and not re.search(r'no tabs|not tabs|never tabs|instead of tabs', low):
                vals.setdefault('indent', set()).add('tabs')
        m = re.search(r'\b(single|double)[- ]quot', low)
        if m and 'quot' in low and not re.search(r'(?:no|not|never|avoid)\s+' + m.group(1), low):
            vals.setdefault('quotes', set()).add(m.group(1))
        if re.search(r'\b(?:no|without|omit|avoid)\s+semicolons?\b|\bsemi(?:colons?)?\s*[:=]\s*(?:false|no|none)\b', low):
            vals.setdefault('semicolons', set()).add('no')
        elif re.search(r'\b(?:use|always|with|require|include)\s+semicolons?\b|\bsemi\s*[:=]\s*true\b', low):
            vals.setdefault('semicolons', set()).add('yes')
        m = re.search(r'(?:line[- ]length|max(?:imum)?[- ]line(?:[- ]length)?|line[- ]width|print[- ]?width|max[- ]len)\D{0,25}?(\d{2,3})\b|\b(\d{2,3})[- ](?:char(?:acter)?s?|columns?|cols?)\b(?=[^.\n]{0,25}(?:line|wide|limit|max|per))', low)
        if m:
            v = int(m.group(1) or m.group(2))
            if 60 <= v <= 200:
                vals.setdefault('line length', set()).add(str(v))
    return vals


NEG_LINE = re.compile(r"\b(?:never|do not|don't|dont|must not|mustn't|should not|shouldn't|avoid|no need to|not allowed|forbidden|prohibited|NEVER|DO NOT)\b", re.I)
CMD_HEAD = re.compile(r'^(?:git|npm|pnpm|yarn|bun|npx|bunx|rm|docker|docker-compose|kubectl|terraform|make|cargo|go|pip|uv|poetry|python|python3|prisma|supabase|drizzle-kit|vercel|firebase|gh|curl|wget|sudo|chmod|brew|apt|apt-get|deno|turbo|nx|mvn|gradle|./gradlew|dotnet|rails|bundle|php|composer|flutter|xcodebuild|wrangler|sst|cdk|pulumi|helm|alembic|psql|mix|swift|just|tsc|eslint|prettier|biome|vitest|jest|pytest|ruff|black)\b')


def norm_cmd(c):
    c = re.sub(r'\s+', ' ', c.strip().strip('$').strip())
    toks = c.split(' ')
    if not toks or not CMD_HEAD.match(c):
        return None
    if (toks[0] in ('npm', 'pnpm', 'yarn', 'bun') and len(toks) >= 3 and toks[1] == 'run') or (toks[0] in ('gh', 'docker', 'kubectl', 'brew') and len(toks) >= 3 and not toks[2].startswith('-')):
        return ' '.join(toks[:3])
    return ' '.join(toks[:2]) if len(toks) >= 2 else toks[0]


NEG_CMD = re.compile(r"(?:\bnever|\bdo not|\bdon't|\bdont|\bmust not|\bmustn't|\bshould not|\bshouldn't|\bavoid|\bno need to|\bnot allowed to|\bforbidden to|\bprohibited from)\s+(?:[\w-]+\s+){0,3}?(?:running|run|use|using|execute|call|invoke|type|start|trigger)?\s*\**$", re.I)


def banned_and_allowed(text):
    """A command is banned when a negation sits right before it ("never run `X`", "do not use `X`")."""
    banned, allowed = set(), set()
    in_fence = False
    for line in (text or '').splitlines():
        s = line.strip()
        if s.startswith('```') or s.startswith('~~~'):
            in_fence = not in_fence; continue
        if in_fence:
            n = norm_cmd(s.lstrip('$ ').split(' #')[0])
            if n:
                allowed.add(n)
            continue
        for m in re.finditer(r'`([^`\n]{2,80})`', line):
            n = norm_cmd(m.group(1))
            if not n:
                continue
            before = line[max(0, m.start() - 60):m.start()]
            (banned if NEG_CMD.search(before) else allowed).add(n)
    return banned, allowed


COMMIT_NEG = re.compile(r"\b(?:never|do not|don't|must not|should not|without (?:being )?asked|unless (?:explicitly )?(?:asked|told|instructed|requested))\W+(?:\w+\W+){0,4}?(?:commit|push)\b|\b(?:commit|push)\w*\W+(?:\w+\W+){0,3}?(?:only )?(?:when|if|unless) (?:explicitly )?(?:asked|told|instructed|requested)", re.I)
COMMIT_POS = re.compile(r"\b(?:always\s+)?commit\s+(?:your|the|all|each|every|after|changes|often|frequently|regularly|when (?:you|done|finished))\b|\bcreate (?:a |small |atomic )?commits?\b|\bgit commit -m\b|\bcommit and push\b|\bpush (?:your|the) (?:changes|branch)\b", re.I)


def commit_policy(text):
    t = text or ''
    neg = bool(COMMIT_NEG.search(t))
    pos_lines = [l for l in t.splitlines() if COMMIT_POS.search(l) and not NEG_LINE.search(l)]
    return neg, bool(pos_lines)
