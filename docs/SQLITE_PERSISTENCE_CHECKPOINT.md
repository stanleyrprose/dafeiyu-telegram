# SQLite 会话持久化诊断检查点 — 2026-11-05

## 结论和边界

在原 Mac bind mount 上，2026-11-05 11:35:48 和 11:41:58 UTC 的两条 Telegram 入站事件均触发 SQLite `DatabaseError`，没有进入 SIWC LLM。保留原数据与一致性备份后，已把 AstrBot 数据目录迁入 Linux Docker 本地 Volume `dafeiyu_telegram_data`。迁移后两轮真实计算对话已正常处理、4 次 SIWC 调用均为 `completed`，其中 8 条历史消息成功落库，并在容器重启后完整保留。重启后已观察到 **5 次新增的成功 SIWC 模型调用**，未再出现 SQLite 错误；用户侧对重启后最新消息的显示尚未进行第二次独立确认。Mac bind mount + WAL 为合理怀疑，尚未通过隔离对照实验严格证明因果。

## 证据

- AstrBot v4.29.4 在 Owner 消息处理期间，从 SessionServiceManager → SharedPreferences.get_async → SQLiteDatabase.get_preference 报过 sqlite3.DatabaseError 和 sqlalchemy.exc.DatabaseError，原始日志包含 `database disk image is malformed`。
- 迁移前数据库位于 Mac `runtime/astrbot/data/data_v4.db`，WAL 模式，文件完整性检查为 `ok`，但旧应用连接查询偏好时反复出错；新 ORM 连接可以读取。
- 迁移前已用 SQLite Online Backup API 在 Git 忽略的 `private/db-backups/` 建立一致快照并校验 `ok`；迁移后再次备份 Linux Volume，校验也为 `ok`。旧 Mac 数据目录没有删除。
- 容器内使用相同 ORM 读取 Owner 会话偏好连续三次成功。
- 容器内使用唯一临时偏好记录做提交、全新连接读回、精确删除，均成功；没有触碰真实用户内容。
- **进一步验证 conversations 表的真实 ORM 路径**：创建一条合成测试会话、更新两轮合成消息、使用新的 ORM engine 读取并核对内容、精准删除及清理后查询，全部通过。测试不涉及真实聊天内容。
- 迁入 Volume 时 `cmd_config.json` 与 `data_v4.db` 逐字节核对一致，新容器确认挂载类型 `volume`、名称正确，WebUI 返回 200，插件加载。容器内再次通过临时偏好与合成会话的 ORM 写入、读回和清理。
- 迁移后真实 Telegram 会话写入 **4 条 User + 4 条 Assistant** 消息，匹配两轮计算问题：8+5→13、刚才的结果加2→15；`provider_stats` 有 4 条 `completed`。重启后 1 条会话、8 条历史及 4 条成功调用仍在，`integrity_check=ok`，未再观察到 SQLite 错误。
- 重启时曾出现单次 Telegram `NetworkError`；原生适配器的长轮询已启动，内建网络恢复机制，无重复失败的证据。重启后已观察到新的成功推理，仍需用户侧确认显示。
- 晚间复核快照（2026-11-05）：容器持续运行约 2 小时，`conversations=1`、历史消息 `18` 条、`provider_stats` 为 `9` 次 `completed`，数据库 `quick_check=ok`，未观察到新的插件加载失败。此为当时的累计计数，不代表重启后一定有新入站请求。受影响路径验收：纯 Python 9 项通过；AstrBot 依赖测试 8 项在 CI 入口明确 skip，并在固定版本 AstrBot 容器内 8/8 通过；ORM 临时偏好/会话持久化测试通过。
- 未清库、未执行 VACUUM、未改 Schema、未改 AstrBot 内核。迁移改变了活动数据库的存储位置，但保留了原始 Mac 数据副本、完整备份和可回滚 Compose 配置。

## 最小剩余验收

1. 真实对话保存与容器重启后历史保留均已通过；不需重复清库或迁移。
2. Owner 在**重启后**再发送一条消息，确认机器人继续回复；从容器日志和数据库检查没有新的 `DatabaseError` 或连续 Telegram 网络失败。
3. 在没有明确的后续失败证据前，不再修改网络重试逻辑或增加守护服务。仅当重启后新消息也能往返时，才把本轮故障修复标记为完整通过。

脚本：`scripts/backup_sqlite_db.py`（直接从 Linux Docker Volume 通过 SQLite Online Backup 生成私有快照）；`scripts/verify_sqlite_persistence.py`（仅在固定版本 AstrBot 容器内运行，使用临时偏好与合成会话，不触碰真实用户内容）。
