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
- [x] [10/28 当日完整工程验收](https://github.com/sgy1023-crt/parquet/actions/runs/40641043157)已通过，实测 SHA、各后端、命令、结果与限制见下文；不代表组委会终审通过。
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

## 2026-10-21 每日核查

截至北京时间 13:39，GitHub API 没有任何 `event=schedule` 记录，不能认定今天 09:17 的定时检查已执行。
已[手动补跑健康检查](https://github.com/sgy1023-crt/parquet/actions/runs/39550814464)：JS 71/71、编译检查通过，公开性、默认分支、上游与官方规则快照均正常。
13:42 显式重新启用 CI，API 确认 `state=active`；这不证明原生定时已恢复。当前公开配置符合默认分支与启用要求，具体未触发原因尚未确认。
[GitHub 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)允许定时延迟或丢弃；10/25、10/28 仍须查实际运行记录，缺失时使用下面的手动命令兜底。
库代码、依赖版本与定时时刻未改，不以手动运行冒充自动触发。

## 2026-10-25 中期复核

10/21–10/24 已连续出现四次成功的原生 `schedule` 运行，例如 [10/21](https://github.com/sgy1023-crt/parquet/actions/runs/39552990085)和 [10/24](https://github.com/sgy1023-crt/parquet/actions/runs/40068083092)。这补充了 10/21 午间检查之后的实际调度证据；定时启动仍有延迟。

本次开始检查时尚无 10/25 定时记录，已使用现有 `mode=full` [手动完整复核](https://github.com/sgy1023-crt/parquet/actions/runs/40166099480)，不冒充自动触发，也不替代 10/28 复核。
实测代码提交为 `d39115500fb1556d77c4121ba331b2bae338391c`，全新检出环境通过全部 17 项检查：四后端各 71/71、全目标检查与构建、格式与公开接口一致性、32 个 fixture 的逐字节重放，以及两个消费者示例。
四后端的实际解码计数均为 full=8、selected=2、empty=0、ordered=4、invalid=0；INT32 示例匹配 2 行，超出浮点精确范围的 INT64 示例匹配 3 行。未测量速度、内存或 I/O 收益。
报告和原始命令收据见该次运行的 `hackathon-final-acceptance` artifact；此 Job 名仅表示工程检查，最终赛事验收仍由组委会确认。

README、使用示例、API 边界、来源与许可材料已复核；`LICENSE` 与上游基线一致。上游仍为 `44d4dc9` / v0.2.2，已知 PR #3 未变化，未发现新增公开安全公告。库代码、公开 API 与依赖均未改。

官网规则源与先前快照一致，仍明示 10/31；尚未发现必须新建分支、提交上游 PR 或获得合并的新规定。[10/21 的普通参与者留言](https://github.com/moonbitlang/Hackathon2026/issues/1#issuecomment-6314073182)称章程第八章有 10/24 日期，但当前线程没有官方答复，不能据此认定赛事改期。飞书章程本次仍无法读取，需参赛者尽快人工核对最新群公告中的截止日期、时区及最终验收入口。

## 2026-10-28 完整工程验收报告

本次开始检查时尚无 10/28 原生定时记录，使用既有 `workflow_dispatch` / `mode=full` [实际运行](https://github.com/sgy1023-crt/parquet/actions/runs/40641043157)完成复核。不是用此前结果代替当日执行。
**实测代码与复现基线：`4d01e5bc469abce6b85fc6bb0a695909f9c77cb6`。** 后续本清单更新只追加文档，不改变该实现；复现时可先 `git checkout --detach 4d01e5bc469abce6b85fc6bb0a695909f9c77cb6`，再按 README 和 DEPENDENCIES.md 安装与执行。

运行日志确认使用全新 Ubuntu 24.04 Runner，在空工作目录初始化 Git 并检出该提交，重新安装固定工具链及下载依赖。实测 `moon` / `moonrun` 为 `0.1.20261012`、`moonc` 为 `0.10.15+943464bfa`；Python 3.13.5、Node.js 24、DuckDB 1.4.4 与固定 fixture 工具按现有工作流安装。

| 后端（本次 Ubuntu 环境） | 单测通过 / 总数 | 失败 | full / selected / empty / ordered / invalid 解码计数 |
|---|---|---|---|
| JS | 71 / 71 | 0 | 8 / 2 / 0 / 4 / 0 |
| wasm | 71 / 71 | 0 | 8 / 2 / 0 / 4 / 0 |
| wasm-gc | 71 / 71 | 0 | 8 / 2 / 0 / 4 / 0 |
| native | 71 / 71 | 0 | 8 / 2 / 0 / 4 / 0 |

全部 **17/17 项检查通过、0 项失败或超时**，另含定向库测试 25/25（属于上述 71 项）、格式检查、生成接口无变化、全目标检查和构建（警告视为错误）。
32 个独立 fixture 及 manifest 逐字节重放一致，其中 16 个有效文件、16 个故意负例。消费者 `i32 >= 102` 选择组 `[2]`、解码 4 行、匹配 2 行；`i64 >= 9007199254740995` 匹配 3 行并保持整数精确性。

实际完整入口：

```sh
python scripts/prepare_dependency_cache.py --toolchain "$HOME/.moon"
python scripts/verify_delivery.py --toolchain "$HOME/.moon" --duckdb "$GITHUB_WORKSPACE/.tools/duckdb"
```

`hackathon-final-acceptance` artifact 中的 `hackathon-acceptance.json` 记录上述 SHA、运行链接、全部 17 条实际子命令、退出码与测试数量；`runs/` 保留原始输出，`decode-work-*/` 保留四后端测量证据。每个子检查仍有 60 秒硬超时。上述路径是本次 CI 环境；本地路径设置见 DEPENDENCIES.md。

已复核 README、API 与消费者文档、Apache-2.0 许可和来源，许可与上游基线一致。上游仍为 `44d4dc9` / v0.2.2、已知 PR #3 无变化，官方规则快照未变，未发现新增分支、上游 PR 或合并的硬性要求。私人群公告、验收表与截止时间口径未确认，不能以公开检查替代。

**工程结论：现有实现与可复现材料具备提交最终验收的条件，未发现阻断性缺陷。** 本轮未修改库、公开 API、依赖或工作流；10/29–10/30 按计划冻结功能，仅处理阻断问题与人工提交材料。
已知限制保持不变：输入仍为完整 Bytes；仅保守解释支持范围内的 INT32/INT64 统计；没有测得速度、峰值内存或 I/O 收益。本次工程通过不等于组委会终审或奖金到账，也没有代替参赛者提交表单或联系他人。

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
