# ServiceEvent MinistryContext QA Checklist

Manual/browser QA checklist for CS-F.3A closure after CS-F.3 added optional `ServiceEvent.ministry_context`.

This checklist verifies label-only behavior for `events.ServiceEvent`. It must not be used to expand scope into ServiceEvent audience filtering, TeamAssignment filtering, MinistryTeam changes, My Serving changes, Bible Study changes, Community Activities, Checklist V1, `ChurchStructureUnit`, scheduling, reminders, availability, swaps, attendance, or role-aware permissions.

Current code reality:

- `ServiceEvent` is in the `events` app.
- `ServiceEvent.ministry_context` is optional and nullable.
- `ServiceEvent.ministry_context` is a label only.
- Visibility remains controlled by existing ServiceEvent status/scope rules.
- TeamAssignment visibility and member selection remain controlled by existing TeamAssignment and MinistryTeam rules.
- My Serving remains based on assigned TeamAssignmentMember rows, assignment status, and event time.

## 1. Required Test Data

Prepare or identify:

- MinistryContext: `CM / Chinese Ministry`.
- MinistryContext: `EM / English Ministry`.
- ServiceEvent with MinistryContext = CM.
- ServiceEvent with MinistryContext = EM.
- ServiceEvent with no MinistryContext.
- At least one MinistryTeam.
- At least one TeamAssignment linked to the CM-labeled ServiceEvent.
- At least one TeamAssignment linked to the EM-labeled ServiceEvent.
- At least one TeamAssignment linked to the blank ServiceEvent.
- Normal serving user assigned to at least one event.
- Staff user with ServiceEvent and TeamAssignment management access.

Record the exact data used:

- CM MinistryContext:
- EM MinistryContext:
- CM-labeled ServiceEvent:
- EM-labeled ServiceEvent:
- Blank ServiceEvent:
- MinistryTeam:
- CM event TeamAssignment:
- EM event TeamAssignment:
- Blank event TeamAssignment:
- Normal serving user:
- Staff user:

## 2. Staff ServiceEvent Create/Edit QA

Manual steps:

- Log in as staff.
- Create a ServiceEvent with MinistryContext = CM.
- Create a ServiceEvent with MinistryContext = EM.
- Create a ServiceEvent with MinistryContext blank.
- Edit each event and change MinistryContext.
- Edit each event and clear MinistryContext.

Expected:

- MinistryContext field is optional.
- Blank saves successfully.
- CM saves successfully.
- EM saves successfully.
- Clearing the value works.
- Form wording or surrounding staff guidance makes clear this is a label only.
- UI does not imply MinistryContext controls visibility, assignment eligibility, or filtering.
- No fake Combined Ministry option is required or created.

## 3. ServiceEvent List/Detail Display QA

Manual steps:

- Open ServiceEvent list.
- Open ServiceEvent detail for the CM-labeled event.
- Open ServiceEvent detail for the EM-labeled event.
- Open ServiceEvent detail for the blank event.

Expected:

- MinistryContext metadata is visible where appropriate for CM and EM events.
- Blank context displays cleanly, either by omitting the label or by showing a clear empty-state value such as `Not specified`.
- Event date/time/location/status remain clear.
- Staff can distinguish CM, EM, and blank events.
- No layout break.
- No wording suggests MinistryContext is an audience filter.

## 4. TeamAssignment Create/Edit/List/Detail QA

Manual steps:

- Create a TeamAssignment for the CM-labeled ServiceEvent.
- Create a TeamAssignment for the EM-labeled ServiceEvent.
- Create a TeamAssignment for the blank ServiceEvent.
- Open TeamAssignment list.
- Open TeamAssignment detail for each assignment.
- Edit existing assignments.
- Change assigned members after selecting a MinistryTeam.

Expected:

- All ServiceEvents remain selectable regardless of MinistryContext.
- Assignment behavior is unchanged.
- Member filtering remains based on MinistryTeam, not MinistryContext.
- Cross-context ServiceEvents are not blocked.
- MinistryContext label appears only as helpful metadata if currently displayed.
- Blank ServiceEvents do not crash assignment pages.
- No accidental filtering was introduced.

## 5. My Serving QA

Manual steps:

- Log in as a serving user assigned to a CM-labeled event.
- Visit My Serving / 我的服事.
- Confirm the assignment if the current flow supports confirmation.
- Log in as a serving user assigned to an EM-labeled event.
- Visit My Serving / 我的服事.
- Confirm the assignment if the current flow supports confirmation.
- Log in as a serving user assigned to a blank event.
- Visit My Serving / 我的服事.
- Confirm the assignment if the current flow supports confirmation.
- Check the Today lightweight My Serving card, if the user has a pending or near-term assignment.

Expected:

- My Serving still shows assigned serving items based on assignment status and event time.
- MinistryContext does not hide assigned items.
- Blank ServiceEvents do not hide assigned items.
- Confirmation behavior is unchanged.
- Today lightweight My Serving card behavior is unchanged.
- My Serving does not imply MinistryContext controls visibility.

## 6. Bible Study Regression

Manual steps:

- Visit `/studies/` as a normal user.
- Confirm Bible Study Schedule MinistryContext scope still works if test data exists.
- Log in as staff.
- Open Bible Study schedule pages.
- Open Weekly Bible Study Guide pages.
- Open Small Group Meeting pages.
- Open meeting generation preview/confirmation pages if existing test data supports it.

Expected:

- CS-F.3 did not change Bible Study behavior.
- Bible Study Schedule MinistryContext scope remains schedule -> guide -> generated meeting.
- Staff Bible Study schedule/guide/meeting generation pages still load.
- Legacy V1 Bible Study UI is not visibly promoted.
- No ServiceEvent or TeamAssignment behavior is introduced into Bible Study generation.

## 7. Bilingual UI

Check labels:

- Ministry Context / 事工范围.
- Service Event / 聚会事件, or the existing project wording for service events.
- My Serving / 我的服事.
- Team Assignment / existing Chinese wording for team assignments.

Expected:

- English and Chinese labels are understandable.
- No misleading wording suggests MinistryContext filters events, assignments, or My Serving.
- No old ambiguous Bible Study Admin wording reappears.
- Existing project wording remains consistent enough for staff to understand the workflow.

## 8. Mobile QA

Manual steps at mobile width:

- Open ServiceEvent list.
- Open ServiceEvent detail.
- Open ServiceEvent create/edit form.
- Open TeamAssignment list.
- Open TeamAssignment detail.
- Open TeamAssignment create/edit form.
- Open My Serving.
- Open the staff menu.

Expected:

- MinistryContext label does not cause horizontal overflow.
- Forms remain usable.
- Staff dropdown remains usable.
- Long MinistryContext labels wrap acceptably.
- Buttons remain reachable.
- Event date/time/location/status remain readable.

## 9. Regression Checks

Quick browser checks:

- Today loads.
- Reading loads.
- Bible Study loads.
- Prayer loads.
- My Serving loads.
- Profile loads.
- Staff menus load.
- ServiceEvent blank MinistryContext does not crash pages.
- Existing ServiceEvents created before CS-F.3 still display and edit correctly.
- Existing TeamAssignments still display and edit correctly.
- Existing My Serving assignments still display correctly.

## 10. Go / No-Go Decision

Go if:

- ServiceEvent can save CM, EM, and blank MinistryContext.
- ServiceEvent list/detail displays the label cleanly.
- TeamAssignment behavior remains unchanged.
- My Serving behavior remains unchanged.
- Blank/legacy ServiceEvents work.
- No filtering behavior appears.
- Mobile and bilingual checks pass.

No-go if:

- Any assignment flow filters or blocks events by MinistryContext.
- Blank ServiceEvents break display or forms.
- My Serving hides valid assignments.
- UI implies MinistryContext controls visibility when it does not.
- Mobile layout breaks.
- Legacy V1 Bible Study UI reappears.

Sign-off:

- [ ] Go: pass.
- [ ] Go with minor non-blocking UI issues.
- [ ] No-go: blocked by ServiceEvent create/edit behavior.
- [ ] No-go: blocked by ServiceEvent display behavior.
- [ ] No-go: blocked by TeamAssignment behavior.
- [ ] No-go: blocked by My Serving behavior.
- [ ] No-go: blocked by Bible Study regression.
- [ ] No-go: blocked by bilingual wording.
- [ ] No-go: blocked by mobile usability.
- [ ] No-go: blocked by unexpected filtering behavior.

Notes:

- Tester:
- Date:
- Browser/device:
- Desktop viewport tested:
- Mobile viewport tested:
- Language(s) tested:
- Staff user:
- Normal serving user:
- ServiceEvents tested:
- TeamAssignments tested:
- Blocking issues:
- Minor follow-up issues:
- Go/no-go decision:
