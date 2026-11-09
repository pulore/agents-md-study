# Check that a Claude Code build collects CLAUDE.md @-imports with the rule claude_imports.mjs copies (added 9 Nov 2026).
#   python3 check_claude_import_rule.py PATH_TO_CLAUDE_BINARY [MORE ...]
# claude_imports.mjs was copied from Claude Code 2.1.220. For each build, this finds the function that collects a file's
# imports and compares it with 2.1.220 piece by piece, with minified identifiers masked:
#   scanner  the @ pattern, the #fragment cut, the "\ " unescape and the rule for how a path may start; the call that
#            resolves the path against the file's folder is compared separately (resolver), since builds name it differently
#   walker   which markdown tokens are read: code and inline code skipped, HTML read only after its comments are removed
#   filter   the checks that skip special paths before the rule above: network shares and WSL paths in 2.1.220, one
#            combined check in later builds that also skips device and process files. In 2.1.317 Claude Code runs the
#            same combined check on a directory's own AGENTS.md path before reading it, so it doesn't stop a normal one.
#            A change here is printed for a reader to judge, not failed.
#   lexer    whether the markdown is lexed in CommonMark mode (marked with gfm off), as claude_imports.mjs does
import hashlib, re, sys

KEEP = set('''function let const var return for of if continue while null new Set void type code codespan html text
tokens items raw trimStart startsWith includes replace trim length indexOf substring replaceAll match exec add
dirname'''.split())
IMPORT_FN = re.compile(r'function [\w$]+\([\w$]+,[\w$]+\)\{let [\w$]+=new Set;function [\w$]+\([\w$]+\)\{let [\w$]+=/\(\?:\^\|\\s\)@'
                       r'.*?return [\w$]+\([\w$]+\),\[\.\.\.[\w$]+\]\}', re.S)
SCANNER = re.compile(r'function [\w$]+\([\w$]+\)\{let [\w$]+=/\(\?:\^\|\\s\)@.*?\.add\([\w$]+\)\}\}\}\}', re.S)
FILTER = re.compile(r'if\(((?:(?!if\().)*?)&&\([\w$]+\.startsWith\("\./"\)')
RESOLVER = re.compile(r'let ([\w$]+)=([\w$]+\([\w$]+,[^;]{1,40}\));[\w$]+\.add\(\1\)')
WALKER = re.compile(r'function [\w$]+\([\w$]+\)\{for\(let [\w$]+ of [\w$]+\)\{if\([\w$]+\.type==="code".*?\}\}(?=return )', re.S)

# masked SHA-256 of the scanner (filter replaced by FILTER) and the walker in Claude Code 2.1.220, and its filter
REFERENCE = {'scanner': '7c946f337f6ce26d5c7fd5f359aeccdff2f7d15b14e7c1c6cd4764712cbce032',
             'walker': '4727ad4df8a89a2a38dd452745a6c5c0035bcc1df4bfc90dda0b664eb5a67009',
             'filter': '!(ID(ID)&&!ID(ID))&&!ID(ID)'}


def mask(code):
    return re.sub(r'\b[A-Za-z_$][\w$]*\b', lambda m: m.group(0) if m.group(0) in KEEP else 'ID', code)


def sha(x):
    return hashlib.sha256(x.encode()).hexdigest()


def lexer_mode(text, fn_name):
    """How a file is lexed before fn_name reads its tokens: 'CommonMark (gfm off)', 'GFM' or 'not found'."""
    call = re.search(r'([\w$]+)=[^;]{0,200}?\?(?:new ([\w$]+)\(\{gfm:!1\}\)\.lex\([\w$]+\)|([\w$]+)\([\w$]+\)):void 0,'
                     r'[^;]{0,200}?' + re.escape(fn_name) + r'\(\1,', text)
    if not call:
        return 'not found'
    if call.group(2):
        return 'CommonMark (gfm off)'
    wrapper = re.search(r'function ' + re.escape(call.group(3)) + r'\([\w$]+\)\{return new ([\w$]+)\(\)\.lex\([\w$]+\)\}', text)
    if not wrapper:
        return 'not found'
    cls = re.search(r'class ' + re.escape(wrapper.group(1)) + r' extends [\w$]+\{.{0,200}?super\(\{gfm:(!0|!1|true|false)', text, re.S)
    if not cls:
        return 'not found'
    return 'CommonMark (gfm off)' if cls.group(1) in ('!1', 'false') else 'GFM'


def pieces(path):
    text = open(path, 'rb').read().decode('latin-1')
    fn = IMPORT_FN.search(text)
    if not fn:
        return None
    f = fn.group(0)
    sc = SCANNER.search(f).group(0)
    flt = FILTER.search(sc).group(1)
    res = RESOLVER.search(sc).group(2)
    core = sc.replace(flt, 'FILTER', 1).replace(res, 'RESOLVE', 1)
    return {'scanner': sha(mask(core)), 'walker': sha(mask(WALKER.search(f).group(0))),
            'filter': mask(flt), 'resolver': mask(res), 'lexer': lexer_mode(text, re.match(r'function ([\w$]+)', f).group(1))}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: check_claude_import_rule.py PATH_TO_CLAUDE_BINARY [MORE ...]')
    for path in sys.argv[1:]:
        got = pieces(path)
        print(path)
        if got is None:
            print('  import function NOT FOUND')
            continue
        for k in ('scanner', 'walker'):
            print(f'  {k:8} {"same as 2.1.220" if got[k] == REFERENCE[k] else "DIFFERENT from 2.1.220"}')
        print(f'  resolver {got["resolver"]}  (2.1.220: ID(ID,ID.dirname(ID)); later builds import dirname under a short name)')
        same_filter = got['filter'] == REFERENCE['filter']
        print(f'  filter   {"same as 2.1.220" if same_filter else "changed"}: {got["filter"]}')
        print(f'  lexer    {got["lexer"]}')
