# Deployment Security and Release Boundary

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

`RELEASE-HYGIENE.0A` does not build a release archive. A future
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
