# 安全说明

本文说明本项目的敏感信息存放方式、已知风险与建议操作。

## 敏感信息存放位置

| 信息 | 存放位置 | 是否进入公开仓库 |
|------|---------|----------------|
| 飞书 Webhook | GitHub Secrets（`FEISHU_WEBHOOK`） | 否 |
| PushPlus / 邮件凭证 | GitHub Secrets | 否 |
| 网页同步用 GitHub Token | 浏览器 localStorage | 否 |
| 关注列表 | `docs/watchlist.json` | 是（仅代码与名称，无金额） |

代码中**不会**硬编码 Token 或 Webhook。Workflow 仅引用 `${{ secrets.* }}`。

## 若 Token 曾在聊天/截图中泄露

请立即执行：

1. 打开 https://github.com/settings/tokens
2. 找到可能泄露的 Token，点击 **Delete** 删除
3. 重新创建 **Fine-grained Token**：
   - Repository access：仅 `fund-monitor`
   - Permissions：**Contents** → Read and write
   - 设置 **Expiration**（建议 90 天或更短）
4. 在监控页 **设置** 中更新新 Token

**切勿**将 Token 提交到仓库、写入 `watchlist.json` 或发给他人。

## 飞书机器人安全（关键词校验）

推送消息标题与正文均包含 **「监控」**（见 `src/formatter.py`），便于启用飞书关键词校验。

配置步骤：

1. 飞书群 → **设置** → **群机器人** → 点击你的机器人
2. **安全设置** → 勾选 **自定义关键词**
3. 添加关键词：`监控`
4. 保存

未包含「监控」的外来请求将被飞书拒绝，降低 Webhook 泄露后被滥用的风险。

## 公开仓库 vs 私有仓库

| 能力 | Public（当前推荐） | Private（免费账户） |
|------|-------------------|---------------------|
| GitHub Actions 定时推送 | 标准 runner **免费** | 每月 2000 分钟免费额度 |
| GitHub Pages 监控页 | **免费** | 不可用（需 Pro） |
| 代码与 watchlist 可见性 | 公开 | 仅自己可见 |

免费账户若改为 Private，**监控网页会失效**。关注列表隐私可通过 Private 隐藏，但 Pages 网站本身通常仍为公开访问。

**建议：保持 Public**，Secrets 不进入代码，风险可控。

## 免费方案能运行多久

- **Public 仓库**：GitHub Actions（标准 runner）与 GitHub Pages **无固定到期日**，可长期使用
- **注意**：仓库若 **60 天无任何 commit**，定时任务会被 GitHub 暂停；任意 commit 可恢复
- 定时规则为周一至周五；非交易时段脚本自动跳过推送（非故障）

## 其他建议

- 不要与他人共用 GitHub Token
- 不在公共电脑保存 localStorage 中的 Token
- 数据源（腾讯/天天基金）为非官方接口，存在变更或限流可能，与仓库可见性无关
