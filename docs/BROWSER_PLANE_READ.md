# 大肥鱼 /read → Mac Browser Plane（开发分支）

## 授权目标、成功标准与 Non-goals

- 用户指定：大肥鱼读取网页时调用 **Mac mini 既有 mac-browser-plane**，不新增独立 Browser Use、Chrome、外部浏览器 API 或公网端口。
- 可观察成功标准：Telegram Owner 发送 `/read https://example.com`，或明确的「帮我打开 https://example.com」等单 URL 读取指令后，Bridge 请求进入 Mac 私有队列；宿主机仅调用已安装 MCP 的 `browser_acquire`；获取 C0 或必要 C1 的网页正文并返回 Telegram，显示页面 URL/执行引擎；失败要明确失败，不伪称已读取。普通聊天里仅提及 URL 不会自动访问网站。
- 范围：只改变显式 `/read URL` 的执行来源。现有 `/search`、`/research` 的搜索摘要机制不变；SIWC 不开放 Function Calling；不加入自然语言自动 Tool Planning、浏览器登录、点击、写操作、手机控制、C2/C3；不修改 Browser Plane 本体/SignalForge PIC，不更换 Docker Volume，也不涉及生产部署。
- Phase D：静态检查、Git 开发分支 Commit/安全 Push；不测试、不运行 CI、不发 PR、不 Merge、不安装 launchd、不重启容器。Phase V/R 各需独立授权。

## 调用路径

```text
Telegram Owner /read URL
  → AstrBot local_life (SIWC 仍为 text-only)
  → /AstrBot/browser-plane-bridge/requests/<uuid>.json
  → Mac bind-mounted private/browser-plane-bridge/requests/
  → launchd QueueDirectories 唤醒一次性 Host Worker
  → 已安装的 mac-browser-mcp-call call browser_acquire (stdio)
  → Browser Plane 原 JobStore / Worker / C0→必要时 C1
  → 读取并校验 Browser Plane 自有 evidence artifact
  → private/browser-plane-bridge/responses/<uuid>.json
  → AstrBot 最多读取 9000 字符，Telegram 展示前 2600 字符
```

LaunchAgent 只有存在未处理请求时才触发，不常驻轮询；Bridge 不开放 TCP/HTTP、Docker socket、SSH、浏览器 Profile、任意 MCP tool 或任意 shell 命令。桥接目录由用户 Mac 主机持有，默认 0700、响应 0600，整个 `private/` 被 Git 忽略。每次请求采用 UUID、原子文件写入、过期时间、单处理器文件锁；读取任务即使中断可重试，因为不允许网页写操作。响应仅返回 URL/正文/引擎/Job ID，不回传本地 evidence 路径、OAuth/Telegram 凭据。

## 安全与边界

- URL 两侧均检查 HTTPS、公开域名、DNS 结果非私有地址；杜绝本机/IP 字面量/用户凭据/自定义端口。Browser Plane 内部依旧执行自己的验证。**此类 URL 检查不等于完整 DNS 重绑定/重定向网络沙箱**；因此只面向 Owner 提供公开网页读取，不授权任意内网操作。后续若要对抗恶意重定向或高风险网页，须在 Browser Plane 执行层增加网络出口限制。
- Browser Plane `browser_acquire` 是 C0 优先，只有在既有判定满足时才进入 C1，不保证所有 JavaScript/登录墙/反爬页面可读。普通认证或限流失败不自动升级 C2/C3。
- 并发由宿主文件锁及既有 Browser Plane JobStore 管控。请求有总等待上限，超时不绕过浏览器平面抓取；晚到结果会在后续清理中回收。
- Docker Desktop bind mount 和 macOS launchd 事件通知的跨虚拟化可见性尚待真实验收。若不可达/事件丢失，Bot 有界超时并提示，不启用备用 HTTP 或无审计的网络代理。
- `/search` 与 `/research` 仍由 DDGS 提供公开搜索摘要，不能当成已使用 Browser Plane 读过每篇正文。

## 发布时操作（未执行）

1. 在 Mac mini 先检查 `~/agent-browser-runtime/app/venv/bin/mac-browser-mcp-call` 与 Browser Plane 的已安装 MCP 版本，确认 `browser_acquire` 可用；检查此项目在已发布分支的更改经过 Phase V/R。
2. 停止**仅** `dafeiyu-telegram` 服务，并按现有 v3 Runbook 对核心 SQLite、life SQLite、notes、config 做私有一致性备份，不删除 Volume。
3. 在**已发布的本机 checkout** 执行 `python3 scripts/install_browser_plane_bridge.py install`，配置 launchd QueueDirectories。该脚本负责私有队列创建和 LaunchAgent 注册；不写入 Browser Plane 仓库。
4. 将 `DAFEIYU_BROWSER_PLANE_ENABLED=true` 添加到 Mac 本地、Git 忽略的 `private/deploy.env`，用相同 Compose 及原 Volume 启动更新后的 Bot；不可把 deploy.env、Token 或 Browser Plane artifacts 复制进 Git。
5. 集中验收：Owner `/read https://example.com`→有真实标题/文本且 engine 来源明确；再检查 JS 页面、有界超时、禁止 localhost/私网 URL、非 Owner 沉默、Broker 未运行 fail-closed、Bot 重启及原有记忆和提醒回归；核对 host bridge 无隐形持续轮询。不能用静态检查取代这些真实证据。

## 回滚

- 首先将私有环境变量 `DAFEIYU_BROWSER_PLANE_ENABLED=false`，仅重启 Bot 使读取明确返回「未启用」。保留旧网页 HTTP 提取函数供源码回滚使用，但**新读网页命令不自动降级调用它**。
- 必要时执行 `python3 scripts/install_browser_plane_bridge.py uninstall`，卸载该独立 LaunchAgent；不清除队列以便人工调查，亦不影响已有 Browser Plane Worker。
- 回滚 Bot 源代码与 Compose 按现有 v3 发布程序执行，**不得** `docker compose down -v`、删除 livingmemory/notes 或碰原 QQ/NapCat。
