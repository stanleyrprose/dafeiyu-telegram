# 大肥鱼 v3 — LivingMemory、主动联系、X/Reddit 探索与日程感知

## 当前授权与成功标准

在已上线 v2 的 Telegram 单 Owner + SIWC + AstrBot v4.29.4 + 单容器上实现下列四项功能；不修改原 QQ/NapCat，不破坏现有数据库和已保存的 `notes.json`。用户本轮授权实现，没有额外授权第三方账号登录、付费 API 或生产部署。

1. **LivingMemory + Embedding**：使用官方 LivingMemory 2.9.1，源固定到 Git commit 1c6a471c9af9ae45a4ccb3a8cec5695c917de50b；embedding 为 Mac 既有本地 Ollama `bge-m3:latest`，1024维，经 AstrBot 的 OpenAI-compatible Embedding Provider。插件与数据位于 Docker Volume，并保持其独立 AGPL 许可。`/lmem status` 和 `/lmem search` 能返回真实结果才算验收；保留 `/remember` 原本手动笔记，LivingMemory 激活时停止旧的自动摘录，避免双写。
2. **主动联系和生活节律**：通过 `/proactive on/off/status/reset` 显式启用；当地时间 23:00—08:00 不发，最近4小时内有互动不发，前次未回应不发；每日最多一次，分享、探索与旧每日关怀共享同一联系额度。未成功发送/超时保留未知状态，不自动重复。
3. **自主公开社区探索**：`/explore add x 关键词`、`/explore add reddit 关键词`、`/explore on/off/list/now/remove`；每天13:00在本地时区读取第三方搜索索引中公开的 X/Reddit 链接，只接受原站帖子 URL，保存 SHA256 去重约48小时；发现的新帖子少量推送 Telegram。严格区分公开索引与官方实时平台 API，不使用账号 Cookie、模拟登录、无授权 API 或 Reddit 未许可抓取。官方 API 深度接入需要用户在平台开发者控制台额外授权。
4. **日程感知与调度**：`/event YYYY-MM-DD HH:MM 时长分钟 事项` 创建带提醒的日程，`/moveevent ID 日期 时间 分钟` 联动改期，`/eventcancel ID` 联动取消，`/agenda` 查询。与现有 `/remind`、`/todo`、本机器人 Cron 一起注入每轮 LLM 上下文；只读真正存在的记录，其他会话 Cron、外部 Google/Apple 日历不声称已同步。

## 架构和边界

- 继续只用一个 AstrBot 容器、既有 SQLite `state.sqlite3` 与 Docker Volume，不新增第二个调度器或外部向量数据库。
- LivingMemory 独立维护索引与备份；官方插件由独立安装脚本从不可变 commit 获取，不把 AGPL 源码复制进 MIT 应用仓库。启用前必须检验 Mac 容器能安全访问 `host.docker.internal:11434/v1`。不得为此将 Ollama 公开暴露到互联网。
- 自动探索只处理用户明确追踪的公开主题；首次 `/explore on` 可初始化两个非敏感示例主题，绝不将私密对话直接发送给第三方搜索。
- 不提供 X/Reddit 登录、发帖、点赞、评论、私信、网站写操作、社交账号自动创建、验证码收集、付费 API 承诺或规避官方访问限制。
- 主动消息和 Telegram Bot 的提交发送结果不能证明用户手机已阅读；at-most-once 避免未知状态下刷屏。
- 日程只针对本 Bot 本地记录，不等同于用户手机/Google/Outlook 的完整日历。

## 开发 / 验收 / 发布阶段

- Phase D：新分支 `feat/dafeiyu-livingmemory-autonomy`，完整开发，阅读/静态检查后可多 Commit 合并 Push；无测试、PR、CI、Merge 或生产部署。
- Phase V：开发完整且用户批准后，集中运行纯 Python 测试、受影响 AstrBot 插件隔离测试、官方 LivingMemory 初始化与真实 bge-m3 向量测试、公开索引检索、安全与回滚验证。
- Phase R：用户授权发布后，再使用 Mac `gh` 创建 PR，检查 CI、Merge；生产部署需另行授权并备份、回滚与用户 Telegram 收发证据。

## 验收证据

需要保留检查结果：plugin pin 与完整性、Embedding 1024维且非空、LivingMemory 私聊召回、Cron 每日上限与免打扰、探索 URL 校验与48h去重、日程/提醒跨重启一致性、Owner 门禁、外部查询不含私人信息、原版聊天回归。
