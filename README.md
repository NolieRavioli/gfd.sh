# gfd.sh

Serverless personal site and dev log powered by AWS Lambda + API Gateway + S3, with Cognito Hosted UI authentication for posting.

## Overview

This project serves static/dynamic pages from a single Lambda handler and stores rendered posts in S3.

- Public pages: home (`/`), about (`/about`)
- Auth routes: login (`/login`), callback/debug (`/test`), logout (`/logout`)
- Protected page: new post form (`/post`)
- Protected API: create post (`POST /post`)

### Key behavior

- Unauthenticated users see `login` in nav.
- Authenticated users see `new post` + `logout`.
- Markdown input is rendered to HTML before being saved to S3.
- Missing required environment variables cause startup failure (no defaults).

---

## Architecture

- `lambda_function.py` — main router for API Gateway events
- `modules/config.py` — strict env loader (`require_env`)
- `modules/cognito_auth.py` — OAuth2/OIDC redirect + token exchange + signed session cookie
- `modules/s3_handler.py` — posts read/write in `posts.json`
- `modules/markdown_parser.py` — Markdown to HTML renderer
- `modules/html_builder.py` — template rendering + auth-aware nav + posts injection
- `www/` — HTML/CSS frontend templates

---

## Required Environment Variables (all required)

This app intentionally has **no fallback defaults**.

If any variable is missing or empty, import/startup fails with:

`RuntimeError: Missing required environment variable: <NAME>`

Set these in Lambda configuration:

| Name | Description | Example |
|---|---|---|
| `S3_BUCKET` | S3 bucket containing `posts.json` | `your-bucket-name` |
| `COGNITO_DOMAIN` | Cognito hosted domain (custom or AWS-provided), with `https://` | `https://login.example.com` |
| `COGNITO_CLIENT_ID` | Cognito app client ID | `xxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `COGNITO_CLIENT_SECRET` | Cognito app client secret | `<secret>` |
| `SESSION_SECRET` | Stable random secret for cookie signing (do not rotate casually) | random 64+ hex chars |
| `REDIRECT_URI` | OAuth callback URL configured in app client | `https://your-domain.com/test` |
| `LOGOUT_REDIRECT_URI` | Post-logout redirect URL configured in app client | `https://your-domain.com` |

### Generate `SESSION_SECRET`

Use any secure random generator, for example:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Use one fixed value in Lambda env vars. Do not generate it dynamically at runtime.

---

## Cognito App Client Configuration

In your Cognito user pool app client:

- Allowed callback URLs must include your `REDIRECT_URI`
- Allowed sign-out URLs must include your `LOGOUT_REDIRECT_URI`
- OAuth scopes should include at least: `openid`, `email`, `phone`
- OAuth flow should allow authorization code grant

---

## Data Model

Posts are stored in S3 key `posts.json`:

```json
{
  "posts": [
    {
      "timestamp": "2026-03-04 12:00:00 MST",
      "html": "<div class=\"textPost\">...</div>"
    }
  ]
}
```

Newest posts are inserted at index 0.

---

## Local Development

### Dependencies

`requirements.txt` includes `boto3` for local lint/tooling parity.

Install locally:

```bash
pip install -r requirements.txt
```

### Run model

This project is designed for Lambda/API Gateway events rather than a local Flask/Django server.

You can test by:

- Invoking `lambda_handler` with representative API Gateway event payloads, or
- Deploying to a dev Lambda stage and testing through your API endpoint

---

## Deploy Notes

1. Package and deploy Lambda code (`lambda_function.py`, `modules/`, `www/`).
2. Ensure API Gateway routes map to Lambda proxy integration.
3. Configure Lambda env vars (table above).
4. Verify Cognito app client callback/signout URLs match env vars.
5. Validate flow:
   - `/login` redirects to Cognito
   - `/test` sets session cookie and shows debug page
   - `/post` only works when authenticated
   - `POST /post` writes to S3

---

## Security Notes

- Do not commit `.env` or any secrets.
- `SESSION_SECRET` must remain stable across Lambda cold starts.
- Session cookie is `HttpOnly; Secure; SameSite=Lax`.
- The debug callback page truncates token display; remove or tighten for production if needed.

---

## License

No license file is currently defined.
