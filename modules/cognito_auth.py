"""
Cognito OAuth2 / OIDC authentication for AWS Lambda.

Handles the full OAuth authorization-code flow:
  /login   → redirect to Cognito hosted UI
  /test    → exchange code for tokens, set session cookie
  /logout  → clear session cookie, redirect to Cognito logout

Session state is stored in a signed cookie (HMAC-SHA256).
No external dependencies beyond the Python standard library.
"""
import json
import base64
import hmac
import hashlib
import time
import urllib.request
import urllib.parse
from modules.config import require_env

# ── configuration (from Lambda environment variables) ───────────────

COGNITO_DOMAIN        = require_env('COGNITO_DOMAIN')
COGNITO_CLIENT_ID     = require_env('COGNITO_CLIENT_ID')
COGNITO_CLIENT_SECRET = require_env('COGNITO_CLIENT_SECRET')
SESSION_SECRET        = require_env('SESSION_SECRET')
REDIRECT_URI          = require_env('REDIRECT_URI')
LOGOUT_REDIRECT_URI   = require_env('LOGOUT_REDIRECT_URI')
SCOPES               = 'email openid phone'


# ── URL builders ────────────────────────────────────────────────────

def get_login_redirect_url():
    """Return the Cognito authorization URL the browser should be sent to."""
    params = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id':     COGNITO_CLIENT_ID,
        'redirect_uri':  REDIRECT_URI,
        'scope':         SCOPES,
    })
    return f'{COGNITO_DOMAIN}/oauth2/authorize?{params}'


def get_logout_redirect_url():
    """Return the Cognito logout URL."""
    params = urllib.parse.urlencode({
        'client_id':  COGNITO_CLIENT_ID,
        'logout_uri': LOGOUT_REDIRECT_URI,
    })
    return f'{COGNITO_DOMAIN}/logout?{params}'


# ── token exchange ──────────────────────────────────────────────────

def handle_callback(code):
    """
    Exchange an authorization code for tokens.
    Returns (token_data_dict, user_info_dict).
    """
    token_endpoint = f'{COGNITO_DOMAIN}/oauth2/token'

    body = urllib.parse.urlencode({
        'grant_type':   'authorization_code',
        'code':         code,
        'redirect_uri': REDIRECT_URI,
        'client_id':    COGNITO_CLIENT_ID,
    }).encode()

    auth = base64.b64encode(
        f'{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}'.encode()
    ).decode()

    req = urllib.request.Request(token_endpoint, data=body)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Authorization', f'Basic {auth}')

    resp = urllib.request.urlopen(req)
    token_data = json.loads(resp.read().decode())

    # Decode user claims from the id_token JWT payload
    user_info = _decode_jwt_payload(token_data['id_token'])

    return token_data, user_info


def _decode_jwt_payload(token):
    """Decode the payload of a JWT without signature verification.
    (Safe here because we just received it from Cognito over HTTPS.)"""
    payload_b64 = token.split('.')[1]
    # Base64 padding
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += '=' * padding
    return json.loads(base64.urlsafe_b64decode(payload_b64))


# ── session cookies ─────────────────────────────────────────────────

def make_cookie_header(user_info):
    """Create a Set-Cookie header value containing signed session data."""
    # Try to get username from cognito:username claim, fallback to email prefix
    username = user_info.get('cognito:username') or user_info.get('email', 'unknown').split('@')[0]
    payload = {
        'email':    user_info.get('email', ''),
        'username': username,
        'sub':      user_info.get('sub', ''),
        'exp':      int(time.time()) + 86400,   # 24 h
    }
    data_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SESSION_SECRET.encode(), data_b64.encode(), hashlib.sha256).hexdigest()
    value = f'{data_b64}.{sig}'
    return f'session={value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400'


def clear_cookie_header():
    """Return a Set-Cookie header that expires the session cookie."""
    return 'session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0'


def get_session(event):
    """Read and validate the session cookie from an API Gateway event.
    Returns a dict with user info (email, sub, exp) or None."""
    headers = event.get('headers') or {}
    cookie_header = headers.get('Cookie', headers.get('cookie', ''))
    if not cookie_header:
        return None

    # Parse cookie string
    cookies = {}
    for item in cookie_header.split(';'):
        item = item.strip()
        if '=' in item:
            name, value = item.split('=', 1)
            cookies[name.strip()] = value.strip()

    token = cookies.get('session')
    if not token:
        return None

    return _validate_session(token)


def _validate_session(cookie_value):
    """Verify HMAC signature and expiration. Returns user dict or None."""
    try:
        data_b64, sig = cookie_value.rsplit('.', 1)
        expected = hmac.new(
            SESSION_SECRET.encode(), data_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(data_b64))
        if payload.get('exp', 0) < time.time():
            return None
        return payload
    except Exception:
        return None
