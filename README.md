# DNSHE 域名自动续期助手（飞书通知版）

基于 GitHub Actions 自动续期 [DNSHE](https://www.dnshe.com/) 免费域名，通过 **飞书群机器人** 推送结果，支持多账号、预检、自动重试与失败兜底告警。

> **模板使用方式**：Fork 本仓库 → 按下方步骤配置你自己的 GitHub Secrets → 在 Actions 中手动触发一次即可运行。密钥只存在你自己的仓库 Secrets 中，不会泄露。

## 功能特性

- **全自动续期**：每月 1 日、15 日北京时间 09:12 自动运行，也可在 GitHub 网页手动触发
- **多账号支持**：最多 10 个 DNSHE 账号（`DNSHE_API_KEY_1` / `DNSHE_API_SECRET_1` 起编号）
- **智能续期**：仅对剩余天数不足 180 天的域名续期；`永不过期` 的域名自动跳过
- **运行前预检**：检查账号认证、域名列表获取、到期时间字段解析，任一失败即通知并退出，不执行续期
- **请求重试**：超时 / 连接错误 / HTTP 5xx 时指数退避重试 3 次
- **上次续期记录**：根目录 `last_renew.json` 记录每个域名上次续期时间，通知中显示"上次续期 X 天前"
- **失败兜底告警**：即使脚本崩溃，GitHub Actions job 失败也会通过 `if: failure()` 单独推送告警
- **隐私安全**：密钥通过 GitHub Secrets / 本地 `.env` 注入，`.env` 已被 gitignore

## 快速上手

### 第一步：创建飞书群机器人

1. 注册飞书账号（个人免费）并登录
2. 创建一个群（可只包含自己），进入群后点击右上角 **... → 设置 → 群机器人 → 添加机器人 → 自定义机器人**pc端有自定义机器人选项，手机端没有
3. 起名并添加，复制 **Webhook 地址**（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）
4. 安全设置建议开启 **签名校验**（可点击机器人进入配置页设置），复制签名密钥
   - 开启签名：通知请求需带 `timestamp + sign`，本脚本已支持，配置 `FEISHU_SIGN_SECRET` 即可
   - **不要用 IP 白名单**：GitHub Actions 运行器 IP 动态变化，会挡掉通知
   - 不设置任何安全设置也可以使用（webhook 泄露有被乱发消息的风险）
5. 将 Webhook（和可选签名密钥）填入下一步的 Secrets

### 第二步：配置 GitHub Secrets  重点！

在仓库 **Settings → Security and quality 目录下的 Secrets and variables → Actions** 点击 New repository secret 新增：

| 变量名称 | 必填 | 示例 | 说明 |
|---|---|---|---|
| `DNSHE_API_KEY_1` | 是 | `cfsd_8f3a91c2b4d5e607` | 第 1 个账号的 API Key |
| `DNSHE_API_SECRET_1` | 是 | `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6` | 第 1 个账号的 API Secret |
| `DNSHE_API_KEY_2` ~ `DNSHE_API_KEY_10` | 否 | `cfsd_1a2b3c4d5e6f7890` | 其余账号，按需配置 |
| `DNSHE_API_SECRET_2` ~ `DNSHE_API_SECRET_10` | 否 | `z9y8x7w6v5u4t3s2r1q0` | 其余账号 |
| `FEISHU_WEBHOOK_URL` | 是 | `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxxxxxxxxxxxxxxxxxx` | 飞书机器人 Webhook |
| `FEISHU_SIGN_SECRET` | 否 | `Gi7pQw9rT2yL5nV8bCk4m` | 飞书签名密钥（开启签名校验时填写） |

> 上表"示例"列均为**虚构占位**，请勿直接复制，需填写你自己的真实值。

> DNSHE API Key 获取：登录 [DNSHE](https://my.dnshe.com/) → 免费域名 → API 管理 → 创建 API 密钥。

### 第三步：手动触发一次

进入 **Actions → DNSHE Domain Auto Renew → Run workflow** 验证配置。手动触发时会向飞书发送一条 `ℹ️ 手动触发运行：DNSHE 预检通过（N 个账号，M 个域名），飞书通知链路正常。` 的确认消息，收到即代表 GitHub Secrets、webhook、签名、脚本全链路正常。首次运行日志中若提示密钥缺失属预期，配置后重跑即可。
具体域名情况可见对应action中的renew日志run renew script

## 本地运行与测试 (非必要)

```bash
# 1. 安装依赖（建议使用项目专用 conda 环境）
pip install -r requirements.txt

# 2. 复制模板并填写真实值
copy .env.example .env

# 3. 本地试跑（会真实调用 DNSHE 只读接口做预检）
python renew_domains.py
```

配置优先级：**环境变量 > `.env` 文件**。GitHub Actions 中由 Secrets 注入，无需 `.env`。`.env` 与 `.gitignore` 是隐私保护层：密钥只存在于本地 `.env`，绝不进入仓库。

## 通知说明

| 场景 | 是否通知 |
|---|---|
| 续期成功 | ✅ 每条域名单独通知（含剩余天数、新到期时间、消耗积分、上次续期） |
| 续期失败 | ❌ 立即通知，含错误详情 |
| 预检失败 / 无账号配置 / 脚本异常 | ❌ 通知并退出 |
| 手动触发运行 | ℹ️ 必发一条"链路正常"确认消息（无论是否有续期） |
| 所有域名剩余天数充足，无需操作 | 不通知，仅写 Actions 日志 |
| 脚本崩溃导致 job 失败 | ❌ 工作流 `if: failure()` 单独兜底告警 |

## 运行计划与日志

- **cron**：`12 1 1,15 * *`（UTC）= 北京时间每月 1、15 日 09:12，避开整点/半点以降低飞书限流风险
- **手动触发**：`workflow_dispatch` 随时可点；手动触发必发一条链路确认消息，定时运行保持"有需要才通知"
- **日志保留**：GitHub 默认保留 90 天。如需改为 14 天，在 **Settings → Actions → General → Workflow job retention** 中修改（workflow YAML 无此设置项）
- **并发保护**：已加 `concurrency`，手动与定时触发不会同时运行

## 说明与注意事项

- 续期请求重试仅在超时/连接错误/5xx 时进行；若首次请求实际成功但响应丢失，重试可能重复扣减积分（低概率）
- `last_renew.json` 由工作流自动回写并提交，无需手动维护；已不在域名列表中的旧记录会被自动清理
- 时间统一使用 UTC 存储与计算，避免时区混乱
- 密钥请勿提交到代码库；建议定期在 DNSHE 后台 `regenerate` 轮换密钥

## 致谢

- [DNSHE](https://www.dnshe.com/)
- [DeepSeek](https://platform.deepseek.com/)
- [OpenCode](https://opencode.ai/)
- [Elsht666](https://github.com/Elsht666/DNSHE-Auto-COMPAT)
- [飞书](https://www.feishu.cn/)
