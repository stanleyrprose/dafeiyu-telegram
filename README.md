# 大肥鱼 Telegram — ChatGPT SIWC 单用户版本

基于 [whyever77/dafeiyu-astrbot](https://github.com/whyever77/dafeiyu-astrbot) 的角色设定及记忆/生活节律设计整理的精简自托管版本。原项目按 MIT 许可证授权，详见 [LICENSE](LICENSE)。

此版本使用 **AstrBot v4.29.4、原生 Telegram 长轮询、ChatGPT SIWC OAuth（Responses API）**，首版只支持一个 Owner 的私聊文字、显式保存的本地记忆与一条每日主动关怀。**不依赖 NapCat、QQ、B 站、API Key、本地代理、设备控制或 Function Tool。**

## 目录

- `plugin/astrbot_plugin_dafeiyu_siwc/`：Owner 私聊平台适配 + SIWC Provider。
- `plugin/astrbot_plugin_dafeiyu_local_life/`：人格提示、显式本地记忆、低频节律。
- `scripts/probe_siwc.py`：仅在 Mac 宿主机进行的 SIWC 授权资格探针。
- `scripts/setup_telegram_credentials.py`：在 SSH 交互终端不回显输入 Telegram Token。
- `scripts/provision_telegram_runtime.py`：把本机保存的凭据写入 Git 忽略的 AstrBot 私有运行配置。
- `deploy/telegram/compose.yaml`：单容器 Docker Compose。
- `deploy/telegram/README.md`：完整部署、恢复和回滚说明。

## 安全边界

Owner 数字 ID 必须与 Telegram 私聊的发送者和聊天 ID 同时匹配；群聊及非 Owner 消息在进入 AstrBot 消息转换前被阻止。默认禁用多模态和函数工具；SIWC 只使用当前账号实际授权的模型，无 API Key 降级。

所有凭据、运行数据库、容器配置及临时文件位于 `private/` 或 `runtime/`，不进入 Git。不要将本机 `credentials.json`、Bot Token、聊天历史或运行日志提交到公共仓库。

## 安装与验收

按 [Mac mini 部署说明](deploy/telegram/README.md) 操作。首次启动容器生成默认配置后需停止容器、运行离线配置脚本、再启动。对外访问仅使用 Telegram，WebUI 端口只绑定 Mac 的 `127.0.0.1:6185`。

开发和验收依据 [AGENTS.md](AGENTS.md) 与 [docs/DEV-WORKFLOW-v1.0.md](docs/DEV-WORKFLOW-v1.0.md)。此分支为**供后续 PR 使用的共同历史基线**，不是已经 Merge 到 main 的生产版本；真实外部服务可用性应以本次实测证据为准。

**尚未通过的验收项：** Telegram 聊天历史的持久化和重启恢复。当前 SQLite 读写验证通过，但历史日志曾出现数据库格式异常。参见 [SQLite 诊断检查点](docs/SQLITE_PERSISTENCE_CHECKPOINT.md)，不能将用户收到单条回复等同于历史保存成功。
