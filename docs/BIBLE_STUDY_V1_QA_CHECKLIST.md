# Bible Study V1 QA Checklist

Reference: `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md` is the source of product boundaries and non-goals.

## 1. Purpose

This checklist verifies Bible Study V1 browser flows, including Bible Study sessions, guides, scope visibility, and session-level worship songs.

It is not a feature roadmap. Use it before deployment and after major changes.

Automated tests still matter, but manual QA checks UI, bilingual behavior, permissions, and the full session flow in a browser.

## 2. Test Accounts Needed

- [ ] Regular user with small group
- [ ] Regular user in different small group
- [ ] User in district A
- [ ] User in district B
- [ ] Staff user
- [ ] User with pastor role
- [ ] User with coworker role / `CAP_MANAGE_BIBLE_STUDIES`
- [ ] User without Bible Study management permission

## 3. Pre-QA Setup

- [ ] Run tests.
- [ ] Confirm at least two districts.
- [ ] Confirm at least two small groups in different districts.
- [ ] Confirm BibleStudySeries exists.
- [ ] Confirm global published session exists.
- [ ] Confirm district-scoped published session exists.
- [ ] Confirm small-group scoped published session exists.
- [ ] Confirm draft session exists.
- [ ] Confirm completed session exists.
- [ ] Confirm cancelled session exists.
- [ ] Confirm one session has guide content.
- [ ] Confirm one session has discussion questions.
- [ ] Confirm one session has worship songs.

Commands:

```powershell
python manage.py check
python manage.py test accounts comments reading prayers studies -v 2
python manage.py runserver
```

## 4. Bible Study List

- [ ] Study list requires login.
- [ ] Published global session visible to logged-in user.
- [ ] District scoped session visible only to matching district.
- [ ] Small group scoped session visible only to matching group.
- [ ] Draft sessions hidden from regular users.
- [ ] Draft sessions visible to manager/staff.
- [ ] Cancelled sessions hidden from regular users.
- [ ] Upcoming tab works.
- [ ] Past tab works.
- [ ] Drafts tab appears only for manager/staff.
- [ ] Chinese labels display correctly.
- [ ] English labels display correctly.

## 5. Bible Study Detail

- [ ] Detail page opens for visible session.
- [ ] Title displays.
- [ ] Scripture reference displays.
- [ ] Thursday pre-study date/time displays.
- [ ] Friday study date/time displays.
- [ ] Location displays if present.
- [ ] Meeting link displays if present.
- [ ] Study guide displays.
- [ ] Discussion questions display.
- [ ] Pre-study notes display.
- [ ] Scope label displays.
- [ ] Status label displays.
- [ ] Regular user cannot see edit/manage controls.
- [ ] Manager/staff can see edit/manage controls.

## 6. Bible Study Create / Edit

- [ ] Regular user cannot access create page.
- [ ] User with `CAP_MANAGE_BIBLE_STUDIES` can access create page.
- [ ] Staff can access create page.
- [ ] Manager can create published session.
- [ ] Manager can create draft session.
- [ ] Manager can edit session.
- [ ] Manager can edit guide.
- [ ] Status change to draft works.
- [ ] Status change to published works.
- [ ] Status change to completed works.
- [ ] Status change to cancelled works.
- [ ] `published_at` behavior is correct.
- [ ] Scope validation works: global rejects district/small_group.
- [ ] Scope validation works: district requires district.
- [ ] Scope validation works: small_group requires small_group.

## 7. Scope / Privacy

- [ ] Global session visible to all logged-in users.
- [ ] District session hidden from outside district.
- [ ] Small group session hidden from outside group.
- [ ] Draft hidden from regular users.
- [ ] Cancelled hidden from regular users.
- [ ] Staff can see all.
- [ ] Manager can see drafts.

## 8. Worship Set

- [ ] Worship Songs section appears on session detail.
- [ ] Regular user can view worship songs for visible session.
- [ ] Empty state appears when no songs.
- [ ] Manager can open Manage Worship Songs.
- [ ] Manager can add worship song.
- [ ] Manager can edit worship song.
- [ ] Manager can delete worship song.
- [ ] Songs render in sort_order order.
- [ ] Song title displays.
- [ ] Key displays if present.
- [ ] YouTube link displays if present.
- [ ] Chord link displays if present.
- [ ] Lyrics link displays if present.
- [ ] Notes display if present.
- [ ] Worship songs are not visible if the parent session is not visible.
- [ ] No full song library behavior appears.
- [ ] No top nav item is added.

## 9. Bilingual Review

- [ ] Chinese study list page is Chinese.
- [ ] Chinese study detail page is Chinese.
- [ ] Chinese create/edit forms are Chinese.
- [ ] Chinese worship management page is Chinese.
- [ ] English pages remain English.
- [ ] Target Chinese label appears: 查经安排.
- [ ] Target Chinese label appears: 周四预查.
- [ ] Target Chinese label appears: 周五查经.
- [ ] Target Chinese label appears: 查经指引.
- [ ] Target Chinese label appears: 讨论问题.
- [ ] Target Chinese label appears: 预查备注.
- [ ] Target Chinese label appears: 查经前敬拜诗歌.
- [ ] Target Chinese label appears: 管理敬拜诗歌.
- [ ] Target English label appears: Bible Studies.
- [ ] Target English label appears: Thursday Pre-study.
- [ ] Target English label appears: Friday Bible Study.
- [ ] Target English label appears: Study Guide.
- [ ] Target English label appears: Discussion Questions.
- [ ] Target English label appears: Pre-study Notes.
- [ ] Target English label appears: Worship Songs.
- [ ] Target English label appears: Manage Worship Songs.

## 10. Home Page Integration

- [ ] Upcoming visible Bible Study session appears on home page if one exists.
- [ ] Hidden sessions do not appear to regular users.
- [ ] Draft sessions do not appear to regular users.
- [ ] Cancelled sessions do not appear to regular users.
- [ ] Home page does not become cluttered.
- [ ] Daily Reading remains primary.
- [ ] No new top-nav clutter.

## 11. Mobile / Usability

- [ ] Study list usable on narrow screen.
- [ ] Detail page readable on mobile.
- [ ] Worship song links are tappable.
- [ ] Forms are not too cramped.
- [ ] Long discussion questions remain readable.
- [ ] Meeting link is usable.

## 12. Known Non-Goals for Bible Study V1

- [ ] Worship songs are session-level only.
- [ ] No full worship song library.
- [ ] No automatic song transposition.
- [ ] No copyright management.
- [ ] No ServiceEvent integration yet.
- [ ] No MinistryTeam / Lighting Team integration yet.
- [ ] No attendance tracking yet.
- [ ] No automatic reminders yet.
- [ ] No pre-study response submission yet.

## 13. Release Readiness Decision

- [ ] All automated tests pass.
- [ ] Manual QA critical flows pass.
- [ ] Scope/privacy checks pass.
- [ ] Bilingual review passes.
- [ ] Manager/staff flows pass.
- [ ] Mobile basic review passes.
- [ ] Known issues documented.
- [ ] Bible Study V1 can be considered stable enough for pilot use.

## 14. Next Phase

After Bible Study V1 and Worship Set V1 QA, the next major development phase is ServiceEvent Foundation.

Do not begin:
- [ ] Lighting Team scheduling
- [ ] MinistryTeam Operations
- [ ] Automatic scheduling
- [ ] Full ServiceEvent expansion beyond foundation

until ServiceEvent Foundation is separately planned.
