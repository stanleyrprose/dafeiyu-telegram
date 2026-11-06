# 大肥鱼 Telegram — 单用户 SIWC 与自治生活助手

基于 [whyever77/dafeiyu-astrbot](https://github.com/whyever77/dafeiyu-astrbot) 的角色设定及记忆/生活节律设计整理的精简自托管版本。原项目按 MIT 许可证授权，详见 [LICENSE](LICENSE)。

此版本使用 **AstrBot v4.29.4、原生 Telegram 长轮询、ChatGPT SIWC OAuth（Responses API）**。在稳定的单 Owner 私聊基线上，新功能分支增加了真实提醒/待办、保守自动记忆、只读公开网页检索，以及基于真实记录的主动关怀。**仍不依赖 NapCat、QQ、B 站、商业 API Key、独立网关、设备控制或 Function Tool。**

## 目录

- `plugin/astrbot_plugin_dafeiyu_siwc/`：Owner 私聊平台适配 + SIWC Provider。
- `plugin/astrbot_plugin_dafeiyu_local_life/`：人格提示、显式/自动记忆、本地 SQLite 提醒与待办、只读信息检索、事实驱动的低频节律。
- `scripts/probe_siwc.py`：仅在 Mac 宿主机进行的 SIWC 授权资格探针。
- `scripts/setup_telegram_credentials.py`：在 SSH 交互终端不回显输入 Telegram Token。
- `scripts/provision_telegram_runtime.py`：把本机保存的凭据写入 Git 忽略的 AstrBot 私有运行配置。
- `deploy/telegram/compose.yaml`：单容器 Docker Compose。
- `deploy/telegram/README.md`：完整部署、恢复和回滚说明。

## P1 + P2 Telegram 指令（功能分支，验收/部署后生效）

| 意图 | 示例 |
|---|---|
| 明确时间的提醒 | /remind 明天上午9点提醒我开会 |
| 相对时间的提醒 | /remind 10分钟后提醒我喝水 |
| 查询/取消/重试提醒 | /reminders、/cancel 3、/retry 3（仅 unknown/failed） |
| 新增/查看/完成待办 | /todo 阅读30分钟、/todos、/done 2 |
| 长期记忆 | /remember 我喜欢JRPG、/memories、/forget 1 |
| 自动记忆开关 | /autoremember on 或 off |
| 公共网页搜索 | /search 缅甸5G频谱公告 |
| 公共页面只读摘录 | /read https://example.org/article |
| 根据搜索摘要研究 | /research 2026年5G FWA的新趋势 |
| 主动关怀开关/预览 | /nudge on、/nudge off、/nudge now |

提醒使用容器环境变量 DAFEIYU_TZ，未配置时为 **Asia/Shanghai**；仰光与北京时间相差 90 分钟。若需要仰光时间，在私有配置中设定 DAFEIYU_TZ=Asia/Yangon，经过独立部署授权后重启。每日关怀时区单独由 DAFEIYU_RHYTHM_TZ 决定。

**确认才生效**：普通聊天里模型说“我会提醒你”不等于任务已经创建；必须看到提醒编号。无明确时间的自然语言提醒会要求补充时间。

自动记忆默认启用保守提取，最多保留24条本地笔记，每轮注入最近16条。用户可以 /memories 审核、/forget 删除。

搜索词会提交给第三方公共搜索引擎；请勿提交客户机密或个人敏感信息。/read 只读取公开 HTTPS 文字网页，限制下载大小并拒绝内网/私有地址，**不是浏览器自动化**。/research 基于检索摘要回答，不能伪称逐篇阅读全文。

提醒自动投递遵循 at-most-once 原则；结果不确定时为 unknown，不会默默重发。须先人工确认，再用 /retry，避免重复通知。

## v3 新功能（当前开发分支，尚未验收或部署）

- **LivingMemory + 本地 Embedding**：官方 LivingMemory 2.9.1 固定版本，连接 Mac 上已有的 Ollama `bge-m3`（1024维）。保留手动 `/remember`，启用插件后使用 `/lmem status`、`/lmem search 关键词`，原来的自动提取停用，避免重复记忆。
- **主动聊天**：`/proactive on`、`/proactive off`、`/proactive status`、`/proactive reset`。本地 23:00—08:00 静默、4 小时内刚聊过则不主动联系、上一条未回应则暂停、每天最多一次；主动关怀和探索共用日额度。
- **X / Reddit 自主探索**：`/explore add x AI agents`、`/explore add reddit 5G RAN`、`/explore on`、`/explore list`、`/explore now`、`/explore remove 1`、`/explore off`。启用后每日13:00查询公开搜索索引中的原站帖子链接，仅分享新链接，不收集登录 Cookie、不冒充平台 API 实时数据。
- **真实日程感知**：`/event 2026-11-10 09:00 60 项目会议` 创建，`/moveevent 3 2026-11-10 10:00 60` 改期，`/eventcancel 3` 取消，`/agenda` 读取本地真实日程与任务。关联提醒与日程联动，模型每轮获得可核验的主人日程和本 Bot Cron。

新增功能默认不擅自打开主动搜索和主动聊天；需要主人明确发送 `/explore on` 和 `/proactive on`。第三方官方 API 登录/授权不属于默认公开索引模式。外部日历（Google、Apple、Outlook）不会被假设已连接。

实施约束与验收标准：[v3 GOAL](docs/GOAL_LIVINGMEMORY_AUTONOMY.md)。**GitHub 开发分支的功能不可当作已上线生产能力。**

## 安全边界

Owner 数字 ID 必须与 Telegram 私聊的发送者和聊天 ID 同时匹配；群聊及非 Owner 消息在进入 AstrBot 消息转换前被阻止。默认禁用多模态和函数工具；SIWC 只使用当前账号实际授权的模型，无 API Key 降级。

凭据与本地部署环境文件位于 Git 忽略的 private/ 目录；运行数据库与笔记位于独立 Docker Volume（容器内 /AstrBot/data），不进入 Git。不要将本机 `credentials.json`、Bot Token、聊天历史或运行日志提交到公共仓库。

## 安装与验收

按 [Mac mini 部署说明](deploy/telegram/README.md) 操作。首次启动容器生成默认配置后需停止容器、运行离线配置脚本、再启动。对外访问仅使用 Telegram，WebUI 端口只绑定 Mac 的 `127.0.0.1:6185`。

开发和验收依据 [AGENTS.md](AGENTS.md)、[docs/DEV-WORKFLOW-v1.0.md](docs/DEV-WORKFLOW-v1.0.md) 及 [P1+P2 执行目标](docs/GOAL_P1_P2.md)。四项新增能力仍需单独完成受影响路径验收，不能将已验证的旧版聊天往返视为新增功能通过。旧版 SQLite 故障与迁移证据见 [SQLite 诊断记录](docs/SQLITE_PERSISTENCE_CHECKPOINT.md)。
