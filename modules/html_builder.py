"""
Dynamic HTML page builder for gfd.sh.

Reads templates from www/, injects authentication-aware navigation,
and populates posts from S3.
"""
import os
import json
import html as _html

_MODULE_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_MODULE_DIR)
HTML_DIR     = os.path.join(_PROJECT_DIR, 'www')


# ── template helpers ────────────────────────────────────────────────

def _read_template(filename):
    """Read a file from the www/ directory."""
    filepath = os.path.join(HTML_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def _content_type(filename):
    if filename.endswith('.css'):
        return 'text/css'
    if filename.endswith('.js'):
        return 'text/javascript'
    if filename.endswith('.json'):
        return 'application/json'
    if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
        return f'image/{filename.rsplit(".", 1)[-1]}'
    return 'text/html'


# ── injection helpers ───────────────────────────────────────────────

def _inject_auth_nav(html_content, user, path='/'):
    """Replace <!-- AUTH_NAV --> with the correct nav links."""
    if user:
        active = ' class="active"' if path == '/post' else ''
        nav = (
            f'<a href="/post"{active}>new post</a>\n'
            f'      <a href="/logout">logout</a>'
        )
    else:
        nav = '<a href="/login">login</a>'
    return html_content.replace('<!-- AUTH_NAV -->', nav)


def _inject_posts(html_content):
    """Replace <!-- POSTS_PLACEHOLDER --> with post HTML from S3."""
    from modules.s3_handler import get_posts          # deferred to avoid circular import

    posts = get_posts()
    if posts:
        posts_html = '\n      '.join(p['html'] for p in posts)
    else:
        posts_html = (
            '<p style="color: var(--text-muted); text-align: center; '
            'padding: 2rem; font-family: var(--font-mono);">No posts yet.</p>'
        )
    return html_content.replace('<!-- POSTS_PLACEHOLDER -->', posts_html)


# ── page builders ───────────────────────────────────────────────────

def build_page(filename, user=None, path='/'):
    """Build a full API Gateway response for *filename*."""
    try:
        content = _read_template(filename)
    except FileNotFoundError:
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'text/plain'},
            'body': '404 Not Found',
        }

    ct = _content_type(filename)

    if filename.endswith('.html'):
        content = _inject_auth_nav(content, user, path)
        if filename == 'index.html':
            content = _inject_posts(content)

    return {
        'statusCode': 200,
        'headers': {'Content-Type': ct},
        'body': content,
    }


def build_debug_page(token_data, user_info):
    """Build the /test callback debug page showing Cognito response data."""
    email = _html.escape(user_info.get('email', 'unknown'))
    sub   = _html.escape(user_info.get('sub', 'unknown'))

    # Truncate sensitive tokens for display
    display = {}
    for k, v in token_data.items():
        if k in ('access_token', 'id_token', 'refresh_token'):
            display[k] = str(v)[:30] + '…[truncated]'
        else:
            display[k] = v

    token_json = _html.escape(json.dumps(display, indent=2))
    user_json  = _html.escape(json.dumps(user_info, indent=2))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auth Callback — gfd.sh</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <nav>
    <a href="/" class="nav-brand">gfd<span>.sh</span></a>
    <div class="nav-links">
      <a href="/">home</a>
      <a href="/about">about</a>
      <a href="/post">new post</a>
      <a href="/logout">logout</a>
    </div>
  </nav>
  <div style="max-width:800px;margin:2rem auto;padding:2rem;">
    <h1 style="font-family:var(--font-mono);color:var(--accent-green);">&#x2714; Cognito said yes</h1>
    <p style="color:var(--text-secondary);">Authentication successful — session cookie has been set.</p>

    <h2 style="font-family:var(--font-mono);color:var(--accent-blue);font-size:1.1rem;margin-top:2rem;">User Info</h2>
    <pre style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;padding:1rem;overflow-x:auto;color:var(--accent-green);font-family:var(--font-mono);font-size:.85rem;">{user_json}</pre>

    <h2 style="font-family:var(--font-mono);color:var(--accent-blue);font-size:1.1rem;margin-top:2rem;">Token Response</h2>
    <pre style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:8px;padding:1rem;overflow-x:auto;color:var(--accent-green);font-family:var(--font-mono);font-size:.85rem;">{token_json}</pre>

    <div style="margin-top:2rem;display:flex;gap:1rem;">
      <a href="/" class="btn btn-primary">Go to Homepage</a>
      <a href="/post" class="btn btn-outline">New Post</a>
    </div>
  </div>
  <footer>
    <div class="footer-domains">
      <a href="https://gfd.sh">gfd.sh</a>
      <a href="https://hondocabin.com" target="_blank" rel="noopener noreferrer">hondocabin.com</a>
    </div>
    <div class="footer-badge">Powered by <span>AWS Lambda</span> + <span>S3</span> + <span>Cognito</span></div>
  </footer>
</body>
</html>'''
