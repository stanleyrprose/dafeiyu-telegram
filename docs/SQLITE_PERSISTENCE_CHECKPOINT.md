# SQLite 会话持久化诊断检查点 — 2026-11-05

## 结论和边界

当前数据库的读写测试通过，但没有复现和解释此前的 `database disk image is malformed`；真实 Telegram 聊天历史持久化仍未通过。两者不能混同。

## 证据

- AstrBot v4.29.4 在 Owner 消息处理期间，从 SessionServiceManager → SharedPreferences.get_async → SQLiteDatabase.get_preference 报过 sqlite3.DatabaseError 和 sqlalchemy.exc.DatabaseError，原始日志包含 `database disk image is malformed`。
- 当前文件为 runtime/astrbot/data/data_v4.db，journal_mode=wal；Mac 和容器内 integrity_check 均为 ok，preferences 表可读取。
- 使用 SQLite Online Backup API 在 Git 忽略的 private/db-backups/ 建立快照，备份 integrity_check=ok，文件 0600。
- 容器内使用相同 ORM 读取 Owner 会话偏好连续三次成功。
- 容器内使用唯一临时偏好记录做提交、全新连接读回、精确删除，均成功；没有触碰真实用户内容。
- **进一步验证 conversations 表的真实 ORM 路径**：创建一条合成测试会话、更新两轮合成消息、使用新的 ORM engine 读取并核对内容、精准删除及清理后查询，全部通过。测试不涉及真实聊天内容。
- 检查时 conversations、provider_stats 和 platform_stats 的行数仍为 0，因此真实聊天历史保存尚未被证明。
- 未清库、未执行 VACUUM、未改 Schema、未移动 SQLite 文件或更改 AstrBot 内核。

## 最小剩余验收

1. Owner 给 Telegram Bot 发送新文字，确认收到明确模型生成的答复，再追问上一轮内容。
2. 只从容器内部核对 conversations 非空历史行数、provider_stats、异常类型，不输出聊天正文或 Token。
3. 重启新容器后确认上下文能延续，且没有新的 DatabaseError。若故障复现，再依证据评估 macOS Docker Desktop bind mount 与 SQLite WAL，而非提前迁移 Docker Volume。
4. 只有真实持久化与重启恢复均通过，才解除该项验收门禁。

脚本：scripts/backup_sqlite_db.py（在线快照）；scripts/verify_sqlite_persistence.py（仅在固定版本 AstrBot 容器内主动使用，临时测试偏好项）。
