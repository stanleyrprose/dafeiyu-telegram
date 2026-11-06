# P1+P2 集中验收证据与发布门禁

## 已执行：Mac mini 隔离验收

- 目标分支 feat/dafeiyu-p1-p2；固定 AstrBot v4.29.4、ddgs==9.16.1。
- 本地 CI 最终 42 项：27 通过、15 条 AstrBot 专用测试明确 skipped；这 15 条已在隔离固定版本容器内完成原版 8/8 和新增 7/7 的独立验收。
- v2 单容器镜像构建成功；构建上下文 182.3KB，Docker 白名单排除 private、运行数据库、日志。
- 隔离镜像成功导入 LocalLife 插件和 ddgs 库；未使用生产 Token 或 OAuth。
- 原有 v1.3 的 Owner / SIWC 针对性回归 8/8 通过。
- 新增 AstrBot 插件运行时回归 7/7 通过，涉及待办、明确提醒、仅一次投递、Owner 门禁、自动记忆、Cron、主动关怀。
- 公共搜索：实际返回 3 条 HTTPS 结果、标题非空。公开 HTTPS 页面：example.com 返回非空正文。无生产凭据。
- SQLite 临时记录及独立备份的测试没有接触生产 Volume、聊天历史或凭据。

## 发布门禁

1. 对最终代码重跑相关单测、静态检查，并把修复 Commit+Push。
2. GitHub PR → CI success → Merge，必须无冲突；CI 的 skipped 与本地容器运行时测试分开记录。
3. 部署前在原生产目录运行 scripts/backup_sqlite_db.py，快照包括核心 SQLite、生活助手 SQLite（如果存在）及 notes.json。
4. 记录生产当前 Git 分支/Commit；仅停止 dafeiyu-telegram 容器，然后切换生产工作树到合并后的 main，构建、启动 v2。
5. 验证容器状态、WebUI、插件加载、数据库记录、Owner 私聊新命令；定时提醒跨一个分钟窗口确认发送。
6. 若有故障：停止本 Bot、切回原 Git 分支及旧 Compose/镜像，继续使用同一 Volume，不执行 down -v、不删除数据。新的 state.sqlite3 保留以免数据丢失。

## 技术边界

- ddgs 公共搜索可能被限流或区域网络阻断；失败时不得编造结果。
- /research 仅基于搜索摘要，不能冒充全文浏览。/read 只读公开 HTTPS 文字网页。
- 自动记忆保存用户原话的低敏感证据；/autoremember off 可以关闭，/forget 删除。
- Telegram 适配器接受发送与手机端真正看见消息是两种不同验收证据。unknown 提醒不自动重复发送。
- 不执行手机控制、网站写入、购物、付款或向非 Owner 发送消息。
