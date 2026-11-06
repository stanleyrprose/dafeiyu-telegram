# 大肥鱼 v3 发布、外部授权与回滚（仅在 Phase V/R 授权后执行）

## 当前运行与目标

- 生产运行的是已验证 v2 的单 AstrBot 容器。开发分支 `feat/dafeiyu-livingmemory-autonomy` 不会自动部署。
- 新版仍为一个容器，既有 Volume `dafeiyu_telegram_data`、Owner Telegram 和 SIWC OAuth 不变。
- LivingMemory 是独立第三方 AGPL-3.0 AstrBot 插件；不将其代码并入本仓库。官方固定 2.9.1 / Git revision 1c6a471c9af9ae45a4ccb3a8cec5695c917de50b。
- Embedding 使用 Mac 本地 Ollama 已安装的 bge-m3:latest，1024维；连接地址写入**容器内私有** AstrBot provider 配置，伪 API Key 仅为本地兼容字段，不是云端凭据。

## Phase V 必做的隔离验收

1. 受影响单元/安全/回滚测试：日程创建、重叠、取消、改期与提醒同事务；Owner 白名单、时区、48小时社区链接去重、每日联系额度、未回应停止、免打扰、出站网络不确定状态。
2. 固定 AstrBot v4.29.4 的插件导入、Cron 注册和 SIWC 回归。
3. 只在隔离容器验证 `host.docker.internal:11434` 是否可到达 Mac Ollama；不要为了连接改变 Mac 的防火墙或公开绑定地址。
4. 在独立 Volume（例如 `dafeiyu_v3_acceptance`）安装官方 LivingMemory 2.9.1，可用 `python3 scripts/prepare_livingmemory.py --volume dafeiyu_v3_acceptance` 作为离线准备命令；必须先为该隔离 Volume 生成不含生产凭据的 AstrBot 默认配置。确认 `/lmem status`、1024维、语义召回；不得对生产 Volume 做验证性写入。
5. 用非私人测试词执行公开索引检索，核对 X/Reddit 原站 URL、没有账号登录或未授权平台 API 调用。检索无结果不得伪造。

## Phase R 生产发布步骤

1. 用户批准发布之后，用 Mac `gh` 完成 PR/CI/Merge；确认 `origin/main` 是通过 CI 的发布基线。
2. 记录当前工作树 Commit/Compose/镜像和运行 Volume。对现有生产聊天做一致性快照（core SQLite、state.sqlite3、notes.json），并在 Mac 私有目录备份含现有模型/Telegram 配置的 `cmd_config.json`；这个文件包含凭据，不得进入 Git 或公开日志。
3. **先停止仅 dafeiyu-telegram 容器**；再次执行 `python3 scripts/backup_sqlite_db.py`。LivingMemory 安装后，这个备份脚本还会打包记忆插件的所有索引、图、配置（在容器停止时做一致副本）。
4. 在生产工作树切换到经批准的 `origin/main` 发布 Commit（绝不能切换原作者 `upstream/main`）；运行 Docker Compose 构建 v3 镜像，保持原 Docker Volume。
5. 保持容器停止，运行 `python3 scripts/prepare_livingmemory.py`。脚本从固定 Git revision 安全提取插件源到 Volume，给 `cmd_config.json` 增加 `dafeiyu_bge_m3` 的本地 Embedding Provider，并写入 LivingMemory 配置 `embedding_provider_id=dafeiyu_bge_m3`、`llm_provider_id=dafeiyu_siwc`、`llm_stream_mode=always`。
6. 先以隔离流程确认 Ollama 连通性和插件实际可加载，再在 Mac 私有 `private/deploy.env` 追加 `DAFEIYU_LIVINGMEMORY_ENABLED=true`。此变量打开后旧的自动摘录停用，手动笔记保留；记忆主要由 LivingMemory 管理。
7. 使用原 Compose 启动**同一个**机器人，核对日志、Owner 门禁、Telegram 回复、`/lmem status`、`/lmem search 关键词`，再人工按需 `/proactive on`、`/explore on`。
8. 观察至少一个真实日程与关联提醒、一次重启后的历史、免打扰期和未回应抑制；不拿自动化单测代替手机端确认。

## 回滚与数据保护

- 提前记录 v2 发布 Commit、镜像、Git 工作树；停 bot 才允许切换代码与卷内插件。
- 恢复 v2 源代码前，停容器，运行 v3 的 `python3 scripts/prepare_livingmemory.py --disable`；它将 `data/plugins/astrbot_plugin_livingmemory` 移到 Volume 的 `vendor_disabled_plugins/`，并保留 LivingMemory 数据与配置。不得直接删除用户记忆、向量索引或原有笔记。
- 不删除新 SQLite 表、任务、日程、原 Notes、Memory 索引或 OAuth 文件；不执行 `docker compose down -v`。
- 如需恢复原配置文件，使用发布前的加密/私有备份，不要从公开 Git 重建 Token。恢复后启动 v2 并校验原会话。
- 若嵌入 Provider 不可达，不打开 `OLLAMA_HOST=0.0.0.0` 暴露模型服务；停止并报告具体需要的授权或改用安全的本地桥接。

## X 与 Reddit 的授权边界

- **默认不需要登录**：`/explore` 使用第三方公开搜索索引里的 X/Reddit 帖子链接，不声称实时覆盖，也不调用原站受限 API。
- 若未来要求实时平台检索，X 需要用户在官方开发者控制台建立应用并批准相关 API 权限；Reddit 官方 API 需要 OAuth 和按平台开发者政策取得授权。开发者账号、付费、Cookie、二次验证码均不由机器人自行获取，届时单独请求主人完成网页登录与授权。
- 官方 API 授权前，不得暗中切换到模拟登录、越权抓取、绕过 CAPTCHA、购买第三方 Token 等路径。
