# Staff Setup Guide / 同工设置指南

Status: **STAFF-ONLY / INTERNAL-ONLY.** This is a limited-trial operations
guide that describes shipped behavior only. It is not a production-readiness
certification and is not an ordinary member help page. Do not expose this
document to ordinary members. If a future slice surfaces it inside the app,
that route must be explicitly staff/superuser gated.

状态：**仅限同工／内部使用。** 本文是有限试运行操作指南，只描述已经交付的行为；
它不是生产就绪认证，也不是普通成员帮助页面。请勿向普通成员公开本文。若未来另行批准
在应用内展示，相关路由必须明确限制为 staff/superuser 才可访问。

## 1. Purpose and operating boundary / 用途与操作边界

**English**

Use this guide to prepare a small, supervised trial and to verify the boundaries
between belonging, audience visibility, agenda items, and serving. Record the
target environment, operator, date, enabled modules, audit result, warnings
reviewed, and smoke-test accounts. A recorded local result does not replace a
fresh check against the exact trial environment.

**中文**

本文用于准备小规模、有人监督的有限试运行，并核对归属、受众可见性、日程项目与服事
之间的边界。请记录目标环境、操作同工、日期、启用模块、审计结果、已复核警告及冒烟
测试账号。本地已有结果不能代替对实际试运行环境重新检查。

Current context / 当前背景：

- Community Activities V1 manual QA passed by user confirmation.
  Community Activities V1 的手动 QA 已由用户确认通过。
- Official Announcements V1 manual QA passed by user confirmation in
  `ANNOUNCEMENTS-QA-PASS.1A`.
  Official Announcements V1 的手动 QA 已在 `ANNOUNCEMENTS-QA-PASS.1A`
  中由用户确认通过。
- The latest recorded setup-readiness audit reported 0 blockers and 19
  warnings. This supports limited-trial planning only; review the warnings and
  rerun the audit against the target database before inviting real users.
  最近记录的设置就绪审计结果为 0 个 blocker、19 个 warning；这只支持有限试运行
  规划。邀请真实用户前，必须复核警告，并对目标数据库重新运行审计。

## 2. Deployment, migrations, and module enablement / 部署、迁移与模块启用

**English**

1. Confirm that the intended code revision and environment-specific settings
   are deployed to the trial environment.
2. Review migration state and planned operations. Apply migrations only through
   the separately approved deployment procedure; this guide does not authorize
   a data-changing command.
3. Run the Django system check and confirm that model changes have no missing
   migration.
4. Review `CMS_ENABLED_MODULES` in the deployed settings. The shipped registered
   keys are `reading`, `prayers`, `studies`, `events`, `community_events`,
   `announcements`, and `ministry`; the default enables all of them. Unknown
   keys fail configuration validation, and `ministry` requires `events`.
5. Confirm the intended navigation, Today contributions, staff links, and
   module-owned Staff Overview/readiness content with both enabled and
   deliberately disabled modules.

Suggested read-only or no-write verification commands:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py migrate --plan
python manage.py audit_trial_setup_readiness --verbose --limit 20 --fail-on-blockers
```

`audit_trial_setup_readiness` is read-only and has no `--apply` mode.
`--limit` limits examples only, not the scan.

**中文**

1. 确认试运行环境部署的是预期代码版本及该环境专用设置。
2. 检查迁移状态及计划操作。只有在另行批准的部署流程中才可执行迁移；本文不授权任何
   会修改数据的命令。
3. 运行 Django 系统检查，并确认模型没有缺失迁移。
4. 检查部署设置中的 `CMS_ENABLED_MODULES`。已交付的注册键为 `reading`、
   `prayers`、`studies`、`events`、`community_events`、`announcements` 和
   `ministry`，默认全部启用。未知键会导致配置校验失败；`ministry` 依赖
   `events`。
5. 对预期启用及刻意停用的模块，分别核对导航、Today 内容、同工入口，以及模块自有的
   Staff Overview／就绪检查内容。

Important limitation / 重要限制：

Module disablement is **surface-gated, not route hard-off**. It hides registered
navigation and selected module-owned surfaces/providers, but does not unload
apps, models, admin registrations, or URLs. Direct routes retain their existing
view-level permissions and visibility rules.

停用模块目前是**界面入口控制，而不是路由硬关闭**：它会隐藏已注册导航及部分模块自有
界面／provider，但不会卸载应用、模型、admin 注册或 URL；直接路由仍依赖原有视图权限
和可见性规则。

## 3. Accounts, Church Structure, and audience verification / 账号、教会结构与受众验证

**English**

- Confirm at least one usable staff or superuser account for trial operations.
  Staff authority must come from the existing permission boundary, never from
  `ChurchStructureMembership`.
- Confirm the `ChurchStructureUnit` hierarchy reflects the intended active
  church structure. Units used for audiences or memberships must be active.
- Confirm each participating ordinary member has the intended active primary
  `ChurchStructureMembership`. Resolve ambiguous multiple active primary rows
  before the trial.
- Do not create a fake `Unassigned` unit. “Unassigned” means that a user has no
  blocking active primary membership and no pending membership request; it is
  a state, not a `ChurchStructureUnit`.
- Treat membership as belonging only. It may establish the member's structure
  context for approved visibility consumers, but it grants no serving,
  coworker role, staff capability, team assignment, or Bible Study role.
- Treat every module-owned audience row as visibility configuration only.
  Audience visibility is not assignment, attendance, approval, or serving.
- For each scoped item, test with a matching ordinary member and a nonmatching
  ordinary member. Selected ancestor units include qualifying descendant
  memberships under the shipped structure-native matching rule; zero audience
  rows fail closed for ordinary users.

**中文**

- 确认至少有一个可用的 staff 或 superuser 账号负责试运行。Staff 权限必须来自现有
  权限边界，绝不能由 `ChurchStructureMembership` 推导。
- 确认 `ChurchStructureUnit` 层级符合预期且需要用于受众或归属的单位均为 active。
- 确认每位参与试运行的普通成员都有正确的 active primary
  `ChurchStructureMembership`；试运行前必须处理多个 active primary 的冲突。
- 不要创建假的 `Unassigned` 单位。“未分配”表示用户没有阻挡性的 active primary
  membership，也没有 pending membership request；它是一种状态，不是
  `ChurchStructureUnit`。
- Membership 只表示归属。它可为已批准的可见性消费者提供结构上下文，但不会授予
  服事、同工角色、staff 权限、团队排班或查经角色。
- 各模块的 audience row 只控制可见性，不代表指派、出席、审批或服事。
- 每个受众限定项目都要用一位匹配成员和一位不匹配成员测试。按当前结构原生匹配规则，
  选择祖先单位会包含符合条件的后代 membership；普通用户遇到零受众行时应 fail
  closed。

## 4. Official Announcements setup / 官方公告设置

**English**

Official Announcements is official staff-authored communication. Its management
workflow is staff/superuser-only.

1. Confirm `announcements` is enabled and the intended staff management and
   authenticated member navigation surfaces appear.
2. As staff/superuser, create a draft with English and Chinese title/body
   content. Check supported-language display and fallback.
3. Choose one or more existing active `ChurchStructureUnit` rows with the
   audience picker. Do not invent audience units for an announcement.
4. Choose normal or check **Important**. Important makes an eligible item a
   Today-reminder candidate; it never bypasses audience visibility.
5. Set the publication window (`publish_start` and optional `publish_end`) and
   save the draft. Verify that future and expired windows remain hidden from
   ordinary members.
6. Publish through the shipped staff action, then verify list and detail with a
   matching ordinary member. Verify the nonmatching member cannot see the item
   and receives 404 on direct hidden-detail access.
7. Archive the announcement and confirm member list/detail visibility ends.
   Archiving preserves its audience rows.
8. For an active Important item, confirm Today shows at most one newest visible
   Important reminder and only its localized title/detail link. Confirm a
   normal announcement does not appear there.

Announcements does **not** add Staff Overview content, My Serving items,
serving state, notifications, `ServiceEvent`, Community Activities, signup,
attendance, or approval/request-changes behavior.

**中文**

Official Announcements 是由 staff 撰写的官方沟通模块，其管理流程只允许
staff/superuser 使用。

1. 确认 `announcements` 已启用，预期的同工管理入口及登录成员导航已出现。
2. 使用 staff/superuser 创建 draft，并填写中英文标题与正文；检查支持语言下的显示
   和 fallback。
3. 使用现有 audience picker 选择一个或多个 active `ChurchStructureUnit`；不要为了
   公告虚构结构单位。
4. 选择普通优先级或勾选 **Important**。Important 只使符合条件的公告可成为 Today
   提醒候选，绝不会绕过受众可见性。
5. 设置发布时间窗（`publish_start` 及可选 `publish_end`）并保存草稿；确认未来开始
   和已过期公告对普通成员隐藏。
6. 通过已交付的同工操作发布；用匹配成员核对列表与详情，再用不匹配成员确认不可见，
   且直接访问隐藏详情返回 404。
7. 归档公告并确认成员列表／详情不再显示；归档会保留 audience rows。
8. 对有效的 Important 公告，确认 Today 最多显示一条最新且当前用户可见的提醒，并且
   只显示本地化标题／详情链接；普通公告不进入 Today。

Announcements **不会**增加 Staff Overview 内容、My Serving 项、服事状态、通知、
`ServiceEvent`、Community Activities、报名、出席或 approval/request-changes 流程。

## 5. Community Activities setup / 社区活动设置

**English**

Community Activities is an independent, secondary module for signup-oriented
community and fellowship activities. It is not the official Church Gatherings
or serving system.

1. Confirm `community_events` is enabled.
2. As an eligible member with active primary membership, create a complete
   draft or submit it for review. Activity Scope is required and saves
   `CommunityActivityAudienceScope` rows using active `ChurchStructureUnit`
   choices. The optional audience note is review context, not visibility.
3. Confirm drafts remain visible only to the primary creator, linked
   co-organizers, and staff/superusers. Only the primary creator manages
   co-organizers and submits a draft; co-organizers may edit within the shipped
   draft/pending-review/changes-requested boundary.
4. As staff/superuser, use the shipped review inbox to publish, request changes
   with a note, or cancel/reject. Verify creator edits/resubmission return a
   `changes_requested` item to `pending_review`.
5. After publication, verify Activity Scope visibility with matching and
   nonmatching members.
6. Test signup, cancel, and re-signup. For capped activities, verify the final
   available slot and full-capacity refusal; cancellation frees capacity.
   These rows express attendance intent only.
7. On Today, confirm an activity appears only when the user has an active
   signup for a published, visible activity happening today. Also confirm only
   the creator's own `changes_requested` item creates the review reminder.

Community Activities adds no My Serving item, `ServiceEvent`, serving record,
check-in, waitlist, notification, or Staff Overview content. Do not use it as
the official church-gathering operations model.

**中文**

Community Activities 是独立、次要的社区／团契活动报名模块，不是官方 Church
Gatherings 或服事系统。

1. 确认 `community_events` 已启用。
2. 具有 active primary membership 的合资格成员可保存完整 draft，或提交审核。
   Activity Scope 为必填，并使用 active `ChurchStructureUnit` 保存
   `CommunityActivityAudienceScope` 行；可选 audience note 只是审核背景，不控制
   可见性。
3. 确认 draft 只对主创建者、已关联 co-organizer 及 staff/superuser 可见。只有主创建
   者能管理 co-organizer 并提交 draft；co-organizer 只能在已交付的
   draft／pending-review／changes-requested 边界内编辑。
4. Staff/superuser 使用现有审核 inbox 执行 publish、附注 request changes 或
   cancel/reject；确认创建者修改并重新提交后，`changes_requested` 会回到
   `pending_review`。
5. 发布后，用匹配与不匹配成员核对 Activity Scope 可见性。
6. 测试 signup、cancel 和重新 signup；有容量上限时，核对最后名额、满额拒绝及取消后
   释放名额。这些记录只表示出席意向。
7. 在 Today 中确认：只有当前用户已有效报名、已发布、可见且发生在今天的活动才出现；
   另一个提醒只用于创建者自己的 `changes_requested` 项目。

Community Activities 不会产生 My Serving 项、`ServiceEvent`、服事记录、check-in、
waitlist、通知或 Staff Overview 内容。不要把它当作官方教会聚会运营模型。

## 6. Bible Study V2 setup / 查经 V2 设置

**English**

- Use the active `BibleStudySeries` + `BibleStudyMeeting` path. Do not revive
  retired V1 `BibleStudySession` workflows.
- Configure series and meeting audiences through module-owned audience rows
  that target `ChurchStructureUnit`. Confirm generated or manually prepared
  member-visible meetings have the intended audience rows; zero-row meetings
  fail closed for ordinary users.
- Verify a matching member can see the meeting and a nonmatching member cannot.
  A visible meeting is agenda, not serving.
- Create personal Bible Study serving only by linking
  `BibleStudyMeetingRole.user` to the actual user. That explicit user-linked
  role may appear in Today and My Serving and use the shipped confirmation
  workflow.
- A display-name-only meeting role is meeting-detail fallback only. It must not
  create Today serving action or My Serving state and must never be matched to
  a user by text.

**中文**

- 使用当前的 `BibleStudySeries` + `BibleStudyMeeting` 路径，不要恢复已退役的 V1
  `BibleStudySession` 流程。
- Series／meeting 的受众使用模块自有 audience rows 指向
  `ChurchStructureUnit`。确认已生成或手动准备、需要对成员可见的 meeting 具有预期
  audience rows；零受众行对普通用户必须 fail closed。
- 用匹配和不匹配成员核对 meeting 可见性。可见 meeting 是日程，不是服事。
- 只有把 `BibleStudyMeetingRole.user` 明确关联到真实用户，才会产生个人查经服事；
  该 user-linked role 可进入 Today 和 My Serving，并使用已交付的确认流程。
- 只有 display name 的 meeting role 只是详情 fallback；它不会产生 Today 服事行动
  或 My Serving 状态，也绝不能通过文字匹配推断用户。

## 7. Ministry and My Serving setup / 事工与 My Serving 设置

**English**

- `MinistryTeam` defines the ministry team context.
- `TeamAssignment` schedules a team for a specific event, and
  `TeamAssignmentMember` explicitly assigns a person. Only that explicit member
  row creates team-serving state for the person.
- My Serving is the dedicated personal serving and confirmation workspace. Use
  it to verify pending, today, this-week, later, and management-linked serving
  surfaces as applicable.
- `ChurchStructureMembership` never creates a team assignment or My Serving
  item.
- Active, date-valid lead/coordinator `MinistryTeamRoleAssignment` rows grant
  the shipped exact-team management responsibility. They may expose management
  links or leader attention, but they are long-term responsibility—not personal
  event serving—and must not appear as a personal serving assignment by
  themselves.
- Keep Bible Study serving separate: its explicit personal source is the
  linked-user `BibleStudyMeetingRole.user`, not a `TeamAssignmentMember`.

**中文**

- `MinistryTeam` 定义事工团队上下文。
- `TeamAssignment` 把团队安排到特定事件，`TeamAssignmentMember` 才是对个人的明确
  指派；只有该个人记录会产生团队服事状态。
- My Serving 是个人服事及确认的专用工作区；按实际数据核对待确认、今天、本周、稍后
  及管理入口等已交付界面。
- `ChurchStructureMembership` 永远不会创建团队排班或 My Serving 项。
- Active、日期有效的 lead/coordinator `MinistryTeamRoleAssignment` 授予当前已交付的
  exact-team 管理责任。它可带来管理链接或 leader attention，但它代表长期责任，不是
  个人事件服事，单独存在时不得显示为个人服事指派。
- 查经服事保持独立：其个人明确来源是 linked-user
  `BibleStudyMeetingRole.user`，不是 `TeamAssignmentMember`。

## 8. Today boundary / Today 边界

**English**

Today is the general, low-noise agenda and lightweight action surface. Depending
on enabled modules and the current user's data, it may include:

- today's reading and check-in state;
- visible Church Gatherings today and this week;
- visible Bible Study V2 meetings today and this week;
- the narrow Community Activities reminders described above;
- at most one visible active Important Announcement reminder; and
- personal action items or compact serving notes backed only by an explicit
  `TeamAssignmentMember` or linked-user `BibleStudyMeetingRole.user`.

Today is not a feed, a staff dashboard, or the full serving workspace. Full
serving confirmation and management remain in My Serving or the owning module.

**中文**

Today 是通用、低噪音的日程与轻量行动界面。根据启用模块和当前用户数据，它可包含：

- 今日阅读与 check-in 状态；
- 今天及本周内当前用户可见的 Church Gatherings；
- 今天及本周内当前用户可见的 Bible Study V2 meetings；
- 上述严格限定的 Community Activities 提醒；
- 最多一条当前用户可见且有效的 Important Announcement 提醒；
- 仅由明确 `TeamAssignmentMember` 或 linked-user
  `BibleStudyMeetingRole.user` 支持的个人行动项／简短服事说明。

Today 不是 feed、staff dashboard 或完整服事工作区。完整确认和管理应留在 My
Serving 或所属模块。

## 9. Limited-trial verification checklist / 有限试运行核对清单

Use separate accounts and record evidence without copying sensitive personal
data into this document. 使用不同账号测试，并记录不含敏感个人资料的证据。

### Platform and setup / 平台与设置

- [ ] `python manage.py check` passes. / Django check 通过。
- [ ] `python manage.py makemigrations --check --dry-run` reports no missing
      migrations. / 未发现缺失迁移。
- [ ] `showmigrations` and `migrate --plan` match the target deployment plan;
      any apply action is separately approved. / 迁移状态与目标部署计划一致，任何 apply
      均另行批准。
- [ ] `CMS_ENABLED_MODULES` contains the intended dependency-valid set and its
      surface gates were checked. / 模块集合符合依赖且已核对界面入口控制。
- [ ] A fresh `audit_trial_setup_readiness --verbose --limit 20
      --fail-on-blockers` result was reviewed. / 已复核目标环境的新就绪审计结果。
- [ ] Every warning has an owner, disposition, or accepted trial limitation.
      / 每个 warning 均有负责人、处理决定或明确接受的试运行限制。

### Accounts and audience / 账号与受众

- [ ] Sample staff/superuser can reach the required management surfaces.
      / 示例 staff/superuser 可访问所需管理界面。
- [ ] Sample matching member has the intended active primary membership and can
      see scoped published content. / 示例匹配成员有正确 active primary
      membership 且可见范围内已发布内容。
- [ ] Sample nonmatching member cannot see that scoped content, including by
      direct hidden-detail URL. / 示例不匹配成员无法通过列表或直接隐藏详情 URL 查看。

### Product smoke tests / 产品冒烟测试

- [ ] Announcement: draft, bilingual content, audience, Important, publish
      window, publish/archive, matching/nonmatching visibility, and max-one
      Today reminder pass. / 公告完整冒烟流程通过。
- [ ] Community Activity: draft/submission, review/request changes, published
      scope visibility, signup/cancel/capacity, and narrow Today reminders pass.
      / 社区活动完整冒烟流程通过。
- [ ] Today/My Serving: visible gathering and meeting remain agenda only;
      membership/audience alone creates no serving; explicit team and linked
      Bible Study assignments appear in the correct serving surfaces; a
      display-name-only Bible Study role does not. / Today／My Serving 边界冒烟
      测试通过。

## 10. Known limitations and escalation / 已知限制与升级边界

**English**

- Disabled modules are surface-gated, not route hard-off.
- Production readiness is not claimed. This guide does not certify deployment
  security, backups, monitoring, scale, accessibility, or operational support.
- Setup-readiness warnings must be reviewed before inviting real users, even
  when blocker count is zero.
- Target-environment migration and audit evidence must be recorded separately;
  local evidence is not target-environment proof.
- New integrations, broader shared surfaces, notifications, route hard-off,
  automatic assignments, or cross-module behavior require a separate approved
  slice.

**中文**

- 停用模块只是界面入口控制，不是路由硬关闭。
- 不宣称生产就绪；本文不认证部署安全、备份、监控、规模、无障碍或运营支持。
- 即使 blocker 为零，邀请真实用户前仍必须复核 setup-readiness warnings。
- 目标环境的迁移与审计证据要另行记录；本地证据不能证明目标环境状态。
- 新集成、更广共享界面、通知、路由硬关闭、自动指派或跨模块行为都需要另行批准。

## 11. Do Not Do / 禁止事项

**English**

- Do not create serving from `ChurchStructureMembership`.
- Do not treat audience visibility as assignment.
- Do not use Community Activities for official church-gathering operations.
- Do not use Announcements for signup or event management.
- Do not claim production readiness from this guide, a QA pass, or a
  zero-blocker audit.
- Do not expose this guide to ordinary members.
- Do not infer staff authority, management responsibility, or a personal Bible
  Study role from belonging, audience rows, or display text.
- Do not implement a future integration or product expansion while following
  this operations guide.

**中文**

- 不得从 `ChurchStructureMembership` 创建或推断服事。
- 不得把受众可见性当作指派。
- 不得用 Community Activities 承担官方教会聚会运营。
- 不得用 Announcements 管理报名或活动。
- 不得根据本文、一次 QA 通过或零 blocker 审计宣称生产就绪。
- 不得向普通成员公开本文。
- 不得从归属、audience rows 或显示文字推断 staff 权限、管理责任或个人查经角色。
- 不得借执行本文之机实现未来集成或扩大产品范围。
