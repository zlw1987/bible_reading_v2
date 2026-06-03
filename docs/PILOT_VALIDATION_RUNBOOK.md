# Pilot Validation Runbook

## 1. Release Candidate Identity

- Tag: `v0.9-pilot-rc1`
- Commit: `9cb0c84cfcf949058fe49fc51b963f56b7aef552`
- Purpose: Church Life Pilot Release Candidate 1

This runbook is for validating the tagged pilot release candidate in real church workflow conditions. It is a validation plan, not a feature roadmap.

## 2. Pilot Purpose

Validate:

- Real church workflow usability.
- Normal-user spiritual life flows.
- Staff management flows.
- Mobile and bilingual readiness.
- Permission and visibility safety.

Do not treat this as a full ERP validation. Finance, HR, broad CRM, automatic scheduling, attendance, reminders, swaps, availability, and complex operations are outside this pilot.

## 3. Pilot Roles

Use these tester roles where possible:

- Normal church member.
- Small group member.
- User without small group.
- Bible Study manager.
- Ministry coordinator.
- Staff reviewer/moderator.
- Superuser/admin fallback.

## 4. Required Pilot Data

Prepare or identify:

- Active reading plan.
- At least one joined reading plan.
- Published Bible Study schedule.
- Published Weekly Bible Study guide.
- Generated Small Group Bible Study meeting.
- MinistryContext CM / EM labels if available.
- ServiceEvent with CM label.
- ServiceEvent with EM label.
- ServiceEvent with blank label.
- MinistryTeam.
- TeamAssignment.
- Assigned serving user.
- Reported reflection.
- Prayer request and reported prayer, if applicable.

Record the exact test data:

| Data item | Value |
| --- | --- |
| Active reading plan | |
| Joined reading plan | |
| Bible Study schedule | |
| Weekly Bible Study guide | |
| Small Group Bible Study meeting | |
| CM MinistryContext | |
| EM MinistryContext | |
| CM-labeled ServiceEvent | |
| EM-labeled ServiceEvent | |
| Blank-label ServiceEvent | |
| MinistryTeam | |
| TeamAssignment | |
| Assigned serving user | |
| Reported reflection | |
| Prayer request / reported prayer | |

## 5. Validation Flow By Module

### Normal-User Flows

- Login.
- Logout.
- Today.
- Reading.
- Bible Study.
- Prayer.
- My Serving.
- Profile.
- Chinese/English toggle.
- Mobile nav.

Expected:

- Core pages load without crashes.
- Navigation labels are clear.
- Users see only content intended for them.
- Empty states are safe and understandable.
- Language toggle changes app UI language without corrupting user-entered content.

### Staff Flows

- Staff dropdown.
- Reading Plan Admin.
- User Admin.
- Reflection Reports.
- Prayer Reports, if used.
- Bible Study Schedules.
- Weekly Bible Study Guides.
- Small Group Meetings.
- Service Events.
- Ministry Teams.
- Team Assignments.
- Lighting Pilot Import, if included.

Expected:

- Staff can reach the grouped management flows from the Staff menu.
- Staff can perform the core pilot management tasks.
- Staff pages do not appear in normal-user navigation.
- Legacy Bible Study V1 is not promoted in normal or staff visible UI.

## 6. Permission And Visibility Validation

Validate:

- Normal users are blocked from staff pages.
- Small-group Bible Study content is isolated to the user's own small group.
- A user without a small group sees a safe empty state.
- My Serving shows only relevant assignments for the logged-in user.
- My Serving does not hide valid assignments.
- Hidden/reported reflections behave correctly for author, normal user, and staff reviewer.
- Prayer reporting/moderation does not expose hidden content incorrectly, if prayer reporting is used.
- Legacy Bible Study V1 remains hidden from promoted UI.

No-Go examples:

- Normal user can access staff pages.
- User sees another small group's Bible Study meeting, preparation, roles, or worship set.
- User sees another person's serving assignment.
- Hidden/reported content leaks to the wrong audience.

## 7. Mobile Validation

Test on:

- iPhone Safari.
- Android Chrome, if available.

Check:

- Top nav.
- Staff dropdown.
- Reading admin pages.
- Bible Study pages.
- ServiceEvent form.
- TeamAssignment pages.
- My Serving.
- Prayer pages.

Expected:

- Staff dropdown opens under or near the Staff / 同工管理 parent trigger.
- Staff dropdown is tall enough and internally scrollable.
- Top nav has no unstable hide-on-scroll behavior.
- Forms remain usable.
- Buttons remain reachable.
- Long names and bilingual labels wrap acceptably.
- Horizontal scrolling is acceptable for staff tables if the page itself does not break.

## 8. Bilingual Validation

Check both Chinese and English modes.

Expected:

- Chinese mode has no obvious English residuals in app-owned UI.
- English mode has no Chinese hard-coding in app-owned UI.
- User-entered content may remain in the language originally entered.
- ServiceEvent MinistryContext wording uses label concepts, not audience-scope/filtering concepts.
- Bible Study wording uses Schedule, Weekly Guide, and Small Group Meeting concepts, not legacy V1 wording.

Key pages to check:

- Main nav.
- Today.
- Reading and My Reading Plans.
- Reading Plan Admin.
- Bible Study normal landing.
- Bible Study Schedules.
- Weekly Bible Study Guides.
- Small Group Meetings.
- Prayer.
- Reflection Reports.
- Prayer Reports, if included.
- User Admin.
- My Serving.
- Service Events.
- Ministry Teams.
- Team Assignments.
- Profile.

## 9. Issue Severity Levels

| Level | Definition | Examples |
| --- | --- | --- |
| P0 Blocker | Cannot pilot, data leak, permission leak, or crash on a core flow. | Staff page exposed to normal user; common route crashes; cross-group Bible Study leak. |
| P1 Must fix before wider pilot | Core workflow broken, mobile staff menu unusable, or major Chinese residual. | Staff cannot manage Bible Study flow; My Serving misses valid assignments; mobile Staff menu cannot be used. |
| P2 Pilot acceptable but fix soon | Layout rough, minor wording issue, or non-core inconvenience. | Awkward wrapping, minor label mismatch, table needs horizontal scroll. |
| P3 Backlog | Nice-to-have, future feature, or deferred item. | Reminder request, availability workflow, new filtering request. |

## 10. Hotfix Policy

- Fix only P0/P1 issues during the pilot RC unless explicitly approved.
- Put P2/P3 issues in the backlog unless the fix is very small and low-risk.
- Do not add new features during pilot validation.
- Do not make schema changes unless unavoidable and approved.
- Every hotfix must include targeted tests/checks.
- Keep hotfixes narrow and tied to a recorded issue.

## 11. Go / No-Go Decision

Go if:

- Core normal-user flows pass.
- Core staff flows pass.
- No permission leaks are found.
- No major mobile blockers are found.
- No major bilingual blockers are found.
- Known limitations are understood by testers and pilot coordinators.

No-Go if:

- Staff pages leak to normal users.
- Bible Study group visibility leaks.
- My Serving leaks unrelated assignments or hides valid assignments.
- Staff cannot manage Bible Study or serving flows.
- Mobile Staff menu is unusable.
- Common pilot routes crash.

## 12. Post-Pilot Outcomes

Possible outcomes:

- Promote RC to pilot release.
- Cut `v0.9-pilot-rc2` after hotfixes.
- Delay pilot due to blockers.
- Start post-pilot backlog planning.

## 13. Sign-Off Table

| Tester | Role | Device/browser | Date | Result | Issues | Go/No-Go |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |
| | | | | | | |
| | | | | | | |

## 14. Deferred Items Reminder

The following deferred items are not pilot blockers unless their absence breaks a documented pilot flow:

- ChurchStructureUnit.
- Hierarchical multi-select audience scope.
- ServiceEvent filtering.
- Community Activities.
- Checklist V1.
- Automatic scheduling.
- Reminders.
- Availability.
- Swaps.
- Attendance.
- Full ERP.

## 15. Related QA References

Use this runbook together with:

- `docs/PILOT_RELEASE_CANDIDATE_READINESS.md`
- `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md`
- `docs/SERVICE_EVENT_MINISTRY_CONTEXT_QA_CHECKLIST.md`

Do not use pilot findings to expand scope during validation. Record future needs as backlog items unless they meet P0/P1 criteria.
