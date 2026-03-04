"""
gfd.sh — Main Lambda Handler

Thin router that dispatches requests to the appropriate module.
All business logic lives in modules/.

Routes:
  GET  /                → homepage with posts
  GET  /about           → about page
  GET  /post            → new-post form (requires auth → redirects to /login)
  GET  /login           → redirect to Cognito hosted UI
  GET  /test            → OAuth callback (exchange code, set cookie, show debug)
  GET  /logout          → clear session, redirect to Cognito logout
  GET  /styles.css      → stylesheet
  POST /post            → create a new post (requires valid session cookie)
"""
import json

from modules.s3_handler import save_post
from modules.markdown_parser import render_markdown
from modules.cognito_auth import (
    get_login_redirect_url,
    get_logout_redirect_url,
    handle_callback,
    get_session,
    make_cookie_header,
    clear_cookie_header,
)
from modules.html_builder import build_page, build_debug_page


# ── entry point ─────────────────────────────────────────────────────

def lambda_handler(event, context):
    method = event.get('httpMethod', event.get('method', ''))
    path   = event.get('path', '/')
    user   = get_session(event)

    if method == 'GET':
        return _handle_get(event, path, user)
    if method == 'POST':
        return _handle_post(event, path, user)
    return _text(405, 'Method Not Allowed')


# ── GET routes ──────────────────────────────────────────────────────

def _handle_get(event, path, user):
    # --- Auth flow ---
    if path == '/login':
        return _redirect(get_login_redirect_url())

    if path == '/test':
        params = event.get('queryStringParameters') or {}
        code = params.get('code')
        if not code:
            return _text(400, 'Missing authorization code from Cognito')
        try:
            token_data, user_info = handle_callback(code)
            cookie = make_cookie_header(user_info)
            body = build_debug_page(token_data, user_info)
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'text/html',
                    'Set-Cookie': cookie,
                },
                'body': body,
            }
        except Exception as e:
            return _text(500, f'Authentication error: {e}')

    if path == '/logout':
        return {
            'statusCode': 302,
            'headers': {
                'Location': get_logout_redirect_url(),
                'Set-Cookie': clear_cookie_header(),
            },
            'body': '',
        }

    # --- Protected page ---
    if path in ('/post', '/post.html'):
        if not user:
            return _redirect('/login')
        return build_page('post.html', user=user, path='/post')

    # --- Public pages ---
    if path == '/' or path in ('/index', '/index.html'):
        return build_page('index.html', user=user, path='/')

    if path in ('/about', '/about.html'):
        return build_page('about.html', user=user, path='/about')

    if path == '/styles.css':
        return build_page('styles.css', user=None, path=path)

    # --- Generic file serving ---
    filename = path.lstrip('/')
    if not filename:
        filename = 'index.html'
    if '.' not in filename:
        filename += '.html'
    return build_page(filename, user=user, path=path)


# ── POST routes ─────────────────────────────────────────────────────

def _handle_post(event, path, user):
    if path == '/post':
        if not user:
            return _text(401, 'Unauthorized — please log in via Cognito')
        try:
            data = json.loads(event.get('body') or '{}')
            content = data.get('content', '')
            if not content.strip():
                return _text(400, 'Post content cannot be empty')
            formatted_html = render_markdown(content)
            save_post(formatted_html)
            return _text(200, 'Post added successfully!')
        except json.JSONDecodeError:
            return _text(400, 'Invalid JSON body')
        except Exception as e:
            return _text(500, str(e))
    return _text(404, 'Not Found')


# ── response helpers ────────────────────────────────────────────────

def _redirect(url):
    return {'statusCode': 302, 'headers': {'Location': url}, 'body': ''}

def _text(code, body):
    return {'statusCode': code, 'headers': {'Content-Type': 'text/plain'}, 'body': body}
