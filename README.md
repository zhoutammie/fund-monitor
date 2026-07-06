# 基金 / 指数实时监控与推送

个人使用的基金与指数监控工具：**GitHub Pages 监控页** + **GitHub Actions 每 30 分钟推送**。

数据来源：腾讯财经（指数/股票）、天天基金（场外基金估值）。**仅供参考，不构成投资建议。**

---

## 功能

- 监控 A 股 / 港股 / 美股指数实时点位
- 监控 A 股 / 港股 / 美股股票实时价格
- 监控场外基金盘中估值
- **网页可视化管理**关注列表（添加/删除 + 一键同步到飞书推送）
- Web 页面每 3 分钟自动刷新
- 交易时段内每 30 分钟推送到飞书 / 微信（PushPlus）/ 邮件

---

## 监控页（推荐）

访问：**https://zhoutammie.github.io/fund-monitor/**

### 管理关注列表

1. 在页面上方选择类型（指数 / 股票 / 场外基金），输入代码，点 **添加**
2. 点击卡片右上角 **×** 可删除
3. 首次使用：点 **设置**，填入 GitHub Token（见下方说明）
4. 修改后点 **保存并同步**，飞书推送将使用新列表

| 类型 | 代码示例 |
|------|---------|
| 指数 | `sh000001`（上证）、`hkHSTECH`（恒生科技）、`usNDX`（纳斯达克） |
| 股票 | `sh600519`（茅台）、`sz000858`（五粮液）、`hk00700`（腾讯） |
| 场外基金 | `110022`（6 位数字，天天基金网可查） |

也可只输入 6 位数字（如 `600519`），系统会自动补全为 `sh600519` / `sz000858`。

### 配置 GitHub Token（一次性）

用于将页面上的修改同步到 GitHub 仓库，使飞书推送内容一致。

1. 打开 https://github.com/settings/tokens
2. **推荐 Fine-grained Token**：
   - Repository access：仅 `fund-monitor`
   - Permissions：**Contents** → Read and write
   - 设置过期时间（如 90 天）
3. 若使用 Classic Token：勾选 `repo` 权限（权限范围更大，不推荐长期使用）
4. 复制 Token，在监控页 **设置** 中粘贴保存

Token **只保存在浏览器 localStorage**，不会写入仓库或 GitHub Actions Secrets。若曾在聊天中发送过 Token，请先删除旧 Token 再创建新的（见 [SECURITY.md](SECURITY.md)）。

---

## 配置文件

唯一数据源：[docs/watchlist.json](docs/watchlist.json)

```json
{
  "indices": [{ "code": "sh000001", "name": "上证指数", "market": "cn" }],
  "funds": [{ "code": "110022", "name": "易方达消费行业" }],
  "stocks": [{ "code": "sh600519", "name": "贵州茅台", "market": "cn" }],
  "refresh_interval": 180,
  "push": { "channels": ["feishu"] }
}
```

网页同步或手动编辑此文件均可。`config/watchlist.yaml` 已废弃。

---

## 飞书推送配置

1. 飞书电脑版：群设置 → 群机器人 → **自定义机器人** → 复制 Webhook
2. GitHub 仓库 **Settings → Secrets → Actions**，添加 `FEISHU_WEBHOOK`
3. **安全设置（推荐）**：机器人 → 自定义关键词 → 添加 `监控`（推送标题含该词，见 [SECURITY.md](SECURITY.md)）
4. Actions → **Fund Monitor Push** → Run workflow（`force_push: true` 可立即测试）

---

## 免费运行与安全

详见 [SECURITY.md](SECURITY.md)。摘要：

- **能跑多久**：Public 仓库下 Actions + Pages 可**长期免费**；60 天无 commit 会暂停定时任务
- **Token 是否在代码里**：**否**。飞书 Webhook 在 GitHub Secrets；网页 Token 在浏览器 localStorage
- **是否改 Private**：免费账户**不建议**（会失去 GitHub Pages 监控页）
- **若 Token 曾泄露**：立即到 GitHub 删除旧 Token，改用 Fine-grained Token（仅 `fund-monitor` + Contents 读写 + 设置过期）

---

## 其他推送渠道（可选）

在 `docs/watchlist.json` 的 `push.channels` 中配置：

```json
"push": { "channels": ["feishu", "pushplus"] }
```

并在 GitHub Secrets 中添加 `PUSHPLUS_TOKEN` 或邮件相关 Secrets（见原 README）。

---

## 本地测试

```bash
cd fund-monitor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FEISHU_WEBHOOK="你的飞书Webhook"
export FORCE_PUSH=true
cd src && python monitor.py
```

---

## 项目结构

```
fund-monitor/
├── .github/workflows/monitor.yml
├── docs/
│   ├── index.html          # 监控页
│   ├── app.js              # 行情展示
│   ├── manage.js           # 关注列表管理 + GitHub 同步
│   ├── style.css
│   └── watchlist.json      # 唯一配置（页面 + 推送共用）
├── src/
│   ├── fetcher.py
│   ├── formatter.py
│   ├── notifier.py
│   └── monitor.py
└── requirements.txt
```

---

## 注意事项

- 添加/删除后必须点 **保存并同步**，飞书推送才会更新
- GitHub Actions 定时任务可能有 5~15 分钟延迟
- 场外基金显示的是**估值估算**，与实际净值可能有偏差

---

## License

MIT
