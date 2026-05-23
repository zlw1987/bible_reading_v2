# Lighting Team Pilot Setup Guide

## 1. Purpose / 目的

This setup is for a limited Lighting Team pilot. It uses the generic Ministry Operations models:

ServiceEvent -> MinistryTeam -> TeamAssignment -> TeamAssignmentMember -> My Serving confirmation.

My Serving is a dedicated top-nav entry for logged-in users. Serving assignments are no longer mixed into the Daily Reading home page.

It is not automatic scheduling.

中文说明：我的服事现在是登录用户的独立顶部导航入口，服事安排不再混在今日读经首页里。

这个设置流程只用于有限范围的灯光组试点。它使用通用的事工团队模型：

ServiceEvent -> MinistryTeam -> TeamAssignment -> TeamAssignmentMember -> 我的服事确认。

这不是自动排班。

## 2. Setup Sunday Services / 创建固定主日聚会

English:
- Open Service Events.
- Click Create Recurring Events.
- Set the date range.
- Keep weekday as Sunday unless another recurring service is needed.
- Preview the events.
- Create events after reviewing duplicates and skipped dates.
- Check the created ServiceEvent records.

中文：
- 打开聚会事件。
- 点击批量创建固定聚会。
- 设置日期范围。
- 除非需要其他固定聚会，否则星期保持为星期日。
- 先预览。
- 检查重复和跳过日期后，再创建聚会事件。
- 检查已创建的 ServiceEvent 记录。

## 3. Prepare CSV / 准备 CSV

Use `docs/examples/lighting_team_pilot_template.csv`.

Required columns:
- `event_date`
- `event_type`
- `event_title`
- `assigned_member`

Optional columns:
- `start_time`
- `end_time`
- `service_detail`
- `special_event_note`
- `worship_team`
- `member_email`
- `playbook_link`

Forbidden columns:
- `phone_number`
- `private_notes`
- `prayer_notes`
- `zoom_password`

Use future 2-3 months only. Use `YYYY-MM-DD` date format. Use `member_email` when the person already has an account.

使用 `docs/examples/lighting_team_pilot_template.csv`。

必填字段：
- `event_date`
- `event_type`
- `event_title`
- `assigned_member`

可选字段：
- `start_time`
- `end_time`
- `service_detail`
- `special_event_note`
- `worship_team`
- `member_email`
- `playbook_link`

禁止字段：
- `phone_number`
- `private_notes`
- `prayer_notes`
- `zoom_password`

只使用未来 2-3 个月的数据。日期格式使用 `YYYY-MM-DD`。如果服事人员已有账号，请填写 `member_email`。

## 4. Dry Run / 试运行

English:
- Open Lighting Pilot Import.
- Upload the CSV.
- Click Dry Run.
- Review counts and row errors.
- Fix CSV issues before importing.

中文：
- 打开灯光组试点导入。
- 上传 CSV。
- 点击试运行。
- 检查统计数量和行错误。
- 正式导入前先修正 CSV 问题。

## 5. Import / 正式导入

Only import after dry-run is clean. Confirm which records were created or reused:

- Lighting Team MinistryTeam
- TeamMembership
- ServiceEvent
- TeamAssignment
- TeamAssignmentMember

只有试运行干净后才正式导入。确认哪些记录被创建或复用：

- Lighting Team MinistryTeam
- TeamMembership
- ServiceEvent
- TeamAssignment
- TeamAssignmentMember

## 6. Verify in Browser / 浏览器验证

English:
- Staff checks Lighting Team.
- Staff checks Team Assignments.
- Assigned user opens My Serving.
- Assigned user confirms assignment.
- Unrelated user cannot see assignment.

中文：
- 同工检查 Lighting Team。
- 同工检查服事排班。
- 被安排的用户打开我的服事。
- 被安排的用户确认服事。
- 无关用户不能看到该服事安排。

## 7. Troubleshooting / 常见问题

Member not linked to user:
- Check that `member_email` matches an existing User email.

Date rejected as past:
- Use future dates only for pilot data.

Duplicate skipped:
- Existing ServiceEvent or assignment already matches the row.

Forbidden column error:
- Remove sensitive columns such as phone numbers, private notes, prayer notes, or Zoom passwords.

User cannot see My Serving assignment:
- Confirm the TeamMembership is linked to the user account and is active.
- Confirm the TeamAssignmentMember exists.
- Confirm the assignment is not cancelled.

成员没有关联到用户：
- 检查 `member_email` 是否匹配已有用户邮箱。

日期因为过去日期被拒绝：
- 试点数据只使用未来日期。

重复记录被跳过：
- 已有 ServiceEvent 或 assignment 与该行匹配。

禁止字段错误：
- 删除电话号码、私人备注、代祷备注、Zoom 密码等敏感字段。

用户在我的服事看不到安排：
- 确认 TeamMembership 已关联到该用户账号并且启用。
- 确认 TeamAssignmentMember 存在。
- 确认排班没有被取消。

## 8. Explicit Non-Goals / 非目标

- No automatic scheduling. / 不做自动排班。
- No availability. / 不做可服事时间。
- No swap request. / 不做换班申请。
- No checklist. / 不做 checklist。
- No full historical import. / 不导入完整历史数据。
- No sensitive data. / 不导入敏感数据。
