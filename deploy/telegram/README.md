# 大肥鱼 Telegram + SIWC｜Mac mini 部署与恢复（v1.3）

> **当前阶段：开发代码已编写，尚未运行受影响路径测试、Docker、Telegram 端到端验证或部署。**  
> 上游大肥鱼来源：whyever77/dafeiyu-astrbot v2.11.1（MIT）；AstrBot 目标：v4.29.4 / 6133541。不得复制原 QQ 运行目录。

## 实际结构

- `scripts/probe_siwc.py`：宿主机首次授权/重新授权 CLI，手机 Termux 通过 SSH 本地端口转发。已由用户报告 M0-B 成功，模型 gpt-6.1-sol。
- `plugin/astrbot_plugin_dafeiyu_siwc/`：原生 Telegram 适配器薄包装 + SIWC Provider，拒绝非主人、群聊、非文本请求。
- `plugin/astrbot_plugin_dafeiyu_local_life/`：主人显式记忆、人格文本注入、一条每日主动问候。
- `persona/大肥鱼-Telegram.md`：精简版人设，移除旧 QQ/B 站/手机/语音工具承诺。
- `deploy/telegram/compose.yaml`：一个固定 v4.29.4 AstrBot 容器，未启用 NapCat 或四个旧内核补丁。
- `private/oauth/`：宿主机私有可写目录，包含 OAuth 授权文件，**禁止提交或发送**。
- `runtime/astrbot/data/`：全新的 AstrBot 会话/插件数据目录，**禁止混入旧 QQ 数据**。

## 通过手机 Termux → SSH 安全配置 Telegram 凭据

在**已经连接 Mac mini 的 SSH 终端**运行：

```sh
cd /Users/xu/Documents/mcpx-projects/dafeiyu-telegram
python3 scripts/setup_telegram_credentials.py
```

- 先输入自己的 **Telegram 数字 User ID**（不是 Bot ID），再粘贴 BotFather 给你的 Token。脚本使用 `getpass` 关闭终端回显，不会把 Token 作为 shell 命令参数、环境变量或日志输出。
- Token 仅写在 Mac 的 `private/telegram/bot_token`，Owner ID 写入 `private/deploy.env`；私有文件夹设置为 0700，文件设置为 0600，且 `private/` 已被 Git 忽略。
- 已有 Token 时必须明确输入 `REPLACE` 才会覆盖。**不要把任何 Token、文件正文或截图发送给 ChatGPT。**
- 本脚本只做本机安全保存和格式检查，**不向 Telegram 发请求，也不自动填写 AstrBot WebUI 的 Bot Token**。最终启用机器人仍需要在本机私有 AstrBot 配置中设置 Token；不要把该私有文件内容提交到 Git。
- 手机剪贴板可能暂存 Token，粘贴后建议清除剪贴板。成功后只需告诉 ChatGPT“Telegram 凭据已配置”，我可以不读取文件内容，仅检查路径是否存在以及权限是否正确。

## 待开发完成且授权正式部署后（此处仅给操作方法）

1. 运行上面的安全配置脚本；它会创建 `private/deploy.env`（Owner ID）和私有 Bot Token 文件。文件位于 Git 忽略目录，不要上传任何 Bot Token 到代码仓库。
2. 确保 `private/oauth/credentials.json` 已存在（M0-B 通过）。不要手工复制其内容。
3. 在项目根目录按需建立 `runtime/astrbot/data`；确保 `private/oauth` 是可读写目录（非单文件只读挂载）。本地文件权限目标分别 0700/0600。
4. Docker Compose 文件：`deploy/telegram/compose.yaml`，运行时指定 `--env-file private/deploy.env`。**不要同时运行原 QQ/NapCat 编排**。
5. 在 Mac 本机访问 `http://127.0.0.1:6185`，修改初始管理密码。只绑定 Mac loopback；远程手机可通过 Termux SSH 的 `-L 127.0.0.1:6185:127.0.0.1:6185` 端口转发访问。
6. WebUI → 机器人 → 新建：类型 **telegram_owner**，**ID 必须为 `telegram_owner`**，填入单独创建的 Telegram Bot Token，启用 Long Polling。该 Token 只放在私有 AstrBot 配置中。不要使用原 Telegram Bot 的 Token 与另一个轮询进程同时启动，否则更新会冲突。
7. WebUI → 模型服务 → 新建：类型 `dafeiyu_siwc`，实例 ID 可用 `dafeiyu_siwc`，启用并设为聊天模型。代码从私有凭据读取模型，不使用商业 API Key。
8. 所用配置文件启用白名单，`id_whitelist` 仅填 `telegram_owner:FriendMessage:<Owner ID>`，关闭两项管理员白名单豁免，关闭未允许来源的详细日志；只启用本项目两个插件。不要加载旧 bili_activity、face_convert 或 schedule_awareness。
9. 选择 AI → 模型 → `dafeiyu_siwc`；不启用 Function Tool、MCP、图像识别等首版非目标能力。

## 主人聊天功能

- 文本聊天：通过 Telegram 原生长轮询进入 SIWC Responses。
- `/remember 明确要保存的长期记忆`：保存到本地私有 `notes.json`，每次 LLM 回合注入（最多 24 条存储、最近 16 条注入）。
- `/memories`：查看笔记；`/forget 3`：删除第 3 条。
- 默认每天 10:00 Asia/Shanghai 触发一次固定关怀文字；可由环境变量 `DAFEIYU_RHYTHM_HOUR`、`DAFEIYU_RHYTHM_TZ` 配置。
- 节律消息遇 SIWC 忙、Telegram 发送失败或超时直接跳过，不自动重试，不建立额外去重表。
- 图片、语音、视频和群聊均不支持，非主人无响应。

## OAuth 恢复

- 第一次授权或真正失效时，仅在 Mac 运行 `scripts/probe_siwc.py --phone-browser`。手机端先建立 SSH `-L 127.0.0.1:18765:127.0.0.1:18765` 转发，再用手机浏览器访问本地 `/auth/start`。
- 运行期的 Provider 通过 `asyncio.Lock` 串行刷新、同目录原子替换；挂载整个目录必须可写。
- **重新登录前停止新 AstrBot 容器**，以免 CLI 与 Provider 同时旋转同一套 Refresh Token；登录后重启容器。
- HTTP 401 最多刷新重试一次，429/403 不换用其他 API Key。检查失败时只看错误类别，不要上传 `credentials.json` 或 Token。
- SSH 的 `channel ... Connection refused` 出现在授权脚本退出后可属正常：临时 loopback HTTP 监听已经关闭。

## 回滚和不会做的事

- 仅停止新 `dafeiyu-telegram` 容器，保留 `runtime/` 和 `private/` 数据；不要使用 `down -v`，更不要操作旧 QQ 目录。
- 不修改 upstream `deploy/compose.yaml`、不运行 NapCat 或外挂内核补丁。
- 开发期允许静态检查和局部提交，但按当前用户工程约束 **不运行单测、PR、CI、Merge 或生产部署**；代码完成后的独立最终验收阶段集中完成测试/修复/发布。
- Git 原始 `origin` 是第三方 whyever77 仓库，严禁向其推送；后续需另设本人控制的远程 SOT 再 Push。

## 待验收项（不是已通过证据）

- Telegram Owner 文字往返与非 Owner/群消息沉默。
- 挂载目录下 Token 更新/容器重启恢复。
- Responses 仅 completed 成功，断流或总超时释放 Semaphore。
- 记忆命令、提示词注入、定时消息只抵达本人。
- Docker 单容器运行、回滚零触碰原 QQ。
