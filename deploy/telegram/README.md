# 大肥鱼 Telegram + SIWC｜Mac mini 部署与恢复

> **版本区分：已部署的 v1.3 已通过聊天与 SQLite 历史恢复验收。P1+P2 四项新增能力当前处于开发分支，尚未完成测试、PR、CI、Merge 或生产部署。不要将开发源文件直接视为已上线。**
> 上游大肥鱼来源：whyever77/dafeiyu-astrbot v2.11.1（MIT）；AstrBot 目标：v4.29.4 / 6133541。不得复制原 QQ 运行目录。

## 实际结构

- `scripts/probe_siwc.py`：宿主机首次授权/重新授权 CLI，手机 Termux 通过 SSH 本地端口转发。已由用户报告 M0-B 成功，模型 gpt-6.1-sol。
- `plugin/astrbot_plugin_dafeiyu_siwc/`：原生 Telegram 适配器薄包装 + SIWC Provider，拒绝非主人、群聊、非文本请求。
- `plugin/astrbot_plugin_dafeiyu_local_life/`：本地记忆、一次性提醒与待办、只读公共检索、基于记录的每日关怀。P1+P2 使用独立 `state.sqlite3`，旧的 `notes.json` 无需迁移。
- `persona/大肥鱼-Telegram.md`：精简版人设，移除旧 QQ/B 站/手机/语音工具承诺。
- `deploy/telegram/compose.yaml`：一个固定 v4.29.4 AstrBot 容器，未启用 NapCat 或四个旧内核补丁。
- `private/oauth/`：宿主机私有可写目录，包含 OAuth 授权文件，**禁止提交或发送**。
- `dafeiyu_telegram_data`：Linux Docker 本地 Volume，存放当前 AstrBot 配置、SQLite、插件状态；`runtime/astrbot/data/` 是迁移前保留的 Mac 回滚副本，不再是活动数据库。两者都不能混入旧 QQ 数据。

## 通过手机 Termux → SSH 安全配置 Telegram 凭据

在**已经连接 Mac mini 的 SSH 终端**运行：

```sh
cd /path/to/dafeiyu-telegram
python3 scripts/setup_telegram_credentials.py
```

- 先输入自己的 **Telegram 数字 User ID**（不是 Bot ID），再粘贴 BotFather 给你的 Token。脚本使用 `getpass` 关闭终端回显，不会把 Token 作为 shell 命令参数、环境变量或日志输出。
- Token 仅写在 Mac 的 `private/telegram/bot_token`，Owner ID 写入 `private/deploy.env`；私有文件夹设置为 0700，文件设置为 0600，且 `private/` 已被 Git 忽略。
- 已有 Token 时必须明确输入 `REPLACE` 才会覆盖。**不要把任何 Token、文件正文或截图发送给 ChatGPT。**
- 本脚本只做本机安全保存和格式检查，**不向 Telegram 发请求，也不自动填写 AstrBot WebUI 的 Bot Token**。最终启用机器人仍需要在本机私有 AstrBot 配置中设置 Token；不要把该私有文件内容提交到 Git。
- 手机剪贴板可能暂存 Token，粘贴后建议清除剪贴板。成功后只需告诉 ChatGPT“Telegram 凭据已配置”，我可以不读取文件内容，仅检查路径是否存在以及权限是否正确。

## 首次部署与配置

1. 运行上面的安全配置脚本；它会创建 `private/deploy.env`（Owner ID）和私有 Bot Token 文件。文件位于 Git 忽略目录，不要上传任何 Bot Token 到代码仓库。
2. 确保 `private/oauth/credentials.json` 已存在（M0-B 通过）。不要手工复制其内容。
3. 运行数据存放于 Docker 本地 Volume `dafeiyu_telegram_data`（不是 Mac bind mount）；`private/oauth` 仍为宿主机可写私有目录。首次部署先在项目根目录执行 `docker volume create dafeiyu_telegram_data`。P1+P2 在原 AstrBot v4.29.4 之上仅增加一个固定依赖层，须先 `docker compose --env-file private/deploy.env -f deploy/telegram/compose.yaml build`，构建不应启动或替换旧机器人。
4. 启动一次 `docker compose --env-file private/deploy.env -f deploy/telegram/compose.yaml up -d`（首次启动可使用已构建的镜像）生成默认配置，再执行 `docker compose --env-file private/deploy.env -f deploy/telegram/compose.yaml stop`。**保持服务停止**，使用一次性容器注入私有配置（凭据只通过只读文件挂载进入，不出现在命令行或 Git）：

   ```sh
   docker run --rm \
     -v dafeiyu_telegram_data:/AstrBot/data \
     -v "$PWD/private:/private:ro" \
     -v "$PWD/scripts/provision_telegram_runtime.py:/opt/provision.py:ro" \
     -e DAFEIYU_DATA_DIR=/AstrBot/data \
     -e DAFEIYU_PRIVATE_DIR=/private \
     --entrypoint python soulter/astrbot:v4.29.4 /opt/provision.py
   ```

   注入成功后，使用原 Compose 命令 `up -d` 重启。**不要在运行时修改 `cmd_config.json`；也不要同时启动旧 QQ/NapCat。**
5. 在 Mac 本机访问 `http://127.0.0.1:6185`，修改初始管理密码。只绑定 Mac loopback；远程手机可通过 Termux SSH 的 `-L 127.0.0.1:6185:127.0.0.1:6185` 端口转发访问。
6. **不要再在 WebUI 手动新增 Telegram/Provider 实例**：上一步离线配置脚本已写入唯一的 `telegram_owner` 轮询适配器、`dafeiyu_siwc` 模型以及 Owner 私聊白名单。重复创建实例可能导致冲突。验证相关配置只通过本地文件的非敏感字段，切勿输出 Token。
7. 禁用旧 bili_activity、face_convert 或 schedule_awareness 插件及 Function Tool、MCP、多模态等非目标能力。

## 主人聊天功能

- 文本聊天：通过 Telegram 原生长轮询进入 SIWC Responses。
- `/remind 明天上午9点提醒我开会`：明确时间的提醒；支持 `/reminders`、`/cancel ID`、`/retry ID`（仅投递不确定项）。无明确时间时拒绝猜测。
- `/todo 每天读书30分钟`、`/todos`、`/done ID`：真实本地待办，重启后仍可恢复。
- `/remember 事实`、`/memories`、`/forget ID`：保持原有持久笔记。`/autoremember on/off/status` 管理低敏感、带原话证据的偏好与目标自动记忆。
- `/search 关键词`、`/read https://...`、`/research 问题`：公开网页检索/只读正文/基于搜索摘要的有来源回答。无网页登录、浏览器自动化或 Function Tool。
- `/nudge on/off/status/now`：根据真实待办、临近提醒和互动活动生成每日一次的主动关怀，没有依据或刚聊过则跳过。
- 设置 `DAFEIYU_TZ` 控制提醒时区（默认 Asia/Shanghai）；关怀时区仍用 `DAFEIYU_RHYTHM_TZ`。第三方公共搜索仅适合非敏感查询。
- P1+P2 唯一额外依赖为 `ddgs==9.16.1`，由单容器 Dockerfile 在构建时固定安装（来源是插件 requirements.txt，单一版本定义）。如果检索引擎不可用，只让 `/search`、`/research` 失败，提醒、待办和记忆仍可正常运行。
- 图片、语音、视频和群聊仍不支持；仅接收 Owner 私聊。

## SQLite 数据与回滚（Mac mini）

- **当前运行库**：Docker Linux 本地 Volume `dafeiyu_telegram_data`，容器内路径 `/AstrBot/data/data_v4.db`。不再通过 macOS bind mount 直接访问 SQLite WAL。`private/oauth` 仍在 Mac 上，原 QQ 服务未改动。
- **一致性备份**：在 Mac 项目根目录执行 `python3 scripts/backup_sqlite_db.py`，脚本通过一次性 Docker 容器使用 SQLite Online Backup，保存核心 `data_v4.db`、新增本地生活助手 `state.sqlite3` 及旧 `notes.json`，全部放入 Git 忽略的 `private/db-backups/`，文件权限 0600。不要直接复制运行中的 SQLite 文件。
- **迁移前的只读回滚快照**：Mac 原 `runtime/astrbot/data/` 保持原状；迁入 Docker Volume 时已校验配置与数据库文件一致，Volume 的 `integrity_check=ok`。
- **回滚**：先停止 `dafeiyu-telegram`，再备份活动 Docker Volume，之后才考虑把 Compose 切回旧 Mac bind mount。**注意：原 Mac 目录不包含迁移之后产生的新聊天；不可直接切回并声称无数据损失。** 如确需回滚，先将 Volume 的最新数据离线复制到新的 Mac 目录，验证一致后再切换挂载。不得执行 `down -v` 或删除 Volume。
- 原故障为 Telegram 消息抵达后触发 AstrBot 会话偏好查询的 `SQLite DatabaseError`；将存储改为 Linux Volume 是针对 macOS bind mount + WAL 的**可逆风险隔离**，不是已经证明根因。需以新消息和重启后历史恢复的实际证据验收。

## OAuth 恢复

- 第一次授权或真正失效时，仅在 Mac 运行 `scripts/probe_siwc.py --phone-browser`。手机端先建立 SSH `-L 127.0.0.1:18765:127.0.0.1:18765` 转发，再用手机浏览器访问本地 `/auth/start`。
- 运行期的 Provider 通过 `asyncio.Lock` 串行刷新、同目录原子替换；挂载整个目录必须可写。
- **重新登录前停止新 AstrBot 容器**，以免 CLI 与 Provider 同时旋转同一套 Refresh Token；登录后重启容器。
- HTTP 401 最多刷新重试一次，429/403 不换用其他 API Key。检查失败时只看错误类别，不要上传 `credentials.json` 或 Token。
- SSH 的 `channel ... Connection refused` 出现在授权脚本退出后可属正常：临时 loopback HTTP 监听已经关闭。

## 回滚和不会做的事

- 仅停止新 `dafeiyu-telegram` 容器，保留 `runtime/` 和 `private/` 数据；不要使用 `down -v`，更不要操作旧 QQ 目录。
- 不修改 upstream `deploy/compose.yaml`、不运行 NapCat 或外挂内核补丁。
- 开发期仅静态检查、分批 Commit/Push；代码完成后集中运行受影响路径测试与回归，符合验收门禁才进入 PR/CI/Merge。真实部署有独立授权和回滚程序。
- 代码事实源是 PUBLIC 仓库 `stanleyrprose/dafeiyu-telegram`，原作者仓库仅作为 `upstream` 参考。PR 准备分支基于公共模板 `main` 的共同历史，不需强推。验收未完成前不得 Merge 或向 `upstream` Push。

## 最终验收条件（以当次实测为准）

- Telegram Owner 文字往返与非 Owner/群消息沉默。
- 挂载目录下 Token 更新/容器重启恢复。
- Responses 仅 completed 成功，断流或总超时释放 Semaphore。
- 记忆命令、提示词注入、定时消息只抵达本人。
- Docker 单容器运行、回滚零触碰原 QQ。
