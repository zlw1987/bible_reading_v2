# Portal UX and Help Center Plan

Status: canonical current/future product plan for `PORTAL-UX-HELP-CENTER.1A`,
with `PORTAL-UX-HELP-CENTER.1A-FU1`, `PORTAL-UX-HELP-CENTER.1A-FU2`,
`PORTAL-HELP-MANUAL-QA.1A-FU1` hardening applied, and
`PORTAL-HELP-MANUAL-QA.1A` product-owner manual QA closed.

This plan records the current portal shell, Staff navigation, Help Center foundation, completed implementation, and deferred slices. It is intended to let a future Codex, Claude, or ChatGPT session continue without relying on conversation memory.

## 1. Current Navigation Architecture

The authenticated shell is `templates/base.html`.

Ordinary member primary navigation is registry-driven through `core.module_registry.get_enabled_nav_items()` and rendered by `templates/partials/_primary_navigation.html`. The first top-level item is Today. Enabled module links are grouped into the existing top navigation groups such as Grow and Community. This is presentation-only; module enablement still comes from `CMS_ENABLED_MODULES`.

The account menu is separate from primary module navigation. It contains Profile, Help Center, My Units when `accounts.unit_management.should_show_my_units_nav(user)` is true, language switching, and logout.

The Staff dropdown is separate from ordinary member primary navigation and remains in the top navigation on desktop and inside the mobile hamburger drawer on mobile. There is no permanent desktop sidebar.

## 2. Current Staff Navigation Architecture

The Staff dropdown is visible only when `user.is_staff` is true. Superusers normally satisfy `is_staff` in Django and therefore see it through the same template condition.

`PORTAL-UX-HELP-CENTER.1A` moved the Staff dropdown data into `accounts/staff_navigation.py` and renders it through `templates/partials/_staff_navigation.html`. This keeps desktop and mobile using the same grouped link inventory.

The whole Staff dropdown remains a navigation surface only. It does not grant access. Underlying views keep their existing route-level decorators and capability checks.

## 3. Staff Dropdown Inventory

| Group | English label | Chinese label | Route name / URL | Owning module | Menu gate | Module gate | Staff Overview? | Primary task |
|---|---|---|---|---|---|---|---|---|
| Start & Help | Staff Overview | 同工总览 | `staff_overview` / `/staff/` | Core/accounts | `user.is_staff` menu plus `staff_member_required` route | none | route itself | Start staff work and view read-only status/action summary. |
| Start & Help | Staff User Guide | 同工使用指南 | `staff_setup_guide` / `/staff/setup-guide/` | Core/accounts/docs | `user.is_staff` menu plus `staff_member_required` route | none | no | Read internal staff guidance. |
| People & Structure | User Admin | 用户管理 | `staff_user_list` / `/staff/users/` | Core/accounts | `user.is_staff` menu plus `staff_member_required` route | none | yes, Users and Admin card | Find users and staff password reset entry. |
| People & Structure | Membership Requests | 成员归属申请 | `staff_membership_request_list` / `/staff/membership-requests/` | Core/accounts | `user.is_staff` menu; route uses `user_passes_test(can_manage_church_memberships)` | none | yes, Membership Requests card | Review requested Church Structure memberships. |
| People & Structure | Church Structure Setup & Review | 教会结构设置与检查 | `staff_structure_map` / `/staff/structure/` | Core/accounts | `user.is_staff` menu plus `staff_member_required` route | none | yes, Users and Admin card | Inspect and maintain Church Structure setup. |
| People & Structure | Ministry Structure | 事工结构 | `ministry_structure_map` / `/structure/` | `ministry` app | `user.is_staff` menu; route currently staff/superuser-gated in view | `ministry` | yes, Ministry Operations card when ministry enabled | Review ministry structure map. |
| Content & Communication | Reading Plan Admin | 读经计划管理 | `staff_reading_plan_list` | `reading` | `user.is_staff` menu; route uses reading guide capability/staff patterns | `reading` | no | Manage reading plans. |
| Content & Communication | Bible Study Schedules | 查经安排 | `bible_study_schedule_manage_list` | `studies` | `user.is_staff` menu; route uses Bible Study manager capability/staff patterns | `studies` | yes, Bible Study card | Manage Bible Study schedules. |
| Content & Communication | Weekly Bible Study Guides | 每周查经指引 | `bible_study_lesson_manage_list` | `studies` | `user.is_staff` menu; route uses Bible Study manager capability/staff patterns | `studies` | yes, Bible Study card | Manage weekly Bible Study guide content. |
| Content & Communication | Small Group Meetings | 小组查经聚会 | `bible_study_meeting_manage_list` | `studies` | `user.is_staff` menu; route uses Bible Study manager capability/staff patterns | `studies` | yes, Bible Study card | Manage V2 Bible Study meetings. |
| Content & Communication | Announcement Admin | 公告管理 | `staff_announcement_list` | `announcements` | `user.is_staff` menu plus `staff_member_required` route | `announcements` | no | Manage official announcements. |
| Gatherings & Serving | Manage Church Gatherings | 管理教会聚会 | `service_event_list` / `/events/` | `events` | `user.is_staff` menu; route also serves member list and exposes management actions through `can_manage_service_events` | `events` | yes, Ministry Operations card when events enabled | Manage official Church Gatherings. |
| Gatherings & Serving | Ministry Teams | 事工团队 | `ministry_team_list` | `ministry` | `user.is_staff` menu; route uses ministry view/management checks | `ministry` | yes, Ministry Operations card when ministry enabled | Maintain ministry teams and team context. |
| Gatherings & Serving | Team Assignments | 服事排班 | `team_assignment_list` | `ministry` | `user.is_staff` menu; route uses team-assignment management/view checks | `ministry` | yes, Ministry Operations card when ministry enabled | Schedule explicit serving assignments. |
| Review & Moderation | Moderation Queue | 审核队列 | `staff_moderation_queue` / `/staff/moderation/` | Core/accounts/comments support | `user.is_staff` menu plus `staff_member_required` route | none | yes, Moderation card | Review content moderation queues. |
| Review & Moderation | Activity Review | 活动审核 | `community_activity_review_list` / `/activities/review/` | `community_events` | `user.is_staff` menu plus `staff_member_required` route | `community_events` | no | Review member-submitted Community Activities. |
| Review & Moderation | Reflection Reports | 默想举报 | `staff_reflection_reports` | comments support / reading surface | `user.is_staff` menu plus `staff_member_required` route | none | yes, Moderation card | Review reflection reports. |
| Review & Moderation | Prayer Reports | 代祷举报 | `staff_prayer_reports` | `prayers` | `user.is_staff` menu plus `staff_member_required` route | `prayers` | yes, Moderation card when prayers enabled | Review prayer reports. |
| System Administration | Django Admin | Django 后台 | `admin:index` / `/admin/` | Django admin | `user.is_staff` menu plus Django admin permissions | none | yes, Users and Admin card | Use Django Admin for existing admin workflows. |

## 4. Staff Overview Relationship

Staff dropdown is navigation. Staff Overview is a read-only status/action surface at `/staff/`.

Staff Overview remains separate and was not converted into a dashboard-style dropdown. `PORTAL-UX-HELP-CENTER.1A` did not add new Staff Overview metrics.

## 5. Existing Staff Setup Guide Implementation

The canonical guide index is `docs/STAFF_SETUP_GUIDE.md`, with language-specific files `docs/STAFF_SETUP_GUIDE.en.md` and `docs/STAFF_SETUP_GUIDE.zh.md`.

The route `/staff/setup-guide/` uses `accounts.views.staff_setup_guide`, is `staff_member_required`, selects a source by current language, parses a small Markdown subset through `_parse_staff_setup_guide_blocks`, and renders escaped blocks in `templates/accounts/staff/setup_guide.html`.

This route remains intact for bookmarks and tests.

## 6. Recommended Information Architecture

The product shell should remain top-navigation based.

Staff navigation should group tasks by staff workflow:

- Start & Help;
- People & Structure;
- Content & Communication;
- Gatherings & Serving;
- Review & Moderation;
- System Administration.

Ordinary member navigation should remain low-noise. Help Center is placed in the account menu because it is a utility/reference surface for every authenticated user, not a primary daily workflow.

## 7. Help Center Architecture

`PORTAL-UX-HELP-CENTER.1A` adds an authenticated Help Center at `/help/` and member-safe guide detail routes at `/help/<slug>/`.

The first implemented guides are docs-backed Markdown files:

- `HELP_CENTER_MEMBER_GUIDE.en.md` / `.zh.md`;
- `HELP_CENTER_SERVING_MINISTRY_GUIDE.en.md` / `.zh.md`;
- `HELP_CENTER_CHURCH_STRUCTURE_GROUP_LEADER_GUIDE.en.md` / `.zh.md`.

The existing Staff User Guide remains at `/staff/setup-guide/` and is integrated into Help Center only for staff/superusers.

## 8. Guide Taxonomy

Guide categories:

- Member Guide: safe for all authenticated users.
- Serving / Ministry Guide: safe explanatory content about explicit serving.
- Church Structure / Group Leader Guide: safe explanatory content about belonging and delegated My Units operations.
- Staff User Guide: staff/internal-only operational guidance.

## 9. Role / Recommendation Rules

Implemented recommendations:

- Member Guide: every authenticated user.
- Serving / Ministry Guide: users with explicit serving data from active linked `TeamAssignmentMember` records or linked-user `BibleStudyMeetingRole` records.
- Church Structure / Group Leader Guide: users for whom `should_show_my_units_nav(user)` is true.
- Staff User Guide: staff/superusers only.

Deferred: broader role recommendation rules for other leadership categories. Do not infer them from `ChurchStructureMembership`, audience rows, event visibility, or activity signup.

## 10. Permission Boundaries

- Navigation visibility is not permission.
- Help Center recommendation is not permission.
- Church Structure membership is not leadership.
- Church Structure membership is not serving.
- Audience visibility is not serving.
- Event visibility is not serving.
- Community Activity signup is attendance intent.
- My Serving requires explicit serving data.
- Calendar is read-only.
- Help Center does not create notifications.
- Help Center feedback is deferred.

## 11. Bilingual Content Rules

Each implemented guide has separate English and Chinese Markdown files. The renderer selects one language and does not mix both languages into a single wall of text.

Visible guide terminology should match existing product labels such as Today, My Serving, Calendar, Church Gatherings, Activities, Announcements, Profile, Staff, and My Units. Chinese guide copy should use the current localized labels such as 今日、我的服事、日历、教会聚会、活动、公告、个人资料、同工管理、我负责的单位.

Ordinary-user guide copy should avoid implementation model names. Internal names such as `TeamAssignmentMember`, `BibleStudyMeetingRole`, and `ChurchStructureMembership` are acceptable in this plan's implementation/recommendation sections because those sections document code behavior for maintainers, not Help Center prose for members.

## 12. Desktop / Mobile Behavior

Desktop keeps the top navigation and dropdown model. No permanent sidebar is introduced.

Mobile keeps the hamburger drawer and inline dropdown expansion already owned by `templates/base.html` and `static/css/app.css`. In the mobile drawer, top-level Grow, Community, Staff, and Account dropdowns use one-open-at-a-time accordion behavior so opening one closes the other open top-level dropdowns. The Staff dropdown uses the same grouped partial on desktop and mobile.

Groups render only when they have visible items. Section headings are non-clickable text.

## 13. Completed In 1A

- Created this canonical plan.
- Added plan entry to `docs/README.md`.
- Moved Staff dropdown inventory into `accounts/staff_navigation.py`.
- Rendered Staff dropdown groups through `templates/partials/_staff_navigation.html`.
- Added a low-noise account-menu Help Center link.
- Added authenticated `/help/`.
- Added authenticated `/help/<slug>/`.
- Added Member, Serving / Ministry, and Church Structure / Group Leader guides in English and Chinese.
- Integrated the existing staff guide into Help Center for staff/superusers only.
- Added focused tests for Staff navigation grouping and Help Center access/recommendation behavior.

## 13a. Completed In 1A-FU1

- Added the missing `ministry` module surface gate to the Staff dropdown Ministry Structure link.
- Expanded the three Help Center guide pairs into practical, task-oriented English and Chinese content.
- Corrected Chinese Help Center labels so the Chinese view does not render English-only start labels or mixed product labels in introductory copy.
- Kept implementation model names out of ordinary-user guide prose while retaining them in this plan where they document recommendation logic and developer-maintained module gates.

## 13b. Completed In 1A-FU2

- Reconciled `MODULE_BOUNDARIES.md` so the historical `MODULAR-CORE.6A` wording remains chronological while current-state guidance records that Staff dropdown Ministry Structure now follows the `ministry` module gate.
- Expanded Member Guide Activities guidance to cover the current V1 signup, cancellation, capacity, re-signup, start-time freeze, no-waitlist, and attendance-intent boundaries.
- Clarified Church Structure / Group Leader guide membership-request wording: delegated leaders use pending requests on managed small-group pages under My Units, while staff may separately use the global Staff membership-request queue.

## 13c. Completed In PORTAL-HELP-MANUAL-QA.1A-FU1

- Product-owner manual QA for `PORTAL-HELP-MANUAL-QA.1A` otherwise passed, with one `LOW` mobile navigation issue found: multiple top-level dropdowns could remain open inside the hamburger drawer.
- Implemented one-open-at-a-time top-level dropdown behavior for the mobile drawer while preserving desktop dropdown behavior and existing drawer open/close semantics.

## 13d. Completed In PORTAL-HELP-MANUAL-QA.1A

- Product-owner deployed manual QA passed after the mobile accordion follow-up.
- Confirmed ordinary member desktop Portal and Help Center behavior.
- Confirmed explicit-serving user recommendations.
- Confirmed delegated My Units leader recommendations.
- Confirmed Staff desktop grouped navigation and Help Center access.
- Confirmed ordinary member mobile and Staff mobile navigation.
- Confirmed final mobile one-open-at-a-time top-level dropdown behavior.
- This records the bounded Portal / Help Center QA pass only; it is not a broad production-readiness claim.

## 14. Deferred Slices

### Help Center feedback

Future possible work: report issue, suggest improvement, own feedback status, and staff review. Keep independent from Notifications V0 unless explicitly approved later.

### Recommendation refinement

Future possible work: add centralized explicit role/capability helpers if product owners want more precise guide recommendations.

### Portal-shell refinement

Future possible work: refine account utility navigation, staff IA, and responsive behavior based on real user feedback. No sidebar redesign is approved.

## 15. Manual QA Checklist

- Sign in as an ordinary member and confirm the account menu shows Help Center but not Staff.
- Open `/help/` as an ordinary member and confirm Member Guide is recommended.
- Confirm ordinary membership alone does not recommend Serving / Ministry.
- Open Member Guide in English and Chinese.
- Sign in as a user with explicit serving and confirm Serving / Ministry Guide is recommended.
- Sign in as a My Units-eligible leader and confirm Church Structure / Group Leader Guide is recommended.
- Sign in as staff and confirm Staff dropdown groups render, Staff User Guide remains available, and Staff Guide is recommended in Help Center.
- Disable modules in a test/dev setting and confirm module-gated Staff links disappear without empty headings.
- Confirm mobile hamburger drawer shows the same Staff grouped links for staff.
- Confirm mobile hamburger drawer top-level dropdowns use one-open-at-a-time behavior.
- Confirm `/staff/setup-guide/` still uses staff-only auth behavior.

## 16. Explicit Non-Goals

- No permanent desktop sidebar.
- No wholesale visual redesign.
- No new app, model, migration, fixture, feedback model, ticket model, notification, email workflow, or deployment change.
- No schema work.
- No Today behavior change.
- No My Serving behavior change.
- No Calendar behavior change.
- No Staff Overview metrics added.
- No serving inference from membership, audience, event visibility, staff status, or Help Center recommendation.
- No leadership inference from membership.
- No route permission widening.
