# ServiceEvent Foundation V1 QA Checklist

Source of product boundaries: `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`.

## 1. Purpose

This checklist verifies ServiceEvent Foundation V1 browser flows.

It is not a feature roadmap. Use it before moving into Ministry Team Operations and after changes that may affect event visibility, permissions, navigation, or bilingual UI.

Automated tests still matter, but manual QA is needed for UI behavior, permissions, and bilingual review.

## 2. Test Accounts Needed

- [ ] Regular user with small group in district A
- [ ] Regular user with small group in district B
- [ ] Regular user without small group
- [ ] Staff user
- [ ] Pastor role user
- [ ] Elder role user
- [ ] Coworker role user with `CAP_MANAGE_SERVICE_EVENTS`
- [ ] User without service event management permission

Do not use real passwords in QA notes.

## 3. Pre-QA Setup

- [ ] Run tests.
- [ ] Confirm at least two districts exist.
- [ ] Confirm at least two small groups exist in different districts.
- [ ] Confirm sample events exist:
  - [ ] Global published event
  - [ ] District-scoped published event
  - [ ] Small-group-scoped published event
  - [ ] Draft event
  - [ ] Completed event
  - [ ] Cancelled event
- [ ] Confirm event types exist in UI:
  - [ ] Sunday Service
  - [ ] Bible Study
  - [ ] Special Meeting
  - [ ] Conference
  - [ ] Gospel Music Night
  - [ ] Baptism
  - [ ] Other

Commands:

```powershell
python manage.py check
python manage.py test accounts comments reading prayers studies events -v 2
python manage.py runserver
```

## 4. Event List

- [ ] Event list requires login.
- [ ] Published global event visible to logged-in user.
- [ ] District scoped event visible only to matching district.
- [ ] Small group scoped event visible only to matching group.
- [ ] Draft events hidden from regular users.
- [ ] Cancelled events hidden from regular users.
- [ ] Draft events visible to manager/staff.
- [ ] Cancelled events visible to manager/staff.
- [ ] Upcoming tab/filter works.
- [ ] Past tab/filter works.
- [ ] Drafts tab/filter appears only for manager/staff if implemented.
- [ ] Chinese labels display correctly.
- [ ] English labels display correctly.

## 5. Event Detail

- [ ] Detail page opens for visible event.
- [ ] Title displays.
- [ ] Event type displays.
- [ ] Start time displays.
- [ ] End time displays if present.
- [ ] Location displays if present.
- [ ] Meeting link displays if present.
- [ ] Scope displays.
- [ ] Status displays.
- [ ] Description displays.
- [ ] Regular user cannot see edit/cancel controls.
- [ ] Manager/staff can see edit/cancel controls.
- [ ] Cancelled event is not visible to regular user.
- [ ] Cancelled event is visible to manager/staff.

## 6. Create / Edit / Cancel

- [ ] Regular user cannot access create page.
- [ ] Staff can access create page.
- [ ] Pastor role user can access create page.
- [ ] Elder role user can access create page.
- [ ] Coworker role user with `CAP_MANAGE_SERVICE_EVENTS` can access create page.
- [ ] Manager can create published event.
- [ ] Manager can create draft event.
- [ ] Manager can edit event.
- [ ] Manager can cancel event.
- [ ] Cancelled event disappears from regular user list.
- [ ] Cancelled event remains visible to manager/staff.
- [ ] `published_at` behavior works correctly.
- [ ] End time cannot be before start time.

## 7. Scope / Privacy

- [ ] Global event visible to all logged-in users.
- [ ] District event hidden from users outside district.
- [ ] Small group event hidden from users outside small group.
- [ ] Draft event hidden from regular users.
- [ ] Cancelled event hidden from regular users.
- [ ] Staff can see all events.
- [ ] Manager can see drafts/cancelled events.
- [ ] Regular user without small group does not see district/small-group scoped events.

## 8. Event Types

- [ ] Sunday Service displays correctly.
- [ ] Bible Study displays correctly.
- [ ] Special Meeting displays correctly.
- [ ] Conference displays correctly.
- [ ] Gospel Music Night displays correctly.
- [ ] Baptism displays correctly.
- [ ] Other displays correctly.
- [ ] Chinese labels display correctly.
- [ ] English labels display correctly.

## 9. Navigation / Scope Discipline

- [ ] Events are not added to normal user top nav.
- [ ] Service Events appears only in Staff menu if implemented.
- [ ] Daily Reading home experience remains primary.
- [ ] Bible Study pages are not refactored into ServiceEvent in this phase.
- [ ] No MinistryTeam links appear.
- [ ] No Lighting Team links appear.
- [ ] No TeamAssignment/scheduling UI appears.

## 10. Bilingual Review

- [ ] Chinese event list page is Chinese.
- [ ] Chinese event detail page is Chinese.
- [ ] Chinese create/edit forms are Chinese.
- [ ] English pages remain English.
- [ ] Target Chinese labels appear:
  - [ ] 聚会事件
  - [ ] 聚会类型
  - [ ] 主日崇拜
  - [ ] 查经
  - [ ] 特别聚会
  - [ ] 特会
  - [ ] 福音音乐会
  - [ ] 洗礼
  - [ ] 开始时间
  - [ ] 结束时间
  - [ ] 范围
  - [ ] 状态
- [ ] Target English labels appear:
  - [ ] Service Events
  - [ ] Event Type
  - [ ] Sunday Service
  - [ ] Bible Study
  - [ ] Special Meeting
  - [ ] Conference
  - [ ] Gospel Music Night
  - [ ] Baptism
  - [ ] Start Time
  - [ ] End Time
  - [ ] Scope
  - [ ] Status

## 11. Mobile / Usability

- [ ] Event list usable on narrow screen.
- [ ] Event detail readable on mobile.
- [ ] Meeting link is tappable.
- [ ] Create/edit form is not too cramped.
- [ ] Date/time fields are usable.
- [ ] Status and scope labels are visually clear.

## 12. Known Non-Goals for ServiceEvent Foundation V1

- [ ] No MinistryTeam.
- [ ] No TeamAssignment.
- [ ] No Lighting Team scheduling.
- [ ] No automatic scheduling.
- [ ] No availability matrix.
- [ ] No swap requests.
- [ ] No checklists.
- [ ] No service review notes.
- [ ] No worship flow management.
- [ ] No full event-management system.
- [ ] No top-nav clutter.

## 13. Release Readiness Decision

- [ ] All automated tests pass.
- [ ] Manual QA critical flows pass.
- [ ] Scope/privacy checks pass.
- [ ] Bilingual review passes.
- [ ] Manager/staff flows pass.
- [ ] Mobile basic review passes.
- [ ] Known issues documented.
- [ ] ServiceEvent Foundation V1 can be considered stable enough to support Ministry Team Operations planning.

## 14. Next Phase

After ServiceEvent Foundation V1 QA, the next major development phase is Ministry Team Operations V1.

Do not begin:
- Lighting Team Pilot
- Automatic scheduling
- Availability matrix
- Swap requests
- Advanced checklists
- Multi-team dashboard

until Ministry Team Operations V1 is separately planned and implemented with generic MinistryTeam models.
