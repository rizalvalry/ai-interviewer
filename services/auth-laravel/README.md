# auth-laravel

Laravel application. Deploy target: **Hostinger cPanel** (PHP-FPM, MySQL).

Not yet implemented — this is a repo gap, not a scaffold. See
`docs/architecture/deployment-strategy.md` for the full reasoning (token
issuance signed with a shared `AUTH_SECRET`, verified by
`services/asr-suggest/auth.py`) and `services/asr-suggest/auth.py` for the
token contract this service must satisfy once built.
