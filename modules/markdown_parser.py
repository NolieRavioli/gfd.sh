"""
Lightweight Markdown-to-HTML converter for gfd.sh.

Zero external dependencies — runs on bare AWS Lambda Python runtime.
Handles the most common Markdown syntax: headings, bold, italic,
strikethrough, inline code, fenced code blocks, links, images,
ordered/unordered lists, blockquotes, horizontal rules, and paragraphs.
"""
import re
import html as _html
import datetime
from zoneinfo import ZoneInfo

# Sentinel used to protect fenced code blocks from inline processing.
_CODE_PH = '\x00CB{}\x00'


# ── public API ──────────────────────────────────────────────────────

def render_markdown(text, username='unknown'):
    """
    Convert Markdown text to HTML, wrapped in a post div with username and timestamp.
    This is the main entry point for creating new posts.
    """
    body_html = _convert(text)
    timestamp = datetime.datetime.now(
        ZoneInfo("America/Denver")
    ).strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        '<div class="textPost" style="position: relative; padding-bottom: 1.2em;">'
        + f'<div class="post-author"><span class="username">{_html.escape(username)}</span> · '
        + f'<span class="post-time">{timestamp}</span></div>'
        + body_html
        + '</div>'
    )


# ── conversion pipeline ────────────────────────────────────────────

def _convert(text):
    """Full Markdown → HTML pipeline."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # 1. Stash fenced code blocks so they aren't touched by later passes
    code_store = []

    def _stash(m):
        lang = m.group(1) or ''
        raw = m.group(2)
        escaped = _html.escape(raw).replace('\t', '    ')
        idx = len(code_store)
        lang_attr = f' class="lang-{_html.escape(lang)}"' if lang else ''
        code_store.append(f'<code{lang_attr}>{escaped}</code>')
        return _CODE_PH.format(idx)

    text = re.sub(r'```(\w*)\n(.*?)```', _stash, text, flags=re.DOTALL)

    # 2. Block-level processing
    html_out = _blocks(text)

    # 3. Restore code blocks
    for idx, block in enumerate(code_store):
        html_out = html_out.replace(_CODE_PH.format(idx), block)

    return html_out


# ── block-level parsing ────────────────────────────────────────────

def _blocks(text):
    lines = text.split('\n')
    result = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        # blank line
        if not line.strip():
            i += 1
            continue

        # horizontal rule  --- / *** / ___
        if re.match(r'^\s*([-*_])\s*\1\s*\1[\s\1]*$', line):
            result.append('<hr>')
            i += 1
            continue

        # heading  # … ######
        hm = re.match(r'^(#{1,6})\s+(.*)', line)
        if hm:
            lvl = len(hm.group(1))
            result.append(f'<h{lvl}>{_inline(hm.group(2).strip())}</h{lvl}>')
            i += 1
            continue

        # blockquote  >
        if line.lstrip().startswith('>'):
            bq = []
            while i < n and lines[i].lstrip().startswith('>'):
                bq.append(re.sub(r'^>\s?', '', lines[i], count=1))
                i += 1
            result.append(f'<blockquote>{_blocks(chr(10).join(bq))}</blockquote>')
            continue

        # unordered list  - / * / +
        if re.match(r'^\s*[-*+]\s+', line):
            items = []
            while i < n and re.match(r'^\s*[-*+]\s+', lines[i]):
                txt = re.sub(r'^\s*[-*+]\s+', '', lines[i])
                items.append(f'<li>{_inline(txt)}</li>')
                i += 1
            result.append(f'<ul>{"".join(items)}</ul>')
            continue

        # ordered list  1.
        if re.match(r'^\s*\d+\.\s+', line):
            items = []
            while i < n and re.match(r'^\s*\d+\.\s+', lines[i]):
                txt = re.sub(r'^\s*\d+\.\s+', '', lines[i])
                items.append(f'<li>{_inline(txt)}</li>')
                i += 1
            result.append(f'<ol>{"".join(items)}</ol>')
            continue

        # code-block placeholder (already stashed)
        if '\x00' in line:
            result.append(line.strip())
            i += 1
            continue

        # paragraph — consecutive non-special, non-blank lines
        para = []
        while i < n and lines[i].strip():
            if re.match(r'^\s*(#{1,6}\s|[-*+]\s|\d+\.\s|>\s)', lines[i]):
                if para:
                    break
            if re.match(r'^\s*([-*_])\s*\1\s*\1[\s\1]*$', lines[i]):
                if para:
                    break
            if '\x00' in lines[i]:
                if para:
                    break
            para.append(lines[i])
            i += 1

        if para:
            content = '<br>'.join(_inline(l) for l in para)
            result.append(f'<p>{content}</p>')

    return '\n'.join(result)


# ── inline-level parsing ───────────────────────────────────────────

_INLINE_RE = re.compile(
    r'(`[^`]+`)'                # group 1 — inline code
    r'|(\!\[[^\]]*\]\([^)]+\))' # group 2 — image
    r'|(\[[^\]]+\]\([^)]+\))'   # group 3 — link
)


def _inline(text):
    """Process inline Markdown: code, images, links, then formatting."""
    tokens = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        s, e = m.span()
        if s > pos:
            tokens.append(_fmt(_html.escape(text[pos:s])))

        if m.group(1):  # inline code
            tokens.append(f'<code>{_html.escape(m.group(1)[1:-1])}</code>')
        elif m.group(2):  # image
            im = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', m.group(2))
            tokens.append(
                f'<img src="{_html.escape(im.group(2), quote=True)}" '
                f'alt="{_html.escape(im.group(1))}">'
            )
        elif m.group(3):  # link
            lm = re.match(r'\[([^\]]+)\]\(([^)]+)\)', m.group(3))
            tokens.append(
                f'<a href="{_html.escape(lm.group(2), quote=True)}" target="_blank">'
                f'{_html.escape(lm.group(1))}</a>'
            )
        pos = e

    if pos < len(text):
        tokens.append(_fmt(_html.escape(text[pos:])))

    return ''.join(tokens)


def _fmt(text):
    """Bold, italic, strikethrough on already-escaped text."""
    # bold+italic  ***text***
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    # bold  **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # italic  *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # strikethrough  ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    return text
