# Pilot Release Candidate Readiness

Status: historical pilot-era checklist. It preserves the release assumptions
and QA scope from that pilot and is not canonical current-state architecture.
Legacy structure/model statements below are historical, not live runtime
guidance. Use `docs/README.md`,
`docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`, and
`docs/MODULE_BOUNDARIES.md` for current truth.

## 1. Release Candidate Scope

This pilot release candidate covers the current lightweight Church Life / spiritual workflow system. It supports daily spiritual practice, small-group Bible Study flow, prayer, serving visibility, and basic staff/ministry operations.

This is not a full church ERP. Finance, HR, broad CRM, complex scheduling, attendance, reminders, and historical personnel operations are outside this pilot.

Pilot includes:

- Today
- Reading
- Bible Study V2
- Prayer
- My Serving
- Ministry Operations
- Staff menu and staff management pages
- Basic Church Structure bridge through `MinistryContext` labels

## 2. Completed Foundations

- IA/nav reset: normal navigation is focused on Today, Reading, Bible Study, Prayer, My Serving, and Profile, with staff functions grouped under the Staff menu.
- Today Dashboard Lite: Today shows current reading, Bible Study, prayer, and serving cues without becoming a broad dashboard.
- Reading cleanup: Reading plans, active plans, guide posts, structured passage readers, check-in, reflection, reporting, and staff reading-plan admin are in the pilot surface.
- Prayer reporting/moderation basics: Prayer list/detail/create, prayer status, comments, reporting, and staff review flows are present.
- Bible Study V2 staff-to-normal-user foundation: Staff manages Bible Study Schedules, Weekly Bible Study Guides, generated Small Group Meetings, preparation, roles, and worship set; normal `/studies/` promotes the user's current small-group meeting.
- Ministry Assignment UX preflight: Ministry Teams, Team Assignments, confirmation, My Serving, and Today serving summary support the manual pilot flow.
- MinistryContext bridge: `MinistryContext -> District -> SmallGroup -> Profile.small_group` supports current Bible Study Schedule scope.
- ServiceEvent MinistryContext label-only foundation: ServiceEvent can carry an optional Ministry Context label without changing visibility, assignment filtering, or My Serving behavior.
- Chinese UI residual cleanup: visible pilot navigation and key staff/normal surfaces have been reviewed for current Chinese wording.
- Staff table/list polish: key staff lists are grouped by content management, ministry operations, and users/review.

## 3. Manual QA Checklist

### Normal User

- [ ] Login works.
- [ ] Logout works.
- [ ] Today page loads and shows the correct current cards.
- [ ] Active reading item opens the correct reading flow.
- [ ] Reading plan page shows joined and available plans correctly.
- [ ] Bible Study `/studies/` normal landing shows the user's current small-group meeting or a safe empty state.
- [ ] Prayer list loads.
- [ ] Prayer detail loads.
- [ ] Prayer create works where allowed.
- [ ] Prayer report works where applicable.
- [ ] My Serving shows pending and upcoming assignments relevant to the user.
- [ ] Profile page loads and saves allowed account fields.
- [ ] Chinese/English language toggle works.
- [ ] Mobile nav is usable.

### Staff User

- [ ] Staff menu opens on desktop.
- [ ] Staff menu opens on mobile.
- [ ] Reading Plan Admin loads.
- [ ] User Admin loads.
- [ ] Reflection Reports loads.
- [ ] Prayer Reports loads, if included in the pilot staff review path.
- [ ] Bible Study Schedules list/create/edit/detail loads.
- [ ] Weekly Bible Study Guides list/create/edit/detail loads.
- [ ] Small Group Meetings list/detail and related management pages load.
- [ ] Service Events list/create/edit/detail loads.
- [ ] Ministry Teams list/create/edit/detail loads.
- [ ] Team Assignments list/create/edit/detail loads.
- [ ] MinistryContext labels are visible where expected on ServiceEvent and TeamAssignment surfaces.
- [ ] MinistryContext labels do not imply filtering or audience control.

## 4. Permission And Visibility Checklist

- [ ] Normal users cannot access staff pages.
- [ ] Staff-only pages require staff status or the intended capability.
- [ ] Bible Study normal users only see their own small-group meeting.
- [ ] Direct access to another small group's Bible Study meeting is denied or redirected safely.
- [ ] Users without a small group see a safe empty state.
- [ ] My Serving only shows assignments relevant to the logged-in user.
- [ ] Hidden or reported reflections behave correctly for author, normal user, and staff views.
- [ ] Prayer reporting/moderation does not expose hidden content incorrectly.
- [ ] Legacy Bible Study V1 is not visible in normal or staff promoted UI.
- [ ] Draft, cancelled, inactive, or otherwise hidden Bible Study items are not promoted to normal users.

## 5. Bilingual QA Checklist

Check each surface in Chinese and English:

- [ ] Main nav
- [ ] Today
- [ ] Reading
- [ ] My Reading Plans
- [ ] Reading Plan Admin
- [ ] Bible Study normal landing
- [ ] Bible Study Schedules
- [ ] Weekly Bible Study Guides
- [ ] Small Group Meetings
- [ ] Prayer
- [ ] Reflection Reports
- [ ] Prayer Reports, if included in pilot staff QA
- [ ] User Admin
- [ ] My Serving
- [ ] Ministry Operations
- [ ] ServiceEvent form
- [ ] ServiceEvent list/detail
- [ ] Ministry Team detail
- [ ] TeamAssignment list/detail

Expected:

- [ ] No obvious English residuals in Chinese mode.
- [ ] No Chinese hard-coding in English mode.
- [ ] ServiceEvent label wording uses Ministry Context Label / Ministry Label concepts, not audience-scope wording.
- [ ] Bible Study V2 wording uses Schedule, Weekly Guide, and Small Group Meeting concepts, not legacy V1 promotion.

## 6. Mobile QA Checklist

- [ ] Top nav remains usable.
- [ ] Staff dropdown remains usable.
- [ ] Today layout is readable.
- [ ] Reading pages are readable and actions are reachable.
- [ ] Bible Study landing is readable.
- [ ] Bible Study schedule list is usable.
- [ ] ServiceEvent form is usable.
- [ ] TeamAssignment list/detail are usable.
- [ ] My Serving is readable and confirmation actions are reachable.
- [ ] Prayer list/detail/reporting pages are usable.
- [ ] Long MinistryContext, schedule, guide, event, and team names wrap acceptably.
- [ ] Staff tables do not break the page; horizontal scrolling is acceptable if needed.

## 7. Deferred / Non-Goals

The following are explicitly not part of this release candidate:

- ChurchStructureUnit flexible hierarchy
- Hierarchical multi-select audience scope
- ServiceEvent filtering by MinistryContext
- Community Activities
- Checklist V1
- Automatic scheduling
- Reminders
- Availability matrix
- Swap requests
- Attendance
- Role-aware Bible Study permissions
- Full church ERP
- Historical import
- Phone, private, or sensitive data import

## 8. Known Acceptable Limitations

- ServiceEvent MinistryContext is label-only.
- Current ServiceEvent audience scope supports only whole church, one district, or one small group.
- Selecting district does not expand child small groups.
- Flexible hierarchy is future CS-H work.
- MinistryContext blank can represent whole-church, combined, legacy, or uncategorized events.
- Some user-created content may remain in the language originally entered.
- Bible Study V2 uses the current `MinistryContext -> District -> SmallGroup` bridge rather than a flexible structure tree.
- Manual TeamAssignment is the pilot serving workflow; automatic scheduling is intentionally absent.

## 9. Pilot Blocker Criteria

### No-Go Blockers

- Normal users can access staff pages.
- Cross-small-group Bible Study visibility leaks.
- My Serving hides valid assignments or leaks unrelated assignments.
- Staff cannot create or edit core Bible Study schedule, guide, or meeting records.
- TeamAssignment cannot be created or confirmed.
- Major Chinese-mode pages contain obvious English residuals.
- Mobile nav or staff menu is unusable.
- Any common pilot route crashes.
- ServiceEvent MinistryContext label changes visibility, assignment filtering, or My Serving behavior.

### Go Criteria

- Core normal-user flows pass.
- Core staff flows pass.
- No permission leakage.
- No major bilingual blockers.
- No major mobile blockers.
- Deferred items are documented and do not block the pilot.
- Known limitations are understood by testers and pilot coordinators.

## 10. Suggested Manual Test Accounts And Data

### Accounts

- Normal user in Rainbow 1:
- Normal user in Rainbow 2:
- Normal user without small group:
- Staff / Bible Study manager:
- Ministry manager:
- Superuser / admin:

### Data

- Active reading plan:
- Published Bible Study schedule:
- Published Weekly Bible Study guide:
- Published Small Group Bible Study meeting:
- Pending My Serving assignment:
- ServiceEvent with CM label:
- ServiceEvent with EM label:
- ServiceEvent with blank label:
- MinistryTeam:
- TeamAssignment:
- Reported reflection:

## 11. Final Sign-Off

- Browser:
- Date:
- Commit:
- Tester:
- Go / No-Go:
- Issues found:
- Required fixes before pilot:

## 12. Notes For Pilot Review

- Use this checklist together with `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md` and `docs/SERVICE_EVENT_MINISTRY_CONTEXT_QA_CHECKLIST.md` for deeper module-specific QA.
- Do not treat deferred items as pilot blockers unless their absence breaks a documented pilot flow.
- Do not commit local database changes such as `db.sqlite3` unless a separate task explicitly asks for seeded database state.
