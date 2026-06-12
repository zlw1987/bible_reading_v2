# Today Page as Personal Action Center — Planning Doc (TODAY-HOME.1A)

Status: TODAY-HOME.1A / 1A.1 docs-only product planning complete; TODAY-HOME.1B read-only IA restructure complete; TODAY-HOME.1D linked Bible Study role chips complete.
Revised by TODAY-HOME.1A.1 after user product decisions and updated after TODAY-HOME.1D: (1) the week strip shows **Church Gatherings / 教会聚会** — visible upcoming `ServiceEvent` rows from the Church Gatherings module — with no hardcoded "special `event_type`" guessing; (2) Bible-study role chips are read-only and linked-user-only, and Bible-study role confirmation is not planned unless a real need appears.

Scope guardrails inherited from AGENTS.md and the task prompt:

- No runtime visibility change from Today itself. ServiceEvent visibility stays SE-AS.4 behavior (audience rows when present, legacy `scope_type`/`district`/`small_group` fallback otherwise), and Today uses the already-visible Bible Study v2 meeting selected by `BibleStudyMeeting.can_be_seen_by`.
- Since CS-CORE.2C-B, `ChurchStructureMembership` is a runtime visibility source for Bible Study v2 `BibleStudyMeeting` ordinary-member visibility; Today must not add any separate visibility rule on top of that.
- No Community Activities implementation, no notifications, no attendance, no care workflows.
- Today remains a personal page for the signed-in user. It must not become a staff/admin dashboard; staff operational views live under `/staff/` and the module manage pages.
- Ordinary users see only their own visible/personal items.

## 1. Current-State Audit

### Route / view / template

- Route: `""` → `reading.views.home`, name `home` (`reading/urls.py`). Top nav labels it "Today" / 「今日」 (`templates/base.html`).
- View: `reading/views.py` `home()` (~line 593).
- Template: `templates/reading/home.html`.

### Data currently shown

1. **Today's reading (hero, one card per enrolled active plan).** Built from `PlanEnrollment` → `ActivePlan` → `ReadingPlanDay` + `CheckIn`. Shows plan day, progress bar, today's passages with reader/audio links, memory verse, check-in state, plan action links. Ended/not-started plans are skipped.
2. **Needs your attention / This Week serving context.** TODAY-HOME.1B replaced the former single `today_serving_summary` card with pending ministry confirmations in Needs your attention and compact serving notes on related Church Gathering rows in This Week.
3. **"Where to go next" static cards.** Bible Study, Prayer, My Serving links.
4. **Upcoming Bible studies (up to 3).** Replaced by TODAY-HOME.1B: Today now shows the user's relevant v2 `BibleStudyMeeting`; the legacy `BibleStudySession` block is no longer part of Today.

### Pre-1B limitations now resolved by TODAY-HOME.1B

- **One serving item only.** Resolved by the three-zone IA: pending ministry confirmations appear in Needs your attention, and confirmed/pending serving context can appear as compact notes on matching Church Gathering rows.
- **Bible Study section uses the legacy session model.** Resolved by replacing the legacy `BibleStudySession` block with the user's relevant v2 `BibleStudyMeeting`.
- **No personal Friday role surfacing.** `BibleStudyMeetingRole` rows linked to the user are not shown anywhere on Today (only inside the meeting detail page).
- **No Church Gathering awareness.** Resolved by adding visible Church Gatherings in This Week, excluding draft/cancelled rows and keeping existing visibility rules.
- **No time framing.** Resolved by the Needs your attention / Today / This Week structure.
- **Multi-plan users get a tall page.** Each enrolled plan renders a full hero card before anything else appears.

### Existing product-direction tension (must be decided consciously)

Pilot-era docs (`LIGHTING_PILOT_PREFLIGHT_REQUIREMENTS.md`, `LIGHTING_TEAM_PILOT_QA_CHECKLIST.md`, `IA_NAVIGATION_REDESIGN_PLAN.md`, `BIBLE_STUDY_V1_QA_CHECKLIST.md`) state that **Today stays a lightweight summary surface and My Serving owns serving details/management**. The "action center" hypothesis evolves this. This plan keeps the boundary by interpreting "action center" as: *Today surfaces and counts the user's personal items and links to the owning module page for the action itself*. Today does not become the management or detail surface. If the user instead wants in-place actions on Today (e.g., confirm buttons), that is an explicit product decision recorded in Section 8.

## 2. Product Goal

**The question the page answers:** "As a church member, what should I do today, and what is coming for me this week?"

**Who it is for:** the ordinary signed-in member. Staff users see the same *personal* page (their own reading, their own assignments/roles); staff operations stay in `/staff/`, `/events/`, `/assignments/`, `/studies/...manage/`.

**What it must not become:**

- a staff/admin dashboard or coverage view;
- a notifications/announcements feed;
- an attendance, care, or checklist workflow;
- a duplicate of My Serving, `/events/`, or `/studies/` detail surfaces;
- a surface that fakes data the models do not have (e.g., Bible-study role confirmation, invitations).

## 3. Recommended Information Architecture

### Recommended: three time/intent zones, fixed order

1. **Needs your attention / 需要你留意** — only items with a real pending action *backed by a real model state*. Today that is exactly one type: ministry-team assignment confirmations (`TeamAssignmentMember.confirmed_at IS NULL` on upcoming non-cancelled assignments). Hidden entirely when empty (no empty state — absence of the section is the "all clear").
2. **Today / 今日** — today's reading hero, essentially as it exists now (check-in is itself the daily action, so the reading hero already *is* an action item; it does not need to move into zone 1).
3. **This week / 本周** — a short, read-only, chronological list of the user's personal week:
   - **Church Gatherings this week / 本周教会聚会**: upcoming visible `ServiceEvent` rows from the Church Gatherings module in the next 7 days, excluding draft and cancelled. No `event_type` guessing — whatever staff/responsible coworkers publish as a gathering and the user can already see is what appears. Where the user has a serving assignment attached to a gathering, the gathering row carries a compact serving note (see deduplication rule below);
   - my small group's next relevant v2 Bible study meeting (`BibleStudyMeeting` via the same logic as `get_v2_landing_context`). TODAY-HOME.1D adds read-only personal role chips/line only from `BibleStudyMeetingRole.user == request.user` on the already-visible primary meeting; Today must never guess role ownership from `display_name` or other name/source matching.
   Each row links to its owning module page (My Serving, meeting detail, event detail).

**Deduplication rule:** the same `TeamAssignmentMember` must not appear as two full rows on one Today page. A pending-confirmation assignment belongs first in **Needs your attention**; the related Church Gathering row in **This week** may still carry a compact note ("You are serving — pending confirmation / 你有服事 · 等待确认"), but never a second full assignment row. A confirmed assignment appears only as the serving note on its gathering row, not as a separate assignment row.

Keep "Where to go next" cards at the bottom (possibly trimmed), so the page still works for users with nothing scheduled.

### Why this IA

- **Pending-action items are rare but urgent; schedule items are common but calm.** Mixing them in one task list (the hypothesis) makes the common case noisy and the urgent case easy to miss. Separating "needs action" from "calendar" lets zone 1 be loud precisely because it is usually absent.
- **The reading hero stays primary.** Daily reading is the app's habit anchor and the only thing guaranteed to be relevant *every* day. Demoting it into a task list among weekly items would weaken the core habit loop.
- **"This week" matches how church life is actually structured** (Friday group, Sunday service, occasional extra gatherings) without hardcoding weekday labels into logic — it is just a 7-day personal window, so a Saturday group or mid-week gathering works identically.
- **It respects existing module ownership.** Today shows and links; My Serving confirms; meeting detail shows the worship set; `/events/` shows event detail. No workflow duplication, consistent with the pilot-era boundary docs.

### Alternatives compared

**A. User's hypothesis: flat personal task list** (today's reading, Sunday assignments, Friday roles, Friday meeting, special meetings, unconfirmed ministry assignments, unconfirmed Bible-study assignments, later invitations).

- Pros: one mental model ("my list"), everything in one place.
- Cons: (1) it mixes *to-confirm* with *already-scheduled*, so most days the "task list" is actually a calendar and the framing is wrong; (2) two of the eight item types do not exist in data today — Bible-study role confirmation has no model field, and invitations have no module — so a literal implementation either fakes states or ships a list with permanent gaps; (3) reading loses its hero position; (4) Sunday assignments and unconfirmed assignments are the *same rows* in two list entries (an assignment is one `TeamAssignmentMember` that is either confirmed or pending), which would double-show items.
- The recommended IA keeps every *real* item from the hypothesis but reorganizes them by intent (act / read / know) instead of by source module.

**B. Status quo plus (minimal):** keep today's layout, only swap the legacy Bible Study card for the v2 meeting and raise the pending count visibility.

- Pros: smallest change, zero risk.
- Cons: still answers only "what is today?", never "what is this week?"; Sunday serving stays invisible until it is the only item the single-card summary happens to pick; Church Gatherings stay invisible. It under-delivers on the actual user need that motivated the hypothesis.

**C. Recommended (three zones)** — chosen because it delivers the hypothesis's value using only data that exists, keeps the habit loop primary, and stays inside current module boundaries.

## 4. Data Availability Matrix

| Proposed item | Availability | Source models / selectors | Notes |
|---|---|---|---|
| Today's Bible reading + check-in | **Available now** | `PlanEnrollment`, `ActivePlan`, `ReadingPlanDay`, `CheckIn`; existing `home()` logic | Already on Today. |
| Pending ministry-assignment confirmations | **Available now** | `TeamAssignmentMember.confirmed_at IS NULL` via `ministry.views.my_serving_assignments(user, tab="upcoming")`; `today_serving_summary` already computes the count | Confirm action exists (`confirm_team_assignment`, supports safe `next` redirect). |
| This week's serving assignments (e.g., Sunday) | **Available now** | Same selector, filtered to `service_event.start_datetime` within next 7 days | Per-member rows are user-scoped by construction. Rendered as compact serving notes on the matching Church Gathering row (Section 3 deduplication rule), not as separate full rows. |
| This week's small-group Bible study meeting | **Available now** | `BibleStudyMeeting` filtered like `studies.views.get_v2_landing_context` (published meeting/lesson/series, membership-visible legacy `SmallGroup` candidates, final `can_be_seen_by`) | Since CS-CORE.2C-B, ordinary visibility uses the user's active primary `ChurchStructureMembership`; `Profile.small_group` alone no longer grants v2 meeting visibility. Legacy `BibleStudySession` block should be retired or kept only as fallback — product decision, Section 8. |
| My Friday serving role(s) (worship lead, study lead, pianist, support, host) | **Available for linked-user roles** | `BibleStudyMeetingRole` (`role`, `user` FK nullable, `display_name`) on the already-visible primary meeting | TODAY-HOME.1D shows read-only role chips/line only for `role.user == request.user`. Display-name-only roles remain visible on meeting detail but are not personalized on Today. Today does not infer identity from display names, username/full-name matching, old discussion-leader names, worship-song lead names, `TeamAssignment`, `TeamMembership`, or `ServiceEvent`. |
| Unconfirmed ministry-team assignments | **Available now** | Same as pending confirmations above | Same rows; in the recommended IA this *is* the "Needs your attention" section, not a separate list entry. |
| Unconfirmed small-group Bible-study serving assignments | **Not planned** | None — `BibleStudyMeetingRole` has no confirmation field | Do not fake, and do not assume a confirmation workflow is coming: the user is leaning toward *not* adding Bible-study role confirmation unless a real need appears. Revisit only if real usage shows the need. |
| Church Gatherings this week / 本周教会聚会 | **Available now** | `ServiceEvent` via `events.views.get_visible_service_events` / `can_be_seen_by` (SE-AS.4 + legacy fallback), filtered to next 7 days, excluding draft/cancelled | All visible upcoming gatherings created in the Church Gatherings module — no hardcoded `event_type` subset. Remaining product question (Section 8) is list size: show all this week's gatherings or cap with a link to `/events/`. |
| Community-event invitations in my audience scope | **Future module needed** | Community Activities is plan-only (`COMMUNITY_ACTIVITIES_V1_PLAN.md`); no invitation model exists | Explicitly out of scope. The IA reserves no visible placeholder; zone 3 can absorb invitations later as another row type. |

## 5. Visibility and Permission Contract

- **Ordinary users.**
  - Reading: own enrollments/check-ins only (already enforced by user-filtered queries).
  - Serving items: only rows where `TeamAssignmentMember.membership.user == request.user` with active membership/team, excluding cancelled assignments and draft/cancelled events — exactly `my_serving_assignments`. No team-wide or coverage data on Today.
  - Bible Study meeting: only the user's membership-visible small-group meeting, gated by `BibleStudyMeeting.can_be_seen_by` (published meeting + published lesson + active published series + active primary `ChurchStructureMembership` matching the meeting legacy small group's mapped small-group unit or descendant). `Profile.small_group` alone no longer grants v2 meeting visibility.
  - Bible Study roles: only `BibleStudyMeetingRole.user == request.user` on the already-visible primary v2 meeting. Never show other members' role rows on Today, and never infer ownership from `display_name`, username/full-name matching, old discussion-leader names, worship-song lead names, `TeamAssignment`, `TeamMembership`, or `ServiceEvent` (the meeting detail page already handles the full roster in its own context).
  - Church Gatherings (`ServiceEvent`): only events passing `can_be_seen_by` — SE-AS.4 audience rows when present, legacy scope fallback otherwise. Today introduces **no new visibility rule**, only a 7-day time filter and draft/cancelled exclusion over already-visible events.
- **Staff users with personal assignments.** Zone 1 and the serving notes in zone 3 are personal-FK-scoped, so staff see only their own items there — correct and automatic. Caution: `ServiceEvent.can_be_seen_by` returns `True` for managers, so a staff user's "Church Gatherings this week" list shows all published/completed gatherings church-wide. That matches `/events/` today and is acceptable for a v1 read-only strip, but Today must exclude draft and cancelled events for everyone — including staff — so Today never becomes a staff manage queue. Today must not add staff-only blocks; staff workflows stay in `/staff/` and manage pages.
- **What must not leak:**
  - other users' assignments, confirmation states, or notes;
  - draft/cancelled events, meetings, lessons, or series to ordinary users;
  - other small groups' meetings or rosters;
  - audience-scope internals (unit names/codes are staff vocabulary; Today shows event titles, not scope explanations);
  - any data derived from `ChurchStructureMembership`.

## 6. Recommended First Implementation Slice (TODAY-HOME.1B)

Status: complete. TODAY-HOME.1B shipped the read-only three-zone IA using existing selectors: pending ministry confirmations in Needs your attention, the existing reading hero in Today, and visible Church Gatherings plus the v2 small-group Bible Study meeting in This Week. It removed the legacy `BibleStudySession` block from Today and did not add role chips, inline confirm, Community Activities/invitations, schema changes, or runtime visibility changes.

**Read-only Today restructure using existing selectors only, establishing the full three-zone IA.** One view (`reading.views.home`) and one template (`templates/reading/home.html`), plus targeted tests:

1. Replace the single `today_serving_summary` card with the **"Needs your attention / 需要你留意"** section: list pending-confirmation items for the next 7–30 days (small cap, e.g., 5) with event title/date/team and a single "Confirm in My Serving" link per item (or one link when more). Reuses `my_serving_assignments`; no new model, no new endpoint, no inline POST. Renders nothing when empty.
2. Keep the existing **"Today / 今日"** reading hero unchanged.
3. Add the **"This week / 本周"** section: (a) upcoming visible Church Gatherings in the next 7 days via `get_visible_service_events` semantics, excluding draft/cancelled, with the user's serving status attached as a compact note on the gathering row where the user has an assignment (per the Section 3 deduplication rule — no duplicate full assignment rows); (b) my group's next relevant v2 `BibleStudyMeeting` (reusing/extracting the `get_v2_landing_context` filtering); each row linking to event detail / My Serving / meeting detail.
4. Replace the legacy `BibleStudySession` block with the v2 meeting row (or keep legacy sessions temporarily below — decide via Section 8 Q4 before implementing).
5. Bilingual copy per Section 7; empty states for "This week"; "Needs your attention" renders nothing when empty.

Explicitly **not** in 1B:

- Bible Study role confirmation/status workflow (not planned at all unless a real need appears);
- any inline confirm action on Today;
- Community Activities / invitations;
- new models or fields;
- runtime visibility changes.

**Why this slice over alternatives:**

- *vs. splitting gatherings into a later slice:* the week strip is now well-defined (all visible upcoming gatherings, no `event_type` guessing), reuses the existing visibility helper unchanged, and is what makes "This week" answer its question — deferring it would ship a week section that misses the most common item.
- *vs. broader role surfacing:* TODAY-HOME.1D keeps chips linked-user-only; display-name-only roles remain on meeting detail and are never treated as "my role" on Today.
- *vs. an inline confirm button on Today:* the confirm endpoint already supports a safe `next` redirect, so inline confirm is cheap *later*, but it crosses the "My Serving owns the action" boundary and so should be its own consciously-approved step, not smuggled into a restructure.
- *vs. a big-bang IA change:* 1B establishes the three-zone skeleton with all currently-reliable data; later milestones only add row types into an existing section, keeping every later diff small and individually reviewable.

## 7. UX Copy (proposal)

Section titles:

| EN | ZH |
|---|---|
| Needs your attention | 需要你留意 |
| Today's Reading | 今日读经 |
| This Week | 本周 |
| Where to go next | 接下来去哪里 |

Row labels / chips:

| EN | ZH |
|---|---|
| Church Gatherings this week | 本周教会聚会 |
| You are serving — pending confirmation | 你有服事 · 等待确认 |
| You are serving — confirmed | 你有服事 · 已确认 |
| Small group Bible study | 小组查经 |
| My role: Discussion Leader / Worship Lead / Pianist / Support / Host *(linked-user roles only)* | 我的角色：带查经 / 带敬拜 / 司琴 / 协助 / 主持（仅限已关联用户的角色） |
| Confirm in My Serving | 去「我的服事」确认 |
| View details | 查看详情 |

Empty states:

| Context | EN | ZH |
|---|---|---|
| Needs your attention | *(section hidden when empty)* | *(同左，无内容时整段隐藏)* |
| This week, nothing scheduled | Nothing scheduled for you this week. Enjoy the rhythm of daily reading. | 本周暂时没有你的安排。继续保持每天读经的节奏。 |
| This week, no small group | You're not in a small group yet, so group Bible study won't appear here. | 你还没有加入小组，所以这里不会显示小组查经。 |
| No reading plan (existing) | Join a reading plan to start reading day by day. | 加入一个读经计划，开始每天的读经。 |

Wording rules: pastoral user-intent language only; no internal terms (no "assignment status", "audience scope", "published", model names) in normal-user UI; EN/ZH paired and natural per `UI_UX_GUARDRAILS.md`.

## 8. Risks, Unknowns, and Questions for the User

1. **Friday Bible-study roles data quality.** TODAY-HOME.1D now surfaces only user-linked rows. `BibleStudyMeetingRole.user` remains nullable and staff may enter free-text names, so display-name-only roles stay on meeting detail and never appear as "my role" on Today.
2. **Bible-study role confirmation.** Decision direction recorded: **not planned** — no confirmation workflow for Bible-study roles unless real usage shows a need. Today must not fake or anticipate it. Revisit only on concrete demand from group leaders.
3. **Church Gatherings list size.** Q: should Today show *all* visible upcoming Church Gatherings this week, or cap the list (e.g., 3–5 rows) and link to `/events/` for the rest? A busy week (or a staff user, who sees church-wide gatherings) could otherwise make "This week" tall.
4. **Legacy `BibleStudySession` block on Today.** Q: retire it from Today once the v2 meeting row exists, or keep both during transition? (Recommend: replace; `/studies/` already leads with v2. Keeping both risks showing the same Friday twice.)
5. **Inline confirm on Today.** Q: keep confirmation strictly in My Serving (recommended for 1B), or later allow a one-tap confirm on Today posting to the existing endpoint with `next`? The latter changes the "Today is read-only summary" boundary and should be a separate yes/no (milestone 1E).
6. **Staff view of "This week".** Q: is it acceptable that staff users see all church-wide published gatherings in their Today strip (mirroring `/events/`), or should Today apply ordinary-audience semantics for staff too? The latter would require a new helper and is *not* recommended now (it edges toward a visibility behavior change). Draft/cancelled gatherings stay excluded for everyone regardless.
7. **Multi-plan reading users.** Q: with multiple active plans, should Today show one hero plus compact rows for the rest? Cosmetic, but affects how dominant zone 2 is.
8. **Invitations (future).** When Community Activities ships, invitations would join zone 1 (pending response) and zone 3 (accepted ones). No placeholder now. Q: confirm that nothing invitation-shaped should appear until that module exists (recommended).

## 9. Proposed Milestone Split

- **TODAY-HOME.1A** — this planning doc (refined by TODAY-HOME.1A.1). Done when reviewed.
- **TODAY-HOME.1B — Read-only Today IA restructure.** Completed. Full three-zone IA: "Needs your attention" (pending ministry confirmations); "Today" reading hero unchanged; "This week" with visible Church Gatherings (draft/cancelled excluded, serving status attached as compact notes per the deduplication rule) + next relevant v2 Bible study meeting; legacy `BibleStudySession` block removed from Today; bilingual copy; targeted `reading` tests. No role chips, inline confirm, Community Activities, new models, endpoints, or visibility changes.
- **BS-ROLE.1B / former TODAY-HOME.1C — Bible Study role assignment / user-linking polish.** Completed in the Bible Study module. `BibleStudyMeetingRole` management now requires a linked user or display name, encourages linked users for Today "my role" surfacing, and preserves display-name-only roles as meeting-detail fallback. No Today change, confirmation workflow, schema/migration, or runtime visibility change.
- **TODAY-HOME.1D — Bible-study role chips on Today.** Completed. Adds read-only Bible Study role chips/line under the small-group Bible Study card only for `BibleStudyMeetingRole.user == request.user` on the already-visible primary meeting. Display-name-only roles remain meeting-detail fallback only. No identity inference from names, old discussion-leader fields, worship-song leads, `TeamAssignment`, `TeamMembership`, or `ServiceEvent`; no confirmation/status workflow, schema/migration, URL, or runtime visibility change from Today itself.
- **TODAY-HOME.1E (optional) — One-tap confirm from Today.** Only if Q5 is separately approved; uses the existing confirm endpoint + `next`; no model change.
- **TODAY-HOME.3x (deferred) — Invitations on Today.** Blocked on Community Activities V1; not planned here.

Bible-study role *confirmation* has no milestone: it is not planned unless real usage demonstrates the need (Section 8 Q2).

Each remaining Today slice is independently approvable and independently revertible; none changes runtime visibility or schemas unless separately approved.
