# AGENTS.md

Project: bible_reading_v2 / CMS.

Shared instruction source for Codex, Claude Code, and other coding agents.

Work compactly. Keep changes scoped to the user's request. Optimize for token and runtime efficiency without reducing required work.

Do not commit, push, or stage files unless explicitly instructed.

## Discovery and Follow-up Reporting

Coding agents may notice related bugs, UX issues, missing tests, technical debt, or architecture risks while implementing the approved task.

Use this rule:

- Do not expand implementation scope just because a related improvement was discovered.
- Fix a discovered issue only when it is necessary to complete the approved task safely, or when it is clearly part of the approved scope.
- Otherwise, leave the implementation unchanged and report the item as a follow-up.
- Do not implement discovery items without explicit user approval.
- Do not use discovery items to justify schema changes, permission changes, source-of-truth changes, cross-app workflow changes, or broad redesign unless the current task explicitly authorizes that scope.

When any such items are found, include a final report section named:

`Discovery Log / Proposed Follow-ups`

For each item, include:

- short title
- file/page/module observed
- why it matters
- classification:
  * `must-fix before commit`
  * `safe follow-up`
  * `larger future milestone`
- suggested next action

## Task-Fit Review and Prompt Challenge

Coding agents should follow the approved prompt, but they are allowed and expected to flag concerns before implementation when the prompt appears unsafe, incomplete, inefficient, inconsistent with current code/docs, or likely to cause scope or architecture problems.

Use this rule:

- Do not silently implement a materially different approach from the approved prompt.
- Do not expand implementation scope just because a better or broader solution is possible.
- If the requested approach is questionable, pause before making broad changes and report a task-fit concern.
- ChatGPT and the user will review the concern and may issue a revised prompt.
- Small in-scope adjustments are allowed when necessary to complete the approved task safely, but they must be reported clearly in the final report.

A task-fit concern should be reported before implementation when the agent believes:

- the prompt conflicts with current code, docs, or product boundaries;
- the requested order is risky, such as implementation before a needed docs/design checkpoint;
- the task may require schema/model/migration changes not explicitly authorized;
- the task may change permissions, visibility, source of truth, or cross-app behavior;
- the task may affect ServiceEvent, My Serving, TeamAssignment, Bible Study, ChurchStructureMembership, Community Activities, or other bounded modules beyond the approved scope;
- the task may require a new dependency, framework, browser QA setup, data seeding approach, or deployment change not explicitly authorized;
- a smaller or safer implementation sequence is clearly preferable;
- the issue looks small but is actually a business-rule or product-direction decision.

When pausing for a task-fit concern, report:

- concern summary;
- why the current prompt may be suboptimal;
- recommended alternative;
- classification:
  * `small in-scope adjustment`
  * `scope-change requiring approval`
  * `larger future milestone`
- likely files/modules affected;
- risk if continuing with the original prompt.

Do not implement the alternative until the user explicitly approves it or provides a revised prompt.

## ChatGPT / Implementer Workflow Discipline

- ChatGPT and the user are the planner/reviewer/scope controller.
- The coding agent is the implementer.
- Work directly on `master` unless the user explicitly requests a feature branch.
- Do not create a feature branch unless explicitly requested.
- Do not commit, push, or stage files unless the user explicitly says to do so.
- Expected workflow: implement -> report changed files/tests/status -> user reviews with ChatGPT -> user commits/pushes manually, usually via GitHub Desktop.

## Scope Quality

- Complete the approved task thoroughly within scope.
- Do not under-fix directly related code paths, tests, UI states, language variants, or permission-visible states just to keep the diff small.
- Do not expand into unrelated redesign, business logic, schema changes, roadmap rewrites, deployment changes, or future modules.
- If a directly related issue is discovered, fix it when it is clearly part of the approved task; otherwise report it as a follow-up.
- Preserve existing runtime behavior unless the task explicitly approves changing it.

## Start-of-Task Discipline

At the start of each task:

- Run `git status --short`.
- Report any pre-existing dirty files before changing anything.
- Do not modify or stage unrelated dirty files.
- Keep docs-only tasks docs-only.
- Keep code tasks out of broad roadmap rewrites unless explicitly requested.

## Python / Django Command Discipline

On Windows/local work, prefer the project interpreter:

- `.venv\Scripts\python.exe`

Use it for Django commands unless there is a clear reason not to.

Examples:

- `.venv\Scripts\python.exe manage.py makemigrations --check`
- `.venv\Scripts\python.exe manage.py check`
- `.venv\Scripts\python.exe manage.py test accounts -v 2`

If using `python` instead of `.venv\Scripts\python.exe`, report which interpreter is being used or why `.venv` was not used.

## Verification

Use a split verification workflow to save tokens and runtime.

The coding agent must run only:

- required short checks;
- directly targeted tests for the changed code path;
- tests it added or modified;
- the smallest additional test class/methods needed to prove the immediate fix.

The user will run larger app suites and full regression manually when needed, then paste failing test names and traceback excerpts back to the coding agent for follow-up fixes.

Do not run full app suites or full project regression unless the user explicitly authorizes it.

For code, model, form, view, URL, template, or CSS changes where applicable, always run:

- `.venv\Scripts\python.exe manage.py makemigrations --check`
- `.venv\Scripts\python.exe manage.py check`
- `git diff --check`

For tests:

- Start with exact test methods or the smallest relevant test class.
- If the task changes one view/template/form, prefer tests that exercise that view/template/form.
- If the task adds or edits tests, run those tests directly.
- If targeted tests pass but broader coverage is prudent, report the exact recommended command for the user to run manually instead of launching it automatically.
- When the user reports failures from a manually run larger suite, fix only the reported failures and the directly related root cause, then rerun the failed test method/class plus minimal impacted targeted tests.

For accounts changes:

- `accounts` tests may exceed 10 minutes.
- Do not run the full `accounts` app suite unless explicitly authorized.
- Prefer exact accounts test methods/classes relevant to the change.
- If the user explicitly authorizes full `accounts` tests, start with timeout >= 900 seconds / 15 minutes.
- Do not run accounts tests with a 2-minute timeout first.
- Do not rerun only because the first timeout was too short.
- If a long-timeout app test still exceeds 15 minutes, stop and report partial output.

For UI or browser behavior changes:

- Perform explicit browser and mobile QA when practical and authorized by the task.
- If browser automation is unavailable, blocked, or would require unsafe commands, report the limitation clearly and say whether manual QA is still required.
- Browser QA does not replace targeted Django tests.
- Do not run broad browser sweeps when a narrow page/state check is sufficient.

## Test and Command Output Discipline

Testing should be token-efficient and evidence-driven.

- Prefer targeted tests first.
- Do not run full app suites or full project regression unless explicitly requested.
- Do not rerun the same passing targeted tests repeatedly.
- Do not rerun a long suite just to get a cleaner final report.
- If the user will run a larger suite manually, provide the exact command and stop.

When running long tests or commands:

- Do not repeatedly print "waiting", "still running", "polling", "test is running", or similar status messages.
- Either wait silently until the command finishes, or give one brief status update and stop producing output until there is a final result.
- Do not create repeated background monitor tasks or repeated polling loops just to watch test output.
- Do not repeatedly read the same test-output file while the command is still running.
- If output is redirected to a file, read it only when the command has completed, or at most once or twice if diagnosing a hang.
- If a test appears hung, report:
  - command run;
  - approximate elapsed time;
  - whether a process is still active;
  - last meaningful output;
  - recommended next action.
- Before launching another long test run, check whether a stale duplicate test process from a previous stopped session is still running.
- Do not kill unrelated Django dev servers or unrelated processes.
- Only stop stale test processes when they are clearly identified.

When the user provides manual test results:

- Treat the pasted failure output as the source of truth.
- Fix the root cause of the reported failure without broad unrelated changes.
- Rerun only the failed test method/class and directly related targeted tests.
- Ask the user to rerun the larger suite manually if broader confirmation is needed.

## Pre-existing Failures and Brittle Tests

- If a test fails, determine whether it is caused by the current change.
- If claiming a failure is pre-existing, provide evidence such as a clean-tree/stash comparison or a clear explanation tied to the failure.
- Do not hide, ignore, or normalize known failing tests.
- If the current task already touches the same test file or UI area, it is acceptable to fix a brittle assertion when the fix is test-only and does not change production behavior.
- Prefer precise assertions that target visible UI labels or behavior rather than broad raw-page substring checks that can accidentally match JavaScript identifiers, CSS class names, or unrelated markup.

## Windows Browser QA / Playwright Fallback

Keep the Django/Python app environment separate from the Node/Playwright browser QA runtime.

- Use the project Python interpreter: `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe`
- Start Django with `--noreload`: `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- Prefer the official browser control workflow for the current coding tool when browser QA is required.
- If the in-app browser fails because of a Windows sandbox/browser startup issue, use the headless Chromium fallback.
- Do not install Node dependencies in this Django repo for browser QA.
- Do not create `package.json`, `package-lock.json`, or `node_modules` in this repo only for Playwright/browser QA.
- Use the external browser QA runtime specified by the task.
- Known external runtimes:
  - `C:\dev\codex-browser-qa`
  - `C:\dev\claude-browser-qa`
- When running Node/Playwright scripts from this repo, set `NODE_PATH` to the selected runtime's `node_modules` directory.
  - Example: `$env:NODE_PATH = "C:\dev\claude-browser-qa\node_modules"`
- Do not rely on cached runtime paths or partial bundled Playwright shims.
- Temporary browser QA helper scripts may be created only when necessary.
- Temporary browser QA helper scripts must be narrow in purpose and removed before the final report.
- Browser QA must not create QA users or seed ministry/business data unless explicitly authorized.
- Creating an authenticated session row for an existing staff account is allowed only for QA login/session purposes, and must be reported clearly.

Reason:

- The Django/Python environment is the source of truth for app checks.
- Browser QA dependencies are intentionally externalized to avoid polluting this Django repo with Node artifacts.
- The Windows Codex browser sandbox can fail, so fallback QA should be deterministic instead of repeatedly searching cached runtime/plugin paths.

## Endpoint-Safe Browser QA Commands

Do not run browser QA through long inline PowerShell scripts.

Do not use PowerShell to dynamically write and execute temporary Node/Playwright scripts with embedded JavaScript, session cookies, or browser automation logic.

Do not use patterns like:

- `powershell.exe -NoProfile -Command "..."`
- `Set-Content` to create a temporary `.js` browser QA script
- setting `NODE_PATH` inside a long inline PowerShell command
- running `node $script` from that same inline PowerShell command
- deleting the script with `Remove-Item` in the same command
- embedding Django `sessionid` cookies inside a long inline command
- launching hidden or background processes through PowerShell
- `System.Diagnostics.ProcessStartInfo`
- `Start-Process`
- `Start-Job`

Reason:

- Endpoint security may flag long inline PowerShell plus dynamic script creation, session-cookie injection, browser automation, hidden process launch, or cleanup/deletion behavior as malicious-looking.
- This has already triggered Netgear Armor / Antivirus blocks for PowerShell commands that attempted to start Django runserver and run Playwright browser QA.

Allowed safer alternatives:

- Prefer a user-started foreground Django server:
  - `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- Prefer checked-in or clearly reviewed QA scripts only when explicitly authorized.
- Use short, transparent commands.
- If browser QA cannot run without long inline PowerShell or endpoint-security-looking behavior, stop and report browser QA as blocked.
- Report the exact manual QA URL and steps instead of trying more launcher/script variants.
- Never ask the user to disable Netgear Armor, antivirus, or endpoint protection.

## QA Data Seeding

- Do not use long inline PowerShell commands to run `manage.py shell -c` for QA data seeding.
- Do not create QA users, set passwords, or insert dev DB records through long PowerShell one-liners.
- Endpoint security may flag PowerShell plus long inline scripts plus user creation, password setting, or database writes as malicious-looking behavior.
- Prefer Django tests, factories, fixtures, existing test setup, or the app UI for QA data.
- For browser/manual QA that needs seeded data, use existing safe dev data if available.
- If seeded data is unavoidable, create a short reviewed Django management command or fixture only when explicitly authorized.
- If a one-off shell command is unavoidable, keep it short and transparent, and ask or report before running it.
- Never bypass endpoint security.
- Never suggest disabling Netgear Armor, antivirus, or endpoint protection.

## Planning Discipline

For schema/model/migration changes, permission changes, source-of-truth changes, cross-app workflow changes, or new staff workflows:

- Do a docs/design plan first unless the prompt explicitly authorizes implementation.
- Do not jump directly into implementation from vague product feedback.
- Record real pilot feedback in backlog/planning docs before implementation when it changes model, workflow, permissions, or module boundaries.

For docs-only planning tasks:

- Do not create a separate meta-plan unless asked.
- Directly inspect the relevant docs and update the requested planning documents.
- Keep the update compact and scoped.

## UI / UX Wording Guardrails

Normal-user UI:

- Do not expose internal model names, IDs, codes, enum values, field names, source-of-truth language, runtime/foundation/legacy architecture terms, or implementation language.
- Use pastoral/user-intent wording.
- Keep EN/ZH copy paired and natural.
- Do not translate user data, enum values, or identifiers unless the UI already has explicit localized labels.

Staff/admin UI:

- Staff UI may show operational transition context when it helps safe decisions.
- Use staff workflow language, not architecture-doc language.
- Avoid labels like “future foundation,” “runtime source of truth,” or “legacy sync target” in visible UI unless the user explicitly asks for technical wording.
- Clearly distinguish current active group data from approval/membership records when both appear together.
- Notes and admin copy must avoid sensitive pastoral, medical, financial, or counseling details unless explicitly authorized.

## Project Constraints

Do not migrate these consumers from `Profile.small_group` to `ChurchStructureMembership` unless explicitly authorized:

- `/studies/`
- Reading progress
- `ServiceEvent`
- My Serving
- Other existing consumers that currently use legacy models or `Profile.small_group`

Do not add the following unless explicitly authorized:

- Audience filtering
- Community Activities implementation
- Notifications
- Attendance
- Announcements
- Care workflows
- File center
- Permission matrix expansion
- Availability
- Swap requests
- Reminder automation
- Checklist engine
- Automatic scheduling engine
- LightingTeam-specific model
- ChurchStructureMembership-based serving role inference

Keep ServiceEvent, MinistryTeam, TeamAssignment, and My Serving workflows generic unless a separate plan authorizes a narrower workflow.

Real pilot feedback has priority over speculative roadmap work, but pilot feedback must not bypass the explicit non-goals above without a separate planning decision.

## Local Artifacts and Generated Files

- Do not stage or commit local tool/harness artifacts.
- Never commit:
  - `.claude/`
  - `.claude/scheduled_tasks.lock`
  - `.playwright-mcp/`
  - temporary browser QA scripts
  - screenshots
  - local credentials
  - local database files
  - generated cache files
  - test output logs unless explicitly requested
- If such files appear in `git status`, report them separately and leave them unstaged.

## Final Report Format

Keep reports compact. Include:

- starting `git status --short`;
- ending `git status --short`;
- files changed;
- behavior changed or preserved;
- verification commands and final results;
- tests intentionally not run and why;
- recommended manual app/full-suite commands for the user, when broader verification is needed;
- browser/mobile QA status when UI changed;
- any pre-existing dirty files left untouched;
- whether runtime behavior changed;
- confirmation of no commits/staging;
- confirmation of no schema/migration/business-logic/deployment changes unless explicitly approved.
- Discovery Log / Proposed Follow-ups, when related issues or improvement opportunities were discovered but not implemented;
- Task-fit concerns or prompt-challenge recommendations, when the agent found the approved prompt unsafe, incomplete, inefficient, inconsistent with current code/docs, or better handled as a revised prompt;


Do not claim browser/mobile QA passed if it was blocked or only partially completed.
Do not claim a full app suite or full regression passed unless it was actually run to completion.
