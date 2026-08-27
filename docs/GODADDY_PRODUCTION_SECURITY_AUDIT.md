# GoDaddy Production Security Safe Audit

Status: local static repository audit for `GODADDY-PRODUCTION-SECURITY.0A-SAFE-AUDIT`
(August 2026). Live hosting state remains unverified except for the later
product-owner Python App verification recorded below.

> **Current-state supersession — `DEPLOY-PYTHON.1A`:** after this static audit,
> the product owner directly verified that the GoDaddy/cPanel Python App
> `AMAXTW.COM/APP_READ` runs Python 3.11.15, that
> `/home/rsnwvvl103hc/virtualenv/app_read/` contains the existing `3.11`
> virtualenv directory, and that the available cPanel selector does not offer
> Python 3.14. The existing `deploy_godaddy.sh` Python path is aligned with that
> production configuration, so no script change was required. Local development
> uses Python 3.14.7. This supersedes only the earlier unverified Python
> version/path question; the audit chronology and all other live-hosting
> limitations remain unchanged.

## 1. Executive summary

This audit found no repository-proven BLOCKER or HIGH security finding in the
source-controlled GoDaddy deployment configuration.

The repository evidence shows an intentionally GoDaddy/cPanel-specific
deployment: cPanel runs `.cpanel.yml`, which invokes `deploy_godaddy.sh`; that
script syncs source into `/home/rsnwvvl103hc/app_read`; Passenger is expected to
load `passenger_wsgi.py`; and `passenger_wsgi.py` selects
`config.settings_godaddy`.

The most important unresolved risk is not a source-code fact: the live cPanel
application root, document root, domain mapping, HTTPS termination, proxy header
behavior, and configured environment variables were not inspected in this
phase. Those items are `MANUAL VERIFICATION REQUIRED`.

Finding counts:

| Severity | Count |
|---|---:|
| BLOCKER | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 2 |
| MANUAL VERIFICATION REQUIRED | 4 |

No actual tracked production secret was found. The repository contains a
development-only Django secret key in `config/settings.py`, while
`config/settings_godaddy.py` requires `DJANGO_SECRET_KEY` from the environment
and fails closed if it is absent.

## 2. Scope and explicit no-live-access statement

This audit was local static analysis only. It inspected source-controlled files
in `C:\dev\bible_reading_v2`.

No GoDaddy, cPanel, production domain, production database, live environment,
Passenger process, server `.htaccess`, deployment, restart, migration,
collectstatic, browser, curl, wget, Playwright, Selenium, or external security
probe was used.

## 3. Evidence limitations

Repository evidence can identify expected deployment architecture and static
configuration choices. It cannot prove:

- which cPanel values are currently configured;
- which file Passenger currently starts;
- whether the production domain is mapped to the intended app root;
- whether HTTPS is enforced before requests reach Django;
- what proxy headers are sent by GoDaddy/Passenger;
- whether live environment variables are present;
- live filesystem permissions or public exposure;
- live response headers, cookies, redirects, or TLS behavior.

Any conclusion requiring those facts is classified as
`MANUAL VERIFICATION REQUIRED`.

## 4. Current deployment architecture reconstructed from repo

| Area | Repository evidence | Classification |
|---|---|---|
| Production settings module | `passenger_wsgi.py` sets `DJANGO_SETTINGS_MODULE` to `config.settings_godaddy`. `deploy_godaddy.sh` also runs Django management commands with `--settings=config.settings_godaddy`. | Confirmed from source |
| Local development settings | `manage.py`, `config/wsgi.py`, and `config/asgi.py` default to `config.settings`. | Confirmed from source |
| cPanel deployment hook | `.cpanel.yml` runs `/bin/bash deploy_godaddy.sh`. | Hosting-specific |
| Source repo path | `deploy_godaddy.sh` expects `/home/rsnwvvl103hc/repositories/app_read`. | Hosting-specific |
| Application/deploy path | `deploy_godaddy.sh` syncs into `/home/rsnwvvl103hc/app_read`. | Hosting-specific |
| Passenger entry point | `deploy_godaddy.sh` verifies `passenger_wsgi.py`; `passenger_wsgi.py` creates the WSGI `application`. | Hosting-specific |
| Python runtime | Product-owner direct cPanel verification confirms Python 3.11.15 and the existing `3.11` virtualenv; `deploy_godaddy.sh` expects the aligned `/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python`. | Verified for the current cPanel Python App |
| App mount path | `settings_godaddy.py` sets `FORCE_SCRIPT_NAME = "/app_read"`, cookie paths under `/app_read/`, and static/media URLs under `/app_read/`. | Hosting-specific |
| Static files | `settings_godaddy.py` sets `STATIC_URL = "/app_read/static/"` and `STATIC_ROOT` under `BASE_DIR.parent / "public_html" / "app_read" / "static"`. `deploy_godaddy.sh` runs collectstatic. | Hosting-specific |
| Media files | `settings_godaddy.py` sets `MEDIA_URL = "/app_read/media/"` and `MEDIA_ROOT = BASE_DIR / "media"`. Serving behavior depends on cPanel/web-server configuration. | Manual verification required |
| Database backend | Production settings use SQLite at `BASE_DIR / "db.sqlite3"`. `deploy_godaddy.sh` expects the DB at `/home/rsnwvvl103hc/app_read/db.sqlite3`, excludes it from rsync, backs it up, runs SQLite quick checks, and then runs migrations. | Confirmed from source |
| Environment variables | Production settings require `DJANGO_SECRET_KEY`; accept `DJANGO_ALLOWED_HOSTS`; admin bootstrap uses `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD`. | Confirmed from source |

The working design should not be normalized into a generic Django deployment
without separately verifying the GoDaddy/Passenger topology.

## 5. Deployment-critical-file risk map

| File | Risk | Why it is deployment-sensitive |
|---|---|---|
| `.cpanel.yml` | CRITICAL | cPanel deployment task entry point. A bad change could stop deployment automation. |
| `deploy_godaddy.sh` | CRITICAL | Copies files, controls deployment paths, runs checks/migrations/collectstatic, and restarts Passenger. |
| `passenger_wsgi.py` | CRITICAL | Passenger WSGI entry point and production settings selector. |
| `config/settings_godaddy.py` | CRITICAL | Production settings, secret requirement, host/CSRF/static/media/cookie/database behavior. |
| `requirements.txt` | HIGH | Defines runtime dependency versions used by the deployed app. |
| `config/settings.py` | HIGH | Base settings imported by production settings; accidental production selection would use development defaults. |
| `manage.py` | HIGH | Default local management entry point; deployment script invokes it with production settings. |
| `run_migrate_godaddy.py` | HIGH | Production helper that runs migrations using GoDaddy settings if executed. |
| `run_collectstatic_godaddy.py` | HIGH | Production helper that clears and collects static files if executed. |
| `run_create_admin_godaddy.py` | HIGH | Production admin bootstrap helper. |
| `config/wsgi.py` | MODERATE | Standard Django WSGI module defaults to development settings; source evidence points Passenger to `passenger_wsgi.py` instead. |
| `config/asgi.py` | LOW | Defaults to development settings but no GoDaddy ASGI path is shown in source. |
| `.gitignore` | MODERATE | Helps keep local secrets, databases, backups, logs, and media out of source control. |
| `.htaccess` | N/A | No source-controlled `.htaccess` was found. Any live server `.htaccess` is outside this audit. |

## 6. Django production-setting review

| Item | Source evidence | Static classification |
|---|---|---|
| `DEBUG` | `settings_godaddy.py` sets `DEBUG = False`. | Confirmed safe from source |
| `SECRET_KEY` | Production reads `DJANGO_SECRET_KEY` and raises `ImproperlyConfigured` if absent. | Confirmed safe from source |
| Development `SECRET_KEY` | `config/settings.py` contains a development Django key and `DEBUG = True`; production entry points point to `settings_godaddy.py`. | Development-only from source |
| `ALLOWED_HOSTS` | Production reads comma-separated `DJANGO_ALLOWED_HOSTS`, with a temporary-domain fallback when unset. | LOW hardening opportunity |
| `CSRF_TRUSTED_ORIGINS` | Built as `https://{host}` for every allowed host. | Relies on configured host list |
| Cookie transport flags | `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`; cookie paths are scoped to `/app_read/`. | Confirmed safe from source |
| HTTPS redirect | `SECURE_SSL_REDIRECT = False`. Source does not prove whether GoDaddy enforces HTTPS before Django. | Manual verification required |
| Proxy header | No `SECURE_PROXY_SSL_HEADER` is configured. Source does not prove GoDaddy/Passenger proxy header behavior. | Manual verification required |
| Security headers | Default Django middleware includes `SecurityMiddleware` and `XFrameOptionsMiddleware`; no explicit HSTS/referrer/content-type hardening settings are configured. | Optional hardening only |
| Static files | `STATIC_ROOT` points under `public_html/app_read/static`; `deploy_godaddy.sh` runs collectstatic with `--clear`. | Hosting-specific |
| Media files | `MEDIA_ROOT` is under the app directory while `MEDIA_URL` is under `/app_read/media/`; live serving depends on web-server mapping. | Manual verification required |
| Database | Production uses SQLite in the app directory. | Confirmed from source; live permissions/backups unverified |

Do not change `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`,
`ALLOWED_HOSTS`, or CSRF behavior until GoDaddy's actual HTTPS/proxy/domain
topology is verified.

## 7. Startup/fail-closed review

| Variable or setting | Static behavior if absent |
|---|---|
| `DJANGO_SECRET_KEY` | Production settings raise `ImproperlyConfigured`. This fails closed rather than using the committed development key. |
| `DJANGO_ALLOWED_HOSTS` | Production settings fall back to `4z8.d4d.mytemp.website`. This may be intentional for the current GoDaddy temporary domain, but should be manually confirmed before cutover or cleanup. |
| Production settings module | Passenger and GoDaddy helper scripts set or pass `config.settings_godaddy`. Standard local `manage.py`, `config/wsgi.py`, and `config/asgi.py` default to `config.settings`. |
| Database path | SQLite path is derived from `BASE_DIR / "db.sqlite3"`. `deploy_godaddy.sh` checks that the expected DB file exists and is non-empty before migrating. |
| Admin bootstrap variables | Missing username or password fails closed in `run_create_admin_godaddy.py`; email is optional. |

## 8. Authentication/admin review

`run_create_admin_godaddy.py` is a manual bootstrap helper. It was inspected
statically only and was not executed.

Static conclusions:

- no username, email, or password defaults are hard-coded;
- passwords are read from `DJANGO_SUPERUSER_PASSWORD` or a non-echoing interactive
  prompt;
- password values are not printed;
- Django password validation is applied;
- additional default-like passwords are rejected;
- existing usernames fail closed unless `--update-existing` is explicitly used;
- user creation/update is wrapped in an atomic transaction;
- nothing in source indicates automatic administrator creation at web startup.

The test file `accounts/test_admin_bootstrap.py` contains test-only passwords
for bootstrap behavior coverage. They do not appear to be production secrets.

## 9. Secret handling

Targeted tracked-source search categories included Django secret keys, database
credentials, passwords, API tokens, private keys, SMTP credentials, OAuth
secrets, and admin credentials.

Results:

| Path | Category | Assessment |
|---|---|---|
| `config/settings.py` | Django secret key | Development-only setting from source; production settings do not use it. |
| `config/settings_godaddy.py` | Secret/env references | Uses environment variable references; no tracked production secret found. |
| `run_create_admin_godaddy.py` | Admin credential env names | Environment-variable and prompt handling only; no default credential found. |
| `accounts/test_admin_bootstrap.py` | Password-like test values | Test-only credentials. |
| `.gitignore` | Secret/database/backups/log ignore coverage | Ignores `.env`, databases, backups, logs, media, audit output, and recovery artifacts. |

No tracked `.env`, SQLite database, backup, private key, certificate, or pfx file
was found by the tracked-file scan.

## 10. Database configuration review

Production settings use SQLite:

- backend: `django.db.backends.sqlite3`;
- source of database path: `BASE_DIR / "db.sqlite3"`;
- deployment expectation: `/home/rsnwvvl103hc/app_read/db.sqlite3`;
- rsync excludes `db.sqlite3`, so deploys should not overwrite the live DB from
  the repository;
- `deploy_godaddy.sh` requires the DB to exist and be non-empty before
  migrations;
- `deploy_godaddy.sh` creates a timestamped pre-migration backup under
  `/home/rsnwvvl103hc/app_read/backups`;
- `deploy_godaddy.sh` runs SQLite `PRAGMA quick_check` on source DB and backup;
- migration execution is part of the deploy script, not part of this audit.

This audit did not connect to any database. Filesystem permissions, backup
retention, backup exposure, and operational restore readiness are manual checks.

## 11. Static/media/source-exposure architecture

Source evidence supports the following:

- `deploy_godaddy.sh` syncs from a repository path into an app path outside
  `public_html`;
- rsync excludes `.git`, `.venv`, `.env`, `db.sqlite3`, `media/`, `tmp/`,
  `backups/`, logs, Python caches, and bytecode;
- `STATIC_ROOT` is under `public_html/app_read/static`;
- `MEDIA_ROOT` is under the app directory, not under `public_html` by this
  source configuration;
- `MEDIA_URL` is `/app_read/media/`, but no repository-controlled rule proves
  how that URL is served in cPanel;
- no source-controlled `.htaccess` was found.

The repository does not prove that `.git`, `.env`, SQLite DB files, backups,
Python source, or settings files are publicly reachable. It also does not prove
the opposite for the live cPanel configuration. Document root and application
root mapping are `MANUAL VERIFICATION REQUIRED`.

## 12. Error/debug exposure

Static review found:

- production `DEBUG = False`;
- no tracked `debug_toolbar` usage;
- no debug-only URL include in `config/urls.py`;
- ordinary Django admin, login, logout, and app URLs are registered;
- `scripts/normalize_legacy_plan.py` has CLI-only `print()` output;
- `run_create_admin_godaddy.py` prints non-secret status messages only.

No repository-proven web stack-trace or debug-toolbar exposure was found.

## 13. Dependency posture

`requirements.txt` contains:

- `Django>=5.2,<5.3`;
- `asgiref==3.11.1`;
- `sqlparse==0.5.5`;
- `typing_extensions==4.15.0`;
- `tzdata==2026.2`.

`deploy_godaddy.sh` expects Python 3.11 at the GoDaddy virtualenv path now
verified for the current Python 3.11.15 cPanel application. Local development
uses Python 3.14.7, so a future dependency must be reviewed against both runtime
lines. No obvious development-only runtime package is listed in
`requirements.txt`.

This phase did not perform internet-based CVE or package research and did not
upgrade dependencies.

## 14. GoDaddy deployment assumptions requiring preservation

| Assumption | Repository evidence | Unknown | What could break if altered |
|---|---|---|---|
| cPanel runs `.cpanel.yml` | `.cpanel.yml` invokes `deploy_godaddy.sh`. | Whether live cPanel still uses this hook. | Deploy automation may stop. |
| Repository path is `/home/rsnwvvl103hc/repositories/app_read` | Hard-coded in `deploy_godaddy.sh`. | Whether account path remains current. | Deploy script may fail before copying. |
| App root is `/home/rsnwvvl103hc/app_read` | Hard-coded as `DEPLOYPATH`. | Whether Passenger app root matches it. | Passenger may load stale or missing code. |
| Python is `/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python` | Hard-coded in the deploy script; later product-owner cPanel verification confirms Python 3.11.15 and the existing `3.11` virtualenv. | Verified for the current cPanel Python App; Python 3.14 is not offered by the observed selector. | Changing this path without a separately verified cPanel runtime migration could break management commands. |
| Passenger entry point is `passenger_wsgi.py` | Deploy script requires it; file sets production settings. | Whether cPanel startup file points there. | App could use wrong settings or fail startup. |
| Settings module is `config.settings_godaddy` | `passenger_wsgi.py`, helpers, and deploy script select it. | Whether live environment overrides it. | Wrong settings could enable development behavior. |
| URL mount is `/app_read` | `FORCE_SCRIPT_NAME`, cookie paths, static/media URLs use it. | Whether domain mapping still requires the prefix. | Routing, cookies, CSRF, static files, or links could break. |
| Static files are served from `public_html/app_read/static` | `STATIC_ROOT` and deploy check point there. | Whether web server maps that directory as expected. | CSS/assets may disappear or stale assets may serve. |
| SQLite DB lives in app path | Production settings and deploy script expect it. | Live permissions and backup policy. | Data loss or app startup/migration failure. |
| `SECURE_SSL_REDIRECT` remains false | Production settings set it false. | Whether HTTPS is enforced upstream. | Changing it blindly may cause redirect loops or may be needed for security. |
| No `SECURE_PROXY_SSL_HEADER` is configured | Production settings omit it. | Which proxy headers GoDaddy sends. | Adding it blindly may mis-detect scheme; leaving it may be fine if upstream handles HTTPS. |

## 15. Findings table

| ID | Severity | Finding | Evidence | Recommended handling |
|---|---|---|---|---|
| F-01 | MANUAL VERIFICATION REQUIRED | HTTPS/proxy topology is not proven from source, so `SECURE_SSL_REDIRECT = False` and the absence of `SECURE_PROXY_SSL_HEADER` cannot be judged safely. | `settings_godaddy.py` sets `SECURE_SSL_REDIRECT = False` and no proxy header setting. | Observe cPanel/domain/proxy behavior in a separately approved phase before changing anything. |
| F-02 | MANUAL VERIFICATION REQUIRED | Live cPanel application root and document root are not proven from source. | Source expects app path outside `public_html` and static under `public_html/app_read/static`. | Verify configured cPanel app root and domain document root without editing. |
| F-03 | MANUAL VERIFICATION REQUIRED | Live environment variable presence is not verified. | Source requires `DJANGO_SECRET_KEY`; `DJANGO_ALLOWED_HOSTS` has a fallback. | Inspect variable names only in cPanel in a future observation phase. |
| F-04 | MANUAL VERIFICATION REQUIRED | Media serving and backup exposure depend on live web-server mapping and permissions. | `MEDIA_ROOT` is app-local; `MEDIA_URL` is public-looking; backups are app-local. | Verify public mapping and permissions without probing sensitive paths in this phase. |
| F-05 | LOW | `DJANGO_ALLOWED_HOSTS` falls back to a temporary GoDaddy domain when unset. | `settings_godaddy.py` fallback host. | After domain cutover is confirmed, consider requiring explicit hosts or removing obsolete temporary host acceptance. |
| F-06 | LOW | HSTS and other optional response-header hardening are not explicitly configured. | Production settings rely mostly on Django defaults plus cookie transport flags. | Consider only after HTTPS/proxy behavior is verified; do not change blindly. |

## 16. Future manual verification plan by risk tier

### Tier 1 - virtually zero-risk observation

- Inspect cPanel environment variable names, not values:
  `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and any superuser bootstrap
  variables if still present.
- Inspect configured cPanel application root.
- Inspect configured startup file/module.
- Python version/virtualenv-path inspection is complete for
  `DEPLOY-PYTHON.1A`: Python 3.11.15 and the existing `3.11` virtualenv are
  verified; the observed selector does not offer Python 3.14.
- Inspect domain mapping and document root.
- Visually confirm the production URL uses HTTPS.
- Inspect whether any live `.htaccess` exists and record its purpose without
  editing it.

### Tier 2 - read-only HTTP/browser inspection

Do not perform in this phase. In a separately approved phase:

- check response headers;
- check cookie flags;
- check HTTP-to-HTTPS redirect behavior;
- check whether `/app_read/static/css/app.css` is served as expected;
- use only safe non-mutating URLs agreed in advance.

### Tier 3 - potentially disruptive checks

`DO NOT PERFORM WITHOUT EXPLICIT PRODUCT-OWNER APPROVAL AND ROLLBACK PLAN`

- changing environment variables;
- changing Passenger settings;
- changing `.htaccess`;
- changing Python version;
- changing application root;
- changing database settings;
- restarting Passenger or the Python app;
- running migrations;
- running collectstatic;
- rotating credentials.

## 17. Risk-ordered future fix slices

1. Remaining manual observation slice: record cPanel app root, startup file,
   environment variable names, domain mapping, and HTTPS topology. Python
   version/path observation is complete under `DEPLOY-PYTHON.1A`.
2. HTTPS/header decision slice: only after topology evidence, decide whether
   Django or GoDaddy should own HTTPS redirects, proxy headers, HSTS, and related
   headers.
3. Host/domain cleanup slice: after domain cutover evidence, decide whether the
   temporary-domain fallback should remain, be narrowed, or be removed.
4. Static/media/source-exposure slice: verify mapping and adjust only with a
   rollback plan if source/media/backup exposure risk is confirmed.
5. Release archive slice: build the future allowlist-based release package
   described in `docs/DEPLOYMENT_SECURITY.md`.

## 18. Explicit no-change zones

Do not modify without separate approval and rollback planning:

- `.cpanel.yml`;
- `deploy_godaddy.sh`;
- `passenger_wsgi.py`;
- `config/settings_godaddy.py`;
- GoDaddy/cPanel Python Application settings;
- Passenger restart behavior;
- live `.htaccess`;
- live environment variables;
- live database path, file, permissions, or backups;
- production domain/TLS settings;
- production static/media mappings.

## 19. What this audit does not prove

This audit and the later narrow Python verification do not prove broad launch
readiness, end-to-end hosting safety, deployment correctness, or general live
GoDaddy state.

The audit proves only that no repository-proven BLOCKER or HIGH finding was
found in the inspected source-controlled deployment configuration. The later
product-owner evidence additionally verifies the current Python 3.11.15 cPanel
application and aligned `3.11` virtualenv path; other live hosting state remains
unverified.

## 20. Recommendation for the next step

Proceed only with the remaining Tier 1 manual observation checklist, with no
changes to runtime, config, deployment, data, credentials, Passenger,
`.htaccess`, or domain/TLS state. The Python version/path item is closed without
a script change. Use the results of the remaining observation to decide whether
any future HTTPS/header/host/static hardening slice is needed.

## Repository state captured for this audit

| Item | Value |
|---|---|
| Repo path | `C:\dev\bible_reading_v2` |
| Branch | `master` |
| Latest local commit | `e784270 chore: clean repository recovery artifacts` |
| Tracked divergence | `0 ahead / 0 behind` against `origin/master` from local tracking refs |
| Starting `git status --short` | clean, with Windows warning reading user global git ignore |
| Sync result | `git fetch origin` failed: `.git/FETCH_HEAD` permission denied; no permission workaround attempted |
| Files changed by this audit | `docs/GODADDY_PRODUCTION_SECURITY_AUDIT.md`; `docs/README.md` |
| Live access | none |
| Data mutation | none |
| Stage/commit/push/deploy/restart | none |
