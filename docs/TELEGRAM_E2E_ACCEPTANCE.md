# Telegram ↔ SIWC 端到端验收记录（2026-11-05）

状态：**尚未满足完整通过条件**；等待 Owner 在 Telegram 主动发送一条新的私聊文字。

## 已验证的证据

- 新建 `dafeiyu-telegram` 容器在 Mac mini 运行，AstrBot v4.29.4；管理页面返回 HTTP 200。
- 本机 Telegram Bot 凭据已安全接入 `runtime/astrbot/data/cmd_config.json`；Owner ID 白名单为独立私聊 UMO。原始凭据不进入 Git。
- 宿主机 Telegram Bot API `getMe`、`sendMessage` 成功；容器内 Telegram SDK `getMe` 成功。
- 已向唯一 Owner 主动发送含 `d2e4f55c` 的一次性验收提示；Telegram 返回 Message ID（未记录该 ID 或 Token）。
- 原 SIWC 请求在 `response.completed` 前产生 `response.output_text.delta`，但最终 `output=[]`，上游 AstrBot 解析器抛 `EmptyModelOutputError`。
- 兼容补丁仅在 **已成功完成** 且收集到真实文本增量时重构完整最终回答。未完成、失败、断流、无增量仍按失败处理。
- 针对性回归测试（Owner 入口、记忆、历史、Token 到期、Responses 完成/失败/空输出）共 **8/8 通过**。
- 基于实际 Mac SIWC 授权的容器内 Provider 直连推理通过：收到了文本增量、1 个最终回复对象、最终回复非空。
- 容器最近一次重启后，安全诊断尚未观察到新的插件装载错误。

## 观察到的风险与边界

- 早期 Telegram 长轮询出现过 `ConnectError/NetworkError`；当前 Mac/容器 TCP 和容器 SDK `getMe` 可用，尚不能据此保证长时间网络稳定。
- 当前运行数据库仍未观察到新的 Telegram 用户入站对话与可核验的出站 AI 回答，因此不能宣布 `Telegram → LLM → Telegram` 已通过。
- 测试脚本只输出计数、终态和错误类型，不记录用户名、Bot Token、OAuth Access/Refresh Token、响应正文或聊天历史。

## 完整通过条件

1. Owner 在 Telegram 向大肥鱼发送新的文字消息。
2. AstrBot 将它识别为 `telegram_owner:FriendMessage:<owner id>`，无群聊/陌生用户路径旁路。
3. SIWC Provider 执行 Responses 请求、获得 `response.completed`，在异常流格式下能重构非空最终文本。
4. Telegram Bot 将 AI 的回答发回同一 Owner 私聊，用户确认看到回答。
5. 此轮没有未处理的异常；必要时使用只含状态/计数的本地日志与数据库核对。

**本验收不等于 PR、CI 或 Merge 授权。**
