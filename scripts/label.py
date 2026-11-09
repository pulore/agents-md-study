# Record manual review labels in raw/review_labels.json (deleted with raw/). Keys are the salted IDs that
# `analyze.py review X` prints. Notes are paraphrases and must not name a repo, owner, product or person.
#   python3 label.py ID near cosmetic|content|contradiction ["note"]
#   python3 label.py ID flag_pm|flag_pypm|flag_test|flag_fmt|flag_style|flag_ban|flag_commit confirmed|false-positive ["note"]
#   python3 label.py --file labels.tsv     (one "ID<TAB>key<TAB>value<TAB>note" per line; the file is read, not kept)
# Original vocabulary (3 Nov run): near = cosmetic (only a title, the tool's name or a generated-file banner differs),
# content (rules, commands or facts only one file has), contradiction (the two files disagree);
# flags = confirmed (a real conflict between the instructions) or false-positive.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RAW

VALID = {'near': {'cosmetic', 'content', 'contradiction'}}
for k in ('pm', 'pypm', 'test', 'fmt', 'style', 'ban', 'commit'):
    VALID['flag_' + k] = {'confirmed', 'false-positive'}
P = os.path.join(RAW, 'review_labels.json')
L = json.load(open(P)) if os.path.exists(P) else {}


def put(a, key, val, note=''):
    if key not in VALID or val not in VALID[key]:
        sys.exit(f'bad label {key}={val}')
    L.setdefault(a, {})[key] = val
    if note:
        L[a][key + '_note'] = note


if sys.argv[1] == '--file':
    for line in open(sys.argv[2]):
        if line.strip() and not line.startswith('#'):
            parts = line.rstrip('\n').split('\t')
            put(parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else '')
else:
    put(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else '')
json.dump(L, open(P, 'w'), indent=1)
print('labels stored for', len(L), 'items')
