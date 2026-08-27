# Deployment Security and Release Boundary

Status: canonical deployment-security and release-hygiene guidance, current
through `RELEASE-HYGIENE.1A` (August 2026).

## Current Python runtime boundary

`DEPLOY-PYTHON.1A — CLOSED, NO SCRIPT CHANGE REQUIRED` records the product
owner's direct cPanel verification of the current split runtime:

- local development uses Python 3.14.7; and
- the GoDaddy/cPanel Python App `AMAXTW.COM/APP_READ` uses Python 3.11.15.

The cPanel virtualenv root contains the existing `3.11` environment, and the
available cPanel Python selector does not offer Python 3.14. The repository
`deploy_godaddy.sh` path
`/home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python` therefore remains
aligned with the verified production application and was not changed.

Any future `.xlsx` dependency for MO-S.6D Slice 8 must be reviewed and verified
against both local Python 3.14.x and deployment Python 3.11.15. No dependency,
virtualenv, deployment, Passenger, migration, or data change was made by this
closeout. This records the Python runtime boundary only; it is not broad hosting
or deployment QA.

`RELEASE-HYGIENE.0A` secured the administrator bootstrap helper, expanded
repository ignore coverage for local secrets/databases/backups/logs/audit and
agent artifacts, and removed previously committed local ServiceEvent audit
outputs. It did not create an external release archive.

`RELEASE-HYGIENE.1A` removed three committed local Calendar/My Serving recovery
snapshots from the current tree:
`calendar_serving_recovery_serving_card_conflicted_before_fix.html`,
`calendar_serving_recovery_staged_before_fix.patch`, and
`calendar_serving_recovery_worktree_before_fix.patch`. These were unreferenced
editor/conflict recovery artifacts, not runtime source, migrations, fixtures, or
canonical history. The cleanup also added ignore coverage for local recovery
directories, editor conflict leftovers, and similarly named staged/worktree
patch snapshots. Intentional historical migrations, operational runbooks,
release/security guidance, and application source remain preserved.

## Safe administrator bootstrap

`run_create_admin_godaddy.py` is a deployment helper, not a source of default
credentials. It contains no username, email, or password defaults and never
prints a password.

For an interactive deployment, provide the username as an argument or
environment value and let the script prompt securely:

```text
python run_create_admin_godaddy.py --username church-admin --email admin@example.org
```

For non-interactive automation, configure these values through the hosting
platform's protected environment configuration rather than placing secrets in
source control or a shell command:

- `DJANGO_SUPERUSER_USERNAME`
- `DJANGO_SUPERUSER_EMAIL` (optional)
- `DJANGO_SUPERUSER_PASSWORD`
- `DJANGO_SECRET_KEY` (required by production settings)

The password must pass Django's configured password validators and an additional
default-like credential check. Missing, weak, default-like, or username-matching
passwords fail closed. If the username already exists, the script also fails
closed unless the operator deliberately adds `--update-existing`; only that
explicit mode resets the password and restores active staff/superuser flags.

Do not redirect or log protected environment values. Rotate an environment
password after bootstrap if the hosting platform cannot remove it immediately.

## Future external release boundary

Repository hygiene remains separate from external deployment/security
validation and from delivery-layer package material such as `ship-pack v0.9.2`.
`RELEASE-HYGIENE.1A` did not build or expand a release archive. A future
`RELEASE-HYGIENE.0B` should use an allowlist-based builder and must exclude:

- `.git`, agent/tool state, IDE state, caches, screenshots, and test output;
- `.env`, credentials, local databases, database backups, logs, and media;
- local audit output and church-specific legacy import data;
- deployment-specific account paths or bootstrap secrets.

The release should include runtime apps and migrations, templates/static source,
requirements, generic production configuration guidance, a version/commit
manifest, and upgrade/backup instructions. The builder should refuse a dirty
tree, scan the finished archive for forbidden paths and secret-like values, and
produce a checksum and file manifest.
