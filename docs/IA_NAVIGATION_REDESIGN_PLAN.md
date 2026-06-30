# IA Navigation Redesign Plan

Status: Implemented. The recommended top-level user navigation and the staff
dropdown grouping described below are now in place. The authenticated navbar IA
cleanup — primary nav for the main user workflows; staff/admin and account
functions grouped into caret dropdowns; a staff Structure Setup / 结构设置
section linking both Church Structure and Ministry Structure — is complete and
passed manual QA. This document is retained as the originating IA rationale; the
sequence in Section 8 is historical/superseded by the shipped navigation.

## 1. Purpose

This document records the recommended information architecture and navigation reset before further feature development.

The project is no longer only a Bible reading check-in app. It is becoming a lightweight church spiritual life and ministry workflow system. Daily Reading remains a core module, but the product should not become a full church ERP.

## 2. Current Problem

- The project has grown beyond "Bible Reading".
- Home/navigation currently mixes spiritual-life modules and ministry-operation modules too loosely.
- Bible Study exists as a major module but should be more clearly surfaced.
- My Serving should not be hidden inside Daily Reading.
- Staff/admin navigation needs grouping as the system grows.

## 3. Recommended Top-Level User Navigation

Superseded by the shipped IA. The original recommendation below kept Profile /
个人资料 as a top-level item; the shipped navbar instead moves Profile and
account functions into an account dropdown. The shipped IA is:

- Primary nav: Today / 今日, Reading / 读经, Bible Study / 查经, Prayer / 代祷,
  Church Gatherings / 教会聚会, My Serving / 我的服事.
- Account dropdown: Profile / 个人资料, My Units / 我负责的单位 (when available),
  language switch, logout.

Original (historical) recommendation:

English:
- Today
- Reading
- Bible Study
- Prayer
- My Serving
- Profile

Chinese:
- 今日
- 读经
- 查经
- 代祷
- 我的服事
- 个人资料

## 4. Page Responsibility

### Today Dashboard

The Today Dashboard should be a lightweight summary page only.

It may show summary cards such as:
- today's reading
- upcoming Bible Study
- next serving assignment
- prayer entry point

It must not become a management page. It must not show full serving management. If serving appears here, it should be a small summary card linking to My Serving.

### Reading

Reading owns:
- Daily Reading
- plans
- check-ins
- reading guide
- reading calendar
- available plans
- reflection flow

Reading should not absorb Bible Study or Ministry Operations.

### Bible Study

Bible Study must become a first-class user-facing module.

It owns:
- church-wide study material
- small-group study preparation
- the real Friday Bible Study workflow

### Prayer

Prayer owns:
- prayer requests
- prayer marks
- prayer comments
- prayer-related reporting

### My Serving

My Serving owns serving assignments visible to the current user.

It should remain separate from Daily Reading. Users should go here for serving details, confirmation, assignment notes, team/event information.

### Profile

Profile owns:
- user profile
- personal church context

## 5. Staff Navigation Grouping

Shipped staff dropdown groups (updated to match the shipped IA):

### Content Management

- Reading Plan Admin
- Bible Study Admin

### Ministry Operations

- Service Events / Church Gatherings
- Ministry Teams
- Team Assignments

### Structure Setup / 结构设置

- Church Structure Setup & Review
- Ministry Structure

### Users and Review

- User Admin
- Reflection Reports
- Prayer Reports
- Django Admin

Lighting Pilot Import/Setup is no longer listed in the staff dropdown: it is
retired from normal discoverable UI and remains only as a retained
route/view/service/command tool if needed.

## 6. Bilingual UI Principles

- Chinese pages should show Chinese labels/data when available.
- English pages should show English labels/data when available.
- Avoid Chinese UI showing English-only event/team names when bilingual fields exist.

Examples:
- 主日崇拜 / Sunday Service
- 灯光组 / Lighting Team

## 7. Non-Goals

- No full ERP dashboard.
- No attendance tracking.
- No scheduling automation.
- No reminders.
- No checklist work yet.

## 8. Suggested Future Implementation Sequence

1. Rename site-level positioning from "Bible Reading" / "读经打卡" to a broader church spiritual life/workflow name.
2. Rename home concept from "Today's Reading" to "Today" only if it becomes a true dashboard.
3. Add Bible Study to normal user navigation.
4. Move available reading plans into Reading module if they currently clutter Today.
5. Keep My Serving independent.
6. Group staff navigation.

