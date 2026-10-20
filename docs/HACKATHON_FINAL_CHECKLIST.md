# 十月黑客松维护与最终验收清单

项目：MoonBit Parquet 行组统计与选择性读取。
2026-10-20，参赛者提供的组委会邮件确认**报名初审通过**；不公开私人邮件、姓名或收款资料。
最终验收仍独立评估完成度、质量、合规和生态相关性，初审不等于最终验收或款项到账。

## 当前工程材料

- [x] [公开 Fork](https://github.com/sgy1023-crt/parquet)，默认分支 `feat/row-group-statistics`，保留上游历史及 Apache-2.0 来源。
- [x] [README](../README.md)、[申报说明](HACKATHON_SUBMISSION.md)、[API](ROW_GROUP_API.md)、[消费者](ROW_GROUP_EXAMPLE.md)、[复现步骤](DEPENDENCIES.md)齐全。
- [x] [已验证完整 CI](https://github.com/sgy1023-crt/parquet/actions/runs/39370996665)：四后端各 71/71，另含 macOS native；32 fixture；解码计数 8/2/0/4/0；DuckDB 互操作与 playground 通过。
- [x] [独立公开克隆记录](REMOTE_REPLAY.json)及[验证边界](VALIDATION.md)可查。完整 Bytes 仍加载入内存，未声称速度、内存或 I/O 收益。
- [x] 工具链固定在 [`.moonbit-version`](../.moonbit-version)，依赖不随意升级；上游截至本次检查仍为 `44d4dc9`、v0.2.2。
- [ ] 以 10/28 实际运行的最终验收报告确认当时的 Commit SHA、各后端、命令与结果。
- [ ] 参赛者按最终公告自行提交验收材料并处理收款手续。

## 2026-10-20 实际维护验证

验证代码提交：`b75a3f171b997eebb6dcc5a282b3d3b067c418be`。

| 真实运行 | 结果 |
|---|---|
| [完整 push CI](https://github.com/sgy1023-crt/parquet/actions/runs/39401173799) | 原有完整检查和新增日期单测通过；健康/验收分支按路由跳过 |
| [手动轻量健康](https://github.com/sgy1023-crt/parquet/actions/runs/39401175601) | 只读核查、JS 检查和 71 项测试通过；上游和官方规则源无新变动 |
| [手动完整验收演练](https://github.com/sgy1023-crt/parquet/actions/runs/39401181367) | 新检出环境全部 17 项检查通过；四后端各 71/71、32 fixture、两个消费者、四后端 8/2/0/4/0 解码计数；报告含实际 SHA 和命令 |

首次手动运行暴露了维护脚本的 GitHub API 末尾斜杠 404，已直接修正规范地址，失败记录仍保留，未增加权限或掩盖错误。库代码与 API 未改。
工作流在默认分支上为 active，定时配置已发布；首次日常计划为 10/21。以上证明实际手动路径可运行，不冒称未来 schedule 已经发生。
10/28 的报告将在当日重新运行后产生，不能用本次演练替代。

## 实际自动调度

使用现有 [CI 工作流](https://github.com/sgy1023-crt/parquet/actions/workflows/ci.yml)，不是 Codex 会话后台运行。
计划每天 **09:17 北京时间**（UTC `01:17`），GitHub 调度可能延迟，不能保证精确启动时刻。

| 北京日期 / 触发方式 | 实际路径 |
|---|---|
| 10/20–10/31 普通每日检查 | 仓库公开性、默认分支、祖先/材料、最近 push CI、上游/公开规则快照；仅 JS 检查与 71 项测试 |
| 10/25 | 复用原完整 CI 矩阵，并记录上游与规则；不重复每日 JS 测试 |
| 10/28 | fresh checkout 安装固定工具和新依赖，运行完整 `verify_delivery.py`；不再同时启动原完整矩阵 |
| 手动 `mode=full` | 当场完整验收，不受赛事日期限制 |
| 北京时间 2026-11-01 00:00 起的 schedule | 仅日期门禁执行，安装、健康扫描和测试任务全部跳过；未来年份也不重新启动 |

日期门禁有自动测试，覆盖 UTC 10/31 15:59:59 与 16:00:00、10/25、10/28、跨年及手动触发。
只读任务仅使用 `contents: read`，需要读取 CI 状态的任务另有 `actions: read`；不提交代码、合并、发布包、建 PR、发消息或填表。
上游和规则变化只记录待分析，不自动判定兼容或合并；私人通知无法被此监控覆盖。

手动触发（本地不用具备 MoonBit 环境）：

```sh
# 完整验收，也是在 10/28 调度迟延时的兜底
gh workflow run ci.yml --repo sgy1023-crt/parquet --ref feat/row-group-statistics -f mode=full

# 单独验证每日健康路径
gh workflow run ci.yml --repo sgy1023-crt/parquet --ref feat/row-group-statistics -f mode=health

gh run list --repo sgy1023-crt/parquet --workflow ci.yml --limit 5
```

完整报告位于对应运行的 Job Summary 和 `hackathon-final-acceptance` artifact；含实际 SHA、执行命令、通过/失败数、限制和工程检查结论。
失败保留非零状态及收据；使用 GitHub Actions 自带通知，用户自行确认账号通知设置。Artifacts 保留 90 天，重要验收报告应自行下载保存。

**彻底关闭定时**：删除 `.github/workflows/ci.yml` 的 `on.schedule` 两行并正常提交，保留 push 和手动验收。
`gh workflow disable ci.yml --repo sgy1023-crt/parquet` 会关闭整个 CI（包括手动与 push），仅在确实不再需要整个工作流时使用。
门禁不会自动修改工作流，因此截止后仍可能有一个很短的门禁 Job 启动。

## 官方规则与人工手续

依据[官网](https://moonbitlang.github.io/Hackathon2026/)及固定[官方源码](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx)：

| 分类 | 核查结果 |
|---|---|
| 官网明文 | 允许维护他人项目，须有本期实质贡献、公开记录、说明、示例、测试、许可与来源；群昵称用 GitHub ID。见 [L123](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx#L123)、[L203](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx#L203)、[L223](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx#L223)。 |
| 未发现硬性规定 | 必须新增分支、上游 PR/合并、每日或固定次数提交。保留记录不等于必须新增这些流程。 |
| 截止 | 明示 2026-10-31，未明示时区及准确时刻；北京时间 23:59 不能当作已确认规则。 |
| 支持 | [L169](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx#L169)：150 元对应申报通过，350 元对应完成且通过本期审核；维护类别适用细则、具体到账日和银行卡手续未明确，不能保证到账。 |
| 季度 | [L98](https://github.com/moonbitlang/Hackathon2026/blob/a879c208b261ca500f65707d42504d06572fa9b0/src/App.tsx#L98)：社区维护项目主动报名；本次报名是否覆盖季度入口未明确。 |
| 私有渠道待人工查 | [正式章程](https://bxup9uklfcb.feishu.cn/wiki/Dx4Bwd6D1i3GfHkajQCcF7SznEd)本轮无法读取；最终验收表、准确截止时间、季度入口、收款和昵称细节请查群/飞书公告及自己的银行流水。 |

项目安排（不是赛事硬性规定）：10/29–10/30 冻结功能，仅修阻断问题、下载报告并整理材料，不依赖 10/31 最后数小时。
若私有公告出现新增要求，由参赛者决定并提供原文后处理；自动监控不联系任何人或代替提交。
