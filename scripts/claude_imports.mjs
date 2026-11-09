// Claude Code's @-import rule, run with the lexer Claude Code uses (added 9 Nov 2026).
//
// The rule is copied from the Claude Code 2.1.220 binary, from the function that collects a CLAUDE.md file's imports:
//   - the file, minus YAML front matter, is lexed by marked in CommonMark mode: new Lexer({ gfm: false });
//   - code blocks and inline code are skipped;
//   - an HTML token is read only if it starts with an HTML comment, and then only what is left once comments are removed;
//   - text tokens are scanned with /(?:^|\s)@((?:[^\s\\]|\\ )+)/g: the "@" must start the text or follow whitespace,
//     and the path runs to the next unescaped whitespace, so trailing punctuation stays part of it ("@AGENTS.md." is
//     the file "AGENTS.md.", which doesn't exist);
//   - "#..." is cut from the path and "\ " becomes a space;
//   - the path must start with "./", "~/", "/" (not "/" alone), or a letter, digit, ".", "_" or "-", and not with "@"
//     or one of #%^&*(); Windows UNC paths are skipped.
// Claude Code then resolves the path against the importing file's folder and loads the file if it exists; the Python
// side (textlib.import_targets) does the resolving.
//
// marked is pinned to 18.1.1 in package.json next to this file. Claude Code bundles its own copy of marked; the
// constructs that matter here (code, inline code, HTML, text) lex the same way across recent marked versions.
//
// Usage: node claude_imports.mjs IN.json OUT.json, where IN.json is {"key": "file text", ...} and OUT.json becomes
// {"key": ["path as written", ...], ...}. marked is loaded from $STUDY_NODE_MODULES, else from the node_modules next
// to this file, else from <git root>/.claude/work/agents-md-study/node/node_modules.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const candidates = [process.env.STUDY_NODE_MODULES, join(here, 'node_modules'), join(here, '..', '..', '..', '..', '..', '.claude', 'work', 'agents-md-study', 'node', 'node_modules')]
  .filter(Boolean);
const nm = candidates.find((d) => existsSync(join(d, 'marked', 'package.json')));
if (!nm) {
  console.error('marked not found. Install it: npm install --prefix <dir> --ignore-scripts marked@18.1.1, then set STUDY_NODE_MODULES=<dir>/node_modules');
  process.exit(2);
}
const req = createRequire(join(nm, 'resolve-from-here.js'));
const markedMod = await import(pathToFileURL(req.resolve('marked')).href);
const { Lexer } = markedMod.Lexer ? markedMod : markedMod.default;

function stripFrontMatter(text) {
  const m = /^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/.exec(text);
  return m ? text.slice(m[0].length) : text;
}

function scan(i, out) {
  const s = /(?:^|\s)@((?:[^\s\\]|\\ )+)/g;
  let a;
  while ((a = s.exec(i)) !== null) {
    let l = a[1];
    if (!l) continue;
    const c = l.indexOf('#');
    if (c !== -1) l = l.substring(0, c);
    if (!l) continue;
    l = l.replaceAll('\\ ', ' ');
    if (!l) continue;
    const unc = /^[\\/]{2}/.test(l) && !/^[\\/]{2}wsl(\$|\.localhost)[\\/]/i.test(l);
    if (unc) continue;
    if (l.startsWith('./') || l.startsWith('~/') || (l.startsWith('/') && l !== '/') ||
        (!l.startsWith('@') && !/^[#%^&*()]+/.test(l) && /^[a-zA-Z0-9._-]/.test(l))) {
      out.add(l);
    }
  }
}

function walk(tokens, out) {
  for (const s of tokens) {
    if (s.type === 'code' || s.type === 'codespan') continue;
    if (s.type === 'html') {
      const a = s.raw || '';
      const l = a.trimStart();
      if (l.startsWith('<!--') && l.includes('-->')) {
        const u = a.replace(/<!--[\s\S]*?-->/g, '');
        if (u.trim().length > 0) scan(u, out);
      }
      continue;
    }
    if (s.type === 'text') scan(s.text || '', out);
    if (s.tokens) walk(s.tokens, out);
    if (s.items) walk(s.items, out);
  }
}

export function importsOf(text) {
  const out = new Set();
  walk(new Lexer({ gfm: false }).lex(stripFrontMatter(text || '')), out);
  return [...out];
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [inPath, outPath] = process.argv.slice(2);
  const input = JSON.parse(readFileSync(inPath, 'utf8'));
  const result = {};
  for (const [k, t] of Object.entries(input)) result[k] = importsOf(t);
  writeFileSync(outPath, JSON.stringify(result));
}
