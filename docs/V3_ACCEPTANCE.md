# 大肥鱼 v3：Phase V 集中验收证据（2026-11-06）

## 隔离测试（已执行）

- 纯 Python 项目测试：65 项，其中 43 通过、22 项固定 AstrBot 环境专用测试按预期 skipped，无失败。
- 固定 AstrBot v4.29.4 v3 镜像在 Mac mini 构建成功。原版 SIWC/Owner + v2 + 新增 v3 AstrBot 回归 22/22 通过，覆盖日程改期/取消与提醒联动、主动联系每日限制、非 Owner 拒绝、敏感待办过滤、X/Reddit 推送等。
- 真实公开 X/Reddit 搜索索引：X 返回 2 条、Reddit 返回 4 条；全部为 HTTPS 原站链接。不使用账号登录、Cookie、平台受限 API。
- Mac Ollama 已安装 bge-m3:latest；容器到 host.docker.internal:11434 可访问，HTTP 200；真实 OpenAI-compatible embedding API 返回 1024 维、1024 项非零。
- 官方 LivingMemory 2.9.1 固定 revision 1c6a471c9af9ae45a4ccb3a8cec5695c917de50b 安装于隔离 Volume `dafeiyu_v3_acceptance`，不含任何生产凭据；模块导入成功，session 隔离配置已写入。
- LivingMemory 官方记忆引擎及作用域测试：72/72 通过。
- 真实向量+真实 FAISS+官方 MemoryEngine：独立临时数据库写入成功，语义检索到 1 条记忆，其他 Telegram session 的召回结果为 0。测试脚本：`scripts/livingmemory_semantic_smoke.py`。
- 以上所有测试均未接入生产 Telegram、SIWC Token 或对生产 Docker Volume 写入数据。

## CI / Release 门禁

- 确保最终修复的开发分支已重新通过受影响测试，并 Push 无 CI。
- 通过 Mac `gh` 创建面向 main 的 PR，GitHub CI success 才 Merge。
- 生产前记录 v2 发布分支/Commit/镜像，停止仅 dafeiyu-telegram 容器，备份 core SQLite、life-state SQLite、notes、LivingMemory 插件数据和含凭据的 `cmd_config.json`（私有 0600，不打印）。
- 使用新版本镜像，保持原 Docker Volume；安装固定版官方插件，配置本地 Ollama Provider；不改变 Mac 11434 服务的公网绑定。
- 启动同一个 Bot 后核查日志、平台轮询、SQLite 完整性、Cron 和 LivingMemory 初始化；通过用户 Telegram /agenda、/lmem status 以及少量新命令进行真实验收。
- 若生产启动或插件初始化失败，立刻停本 Bot、禁用第三方插件并恢复原 v2 代码/Compose 与私有配置备份；绝不删除 Docker Volume 或用户记忆。

## 尚需用户侧的证明

- Telegram App 对 v3 新功能的可见交互回复必须由本人确认；后台接受发送不等于手机已经看到。
- 自动主动聊天默认关闭；X/Reddit 定时探索默认关闭。只有本人通过 `/proactive on` 和 `/explore on` 才开始主动推送。
