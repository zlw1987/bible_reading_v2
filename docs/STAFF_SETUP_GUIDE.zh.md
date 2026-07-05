# 同工设置指南

状态：仅限同工／内部使用。

本指南是有限试运行操作指南，只描述已经交付的行为。它不是生产就绪认证，也不是普通
成员帮助页面。请勿向普通成员公开。本应用内的 `/staff/setup-guide/` 页面沿用其他
`/staff/` 界面的 staff/superuser 权限边界。

## 1. 用途与操作边界

本指南用于准备小规模、有人监督的有限试运行，并核对归属、受众可见性、日程项目与服事
之间的边界。请记录目标环境、操作同工、日期、启用模块、审计结果、已复核警告及冒烟
测试账号。本地已有结果不能代替对实际试运行环境重新检查。

当前背景：

- Community Activities V1 的手动 QA 已由用户确认通过。
- Official Announcements V1 的手动 QA 已在
  `ANNOUNCEMENTS-QA-PASS.1A` 中由用户确认通过。
- 最近记录的设置就绪审计结果为 0 个 blocker、19 个 warning；这只支持有限试运行
  规划。邀请真实用户前，必须复核警告，并对目标数据库重新运行审计。

## 2. 部署、迁移与模块启用

1. 确认试运行环境部署的是预期代码版本及该环境专用设置。
2. 检查迁移状态及计划操作。只有在另行批准的部署流程中才可执行迁移；本指南不授权
   任何会修改数据的命令。
3. 运行 Django 系统检查，并确认模型没有缺失迁移。
4. 检查部署设置中的 `CMS_ENABLED_MODULES`。已交付的注册键为 `reading`、
   `prayers`、`studies`、`events`、`community_events`、`announcements`
   和 `ministry`，默认全部启用。未知键会导致配置校验失败；`ministry` 依赖
   `events`。
5. 对预期启用及刻意停用的模块，分别核对导航、Today 内容、同工入口，以及模块自有的
   Staff Overview／就绪检查内容。

建议运行以下只读或不写入命令：

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py migrate --plan
python manage.py audit_trial_setup_readiness --verbose --limit 20 --fail-on-blockers
```

`audit_trial_setup_readiness` 是只读命令，没有 `--apply` 模式。`--limit`
只限制示例数量，不限制扫描范围。

重要限制：

停用模块目前是界面入口控制，而不是路由硬关闭。它会隐藏已注册导航及部分模块自有
界面／provider，但不会卸载应用、模型、admin 注册或 URL；直接路由仍依赖原有视图
权限和可见性规则。

## 3. 账号、教会结构与受众验证

- 确认至少有一个可用的 staff 或 superuser 账号负责试运行。Staff 权限必须来自现有
  权限边界，绝不能由 `ChurchStructureMembership` 推导。
- 确认 `ChurchStructureUnit` 层级符合预期，且需要用于受众或归属的单位均为 active。
- 确认每位参与试运行的普通成员都有正确的 active primary
  `ChurchStructureMembership`；试运行前必须处理多个 active primary 的冲突。
- 不要创建假的 `Unassigned` 单位。“未分配”表示用户没有阻挡性的 active primary
  membership，也没有 pending membership request；它是一种状态，不是
  `ChurchStructureUnit`。
- Membership 只表示归属。它可为已批准的可见性消费者提供结构上下文，但不会授予
  服事、同工角色、staff 权限、团队排班或查经角色。
- 各模块的 audience row 只控制可见性。受众可见性不代表指派、出席、审批或服事。
- 每个受众限定项目都要用一位匹配成员和一位不匹配成员测试。按当前结构原生匹配规则，
  选择祖先单位会包含符合条件的后代 membership；普通用户遇到零受众行时应 fail
  closed。

## 4. 官方公告设置

Official Announcements 是由 staff 撰写的官方沟通模块，其管理流程只允许
staff/superuser 使用。它不是活动管理、报名或服事模块。

1. 确认 `announcements` 已启用，预期的同工管理入口及登录成员导航已出现。
2. 使用 staff/superuser 创建 draft，并填写中英文标题与正文；检查支持语言下的显示
   和 fallback。
3. 使用现有 audience picker 选择一个或多个 active `ChurchStructureUnit`；不要为了
   公告虚构结构单位。
4. 选择普通优先级或勾选 Important。Important 只使符合条件的公告可成为 Today
   提醒候选，绝不会绕过受众可见性。
5. 设置发布时间窗（`publish_start` 及可选 `publish_end`）并保存草稿；确认未来开始
   和已过期公告对普通成员隐藏。
6. 通过已交付的同工操作发布；用匹配成员核对列表与详情，再用不匹配成员确认不可见，
   且直接访问隐藏详情返回 404。
7. 归档公告并确认成员列表／详情不再显示；归档会保留 audience rows。
8. 对有效的 Important 公告，确认 Today 最多显示一条最新且当前用户可见的提醒，并且
   只显示本地化标题／详情链接；普通公告不进入 Today。

Announcements 不会增加 Staff Overview 内容、My Serving 项、服事状态、通知、
`ServiceEvent`、Community Activities、报名、出席或
approval/request-changes 流程。

## 5. 社区活动设置

Community Activities 是独立、次要的社区／团契活动报名模块。它不是
`ServiceEvent`、官方 Church Gatherings、My Serving 或服事系统。

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

Community Activities 不会产生 My Serving 项、`ServiceEvent`、Church Gathering、
服事记录、check-in、waitlist、通知或 Staff Overview 内容。不要把它当作官方教会
聚会运营模型。

## 6. 查经 V2 设置

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

## 7. 事工与 My Serving 设置

- `MinistryTeam` 定义事工团队上下文。
- `TeamAssignment` 把团队安排到特定事件，`TeamAssignmentMember` 才是对个人的明确
  指派；只有该个人记录会产生团队服事状态。
- My Serving 是个人服事及确认的专用工作区；按实际数据核对待确认、今天、本周、稍后
  及管理入口等已交付界面。My Serving 只显示明确服事。
- `ChurchStructureMembership` 永远不会创建团队排班或 My Serving 项。
- Active、日期有效的 lead/coordinator `MinistryTeamRoleAssignment` 授予当前已交付的
  exact-team 管理责任。它可带来管理链接或 leader attention，但它代表长期责任，不是
  个人事件服事，单独存在时不得显示为个人服事指派。
- 查经服事保持独立：其个人明确来源是 linked-user
  `BibleStudyMeetingRole.user`，不是 `TeamAssignmentMember`。

## 8. Today 边界

Today 是通用、低噪音的日程与轻量行动界面。根据启用模块和当前用户数据，它可包含：

- 今日阅读与 check-in 状态；
- 今天及本周内当前用户可见的 Church Gatherings；
- 今天及本周内当前用户可见的 Bible Study V2 meetings；
- 上述严格限定的 Community Activities 提醒；
- 最多一条当前用户可见且有效的 Important Announcement 提醒；
- 仅由明确 `TeamAssignmentMember` 或 linked-user
  `BibleStudyMeetingRole.user` 支持的个人行动项／简短服事说明。

Today 是低噪音日程，不是 feed、staff dashboard 或完整服事工作区。完整确认和管理应
留在 My Serving 或所属模块。

## 9. 有限试运行核对清单

使用不同账号测试，并记录不含敏感个人资料的证据。

### 平台与设置

- [ ] `python manage.py check` 通过。
- [ ] `python manage.py makemigrations --check --dry-run` 未发现缺失迁移。
- [ ] `showmigrations` 和 `migrate --plan` 符合目标部署计划；任何 apply 操作都已
  另行批准。
- [ ] `CMS_ENABLED_MODULES` 包含预期、依赖有效的模块集合，并已核对其界面入口控制。
- [ ] 已复核目标环境新运行的 `audit_trial_setup_readiness --verbose --limit 20
  --fail-on-blockers` 结果。
- [ ] 每个 warning 均有负责人、处理决定或明确接受的试运行限制。

### 账号与受众

- [ ] 示例 staff/superuser 可访问所需管理界面。
- [ ] 示例匹配成员有正确的 active primary membership，且可见范围内已发布内容。
- [ ] 示例不匹配成员无法通过列表或直接隐藏详情 URL 查看该范围内容。

### 产品冒烟测试

- [ ] 公告：draft、双语内容、受众、Important、发布时间窗、发布／归档、匹配／不匹配
  可见性，以及 Today 最多一条提醒均通过。
- [ ] 社区活动：draft／提交、审核／request changes、发布后范围可见性、
  signup／cancel／容量，以及严格限定的 Today 提醒均通过。
- [ ] Today／My Serving：可见 gathering 和 meeting 仍只是日程；membership／audience
  本身不产生服事；明确团队和 linked Bible Study 指派进入正确服事界面；只有 display
  name 的 Bible Study role 不进入个人服事界面。

## 10. 已知限制与升级边界

- 停用模块只是界面入口控制，不是路由硬关闭。
- 不宣称生产就绪；本指南不认证部署安全、备份、监控、规模、无障碍或运营支持。
- 即使 blocker 为零，邀请真实用户前仍必须复核 setup-readiness warnings。
- 目标环境的迁移与审计证据要另行记录；本地证据不能证明目标环境状态。
- 新集成、更广共享界面、通知、路由硬关闭、自动指派或跨模块行为都需要另行批准。

## 11. 禁止事项

- 不得从 `ChurchStructureMembership` 创建或推断服事。
- 不得把受众可见性当作指派或服事。
- 不得用 Community Activities 承担官方教会聚会运营。
- 不得用 Announcements 管理活动、报名或服事。
- 不得根据本指南、一次 QA 通过或零 blocker 审计宣称生产就绪。
- 不得向普通成员公开本指南。
- 不得从归属、audience rows 或显示文字推断 staff 权限、管理责任或个人查经角色。
- 不得借执行本指南之机实现未来集成或扩大产品范围。
