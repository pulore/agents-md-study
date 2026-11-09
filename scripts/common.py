# Shared helpers for the CLAUDE.md / AGENTS.md study. Read-only GitHub API calls through the gh CLI.
#
# Where files go
#   WORK/raw  per-repo data while counting: repo names, node IDs, file texts, and the random salt.
#             Deleted with /bin/rm once the counts and labels are written (see run_all.sh purge).
#   WORK/agg  aggregates only (counts, intervals, API usage). No repo names, node IDs or file texts.
# WORK defaults to <git root>/.claude/work/agents-md-study/pipeline (git-ignored). Set STUDY_WORK to override.
# Never point it at /tmp or at a folder that gets committed.
import atexit, datetime, hashlib, hmac, json, os, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))


def _git_root(p):
    while p != os.path.dirname(p):
        if os.path.exists(os.path.join(p, '.git')):
            return p
        p = os.path.dirname(p)
    return None


WORK = os.environ.get('STUDY_WORK') or os.path.join(_git_root(HERE) or os.path.dirname(HERE), '.claude', 'work', 'agents-md-study', 'pipeline')
STUDY = WORK                           # kept for the original scripts, which used STUDY as the base folder
RAW = os.path.join(WORK, 'raw')        # per-repo data, deleted after counting (holds repo names and file texts)
AGG = os.path.join(WORK, 'agg')        # aggregates only, kept
os.makedirs(AGG, exist_ok=True)

# ---- sample design (fixed) ----
SEED = 20261103
K_DAYS = 420
FIRST_DAY = datetime.date(2008, 1, 1)
LAST_DAY = datetime.date(2026, 11, 2)  # fixed together with SEED: moving it reshuffles every day, so a rerun draws the original 420 days


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---- run date and frame window ----
# The frame is public, non-fork, non-archived repos with 10+ stars and a push in the 30 days to the run date.
# phase1 records the run date in agg/run_config.json; every later step reads it from there.
CONFIG_PATH = os.path.join(AGG, 'run_config.json')
_cfg = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}
_env_date = os.environ.get('STUDY_RUN_DATE')
if _env_date and _cfg.get('run_date') and _env_date != _cfg['run_date']:
    sys.exit(f"STUDY_RUN_DATE={_env_date} but {CONFIG_PATH} says {_cfg['run_date']}. Use a fresh STUDY_WORK for a new run.")
RUN_DATE = datetime.date.fromisoformat(_env_date or _cfg.get('run_date') or datetime.datetime.now(datetime.timezone.utc).date().isoformat())
PUSH_FROM = RUN_DATE - datetime.timedelta(days=30)
# is:public (added 9 Nov 2026): signed-in repository search also returns private repos the searching account can see.
FRAME_Q = f'stars:>=10 pushed:>={PUSH_FROM.isoformat()} archived:false is:public'   # forks are excluded by default in repo search


def run_config():
    return json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}


def log(*a):
    print(datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S'), *a, flush=True)


def all_days():
    n = (LAST_DAY - FIRST_DAY).days + 1
    return [FIRST_DAY + datetime.timedelta(days=i) for i in range(n)]


def sampled_days(k):
    import random
    days = all_days()
    random.Random(SEED).shuffle(days)
    return days[:k]


# ---- salted, irreversible IDs ----
# The salt is 32 random bytes in raw/salt.bin. It is deleted with raw/, after which no one (us included)
# can link a label back to a repo.
def _salt():
    p = os.path.join(RAW, 'salt.bin')
    if not os.path.exists(p):
        os.makedirs(RAW, exist_ok=True)
        with open(p, 'wb') as f:
            f.write(os.urandom(32))
    with open(p, 'rb') as f:
        return f.read()


_SALT = None


def anon(node_id, n=12):
    global _SALT
    if _SALT is None:
        _SALT = _salt()
    return hmac.new(_SALT, ('repo:' + node_id).encode(), hashlib.sha256).hexdigest()[:n]


def day_id(day):
    global _SALT
    if _SALT is None:
        _SALT = _salt()
    return hmac.new(_SALT, ('day:' + str(day)).encode(), hashlib.sha256).hexdigest()[:8]


# ---- API usage accounting (written to agg/api_usage/ when each script exits) ----
USAGE = {'search_repositories_requests': 0, 'search_code_requests': 0, 'rest_core_requests': 0,
         'graphql_requests': 0, 'graphql_cost_points': 0, 'rate_limit_sleeps': 0, 'failed_requests': 0}
_ulock = threading.Lock()
_T0 = now_iso()
import __main__ as _m
_MAIN = getattr(_m, '__file__', None) or sys.argv[0]       # read now: Python clears __main__.__file__ before atexit runs
_ARGV = list(getattr(sys, 'orig_argv', sys.argv))


def _count(k, n=1):
    with _ulock:
        USAGE[k] = USAGE.get(k, 0) + n


def _write_usage():
    if not any(v for k, v in USAGE.items()):
        return
    d = os.path.join(AGG, 'api_usage'); os.makedirs(d, exist_ok=True)
    main, argv = _MAIN, _ARGV
    after = argv[argv.index(main) + 1:] if main in argv else []
    name = os.path.basename(main).replace('.py', '') + ('-' + after[0] if after and after[0].isalpha() else '')
    rec = dict(USAGE, script=name, started_utc=_T0, ended_utc=now_iso())
    json.dump(rec, open(os.path.join(d, f'{name}-{os.getpid()}-{int(time.time())}.json'), 'w'), indent=1)


atexit.register(_write_usage)


def _rest_kind(path):
    return 'search_repositories_requests' if path.startswith('search/repositories') else (
        'search_code_requests' if path.startswith('search/code') else 'rest_core_requests')


def gh_rest(path, params=None, retries=6):
    """GET a REST path. Returns (status_ok, parsed_json_or_text)."""
    cmd = ['gh', 'api', '-X', 'GET', path]
    for k, v in (params or {}).items():
        cmd += ['-f', f'{k}={v}']
    for attempt in range(retries):
        _count(_rest_kind(path))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return True, json.loads(r.stdout)
            except Exception:
                return True, r.stdout
        err = (r.stderr or '') + (r.stdout or '')[:300]
        if 'rate limit' in err.lower() or 'HTTP 403' in err or 'HTTP 429' in err:
            log('rate limited on', path.split('?')[0].split('/')[0], '-> sleeping 65s')
            _count('rate_limit_sleeps')
            time.sleep(65)
            continue
        if 'HTTP 404' in err or 'HTTP 409' in err or 'HTTP 451' in err:
            _count('failed_requests')
            return False, err
        log('REST error', path.split('/')[0], err[:120], 'retry', attempt)
        time.sleep(5 * (attempt + 1))
    _count('failed_requests')
    return False, 'gave up'


def gh_graphql(query, variables, retries=5):
    body = json.dumps({'query': query, 'variables': variables})
    for attempt in range(retries):
        _count('graphql_requests')
        r = subprocess.run(['gh', 'api', 'graphql', '--input', '-'], input=body, capture_output=True, text=True)
        out = r.stdout or ''
        try:
            d = json.loads(out) if out else None
        except Exception:
            d = None
        if d and d.get('data') is not None:
            cost = ((d['data'].get('rateLimit') or {}) if isinstance(d['data'], dict) else {}).get('cost')
            _count('graphql_cost_points', cost if isinstance(cost, int) else 1)
            return d
        err = (r.stderr or '') + out[:300]
        if 'rate limit' in err.lower() or 'HTTP 403' in err or 'HTTP 429' in err:
            log('graphql rate limited -> sleeping 65s')
            _count('rate_limit_sleeps')
            time.sleep(65)
            continue
        log('GraphQL error', err[:160], 'retry', attempt)
        time.sleep(4 * (attempt + 1))
    _count('failed_requests')
    return None
