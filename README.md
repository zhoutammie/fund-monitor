# 基金 / 指数实时监控与推送

个人使用的基金与指数监控工具：**GitHub Pages 监控页** + **GitHub Actions 每 30 分钟推送**。

数据来源：腾讯财经（指数）、天天基金（场外基金估值）。**仅供参考，不构成投资建议。**

---

## 功能

- 监控 A 股 / 港股 / 美股指数实时点位
- 监控场外基金盘中估值
- Web 页面每 3 分钟自动刷新
- 交易时段内每 30 分钟推送到飞书 / 微信（PushPlus）/ 邮件

---

## 快速开始

### 1. 克隆并修改关注列表

编辑 [`config/watchlist.yaml`](config/watchlist.yaml)：

```yaml
indices:
  - code: sh000001
    name: 上证指数
    market: cn

funds:
  - code: "110022"
    name: 易方达消费行业

push:
  channels: ["feishu"]
```

**指数代码（腾讯财经）：**

| 名称 | 代码 |
|------|------|
| 上证指数 | `sh000001` |
| 深证成指 | `sz399001` |
| 恒生科技 | `hkHSTECH` |
| 恒生指数 | `hkHSI` |
| 纳斯达克100 | `usNDX` |
| 标普500 | `usSPX` |

**基金代码：** 打开 [天天基金网](https://fund.eastmoney.com/) 搜索基金，URL 中的数字即为代码（如 `110022`）。

修改关注列表后，请同步更新 [`docs/watchlist.json`](docs/watchlist.json)（供监控页使用）。

---

### 2. 配置飞书机器人（推荐）

1. 打开飞书，创建一个群（或复用已有群）
2. 群设置 → 群机器人 → 添加机器人 → **自定义机器人**
3. 复制 **Webhook 地址**（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）

---

### 3. 配置 PushPlus 微信推送（可选）

1. 打开 [PushPlus 官网](https://www.pushplus.plus/) 注册
2. 微信扫码关注「推送加」公众号
3. 在「一对一消息」页面复制 **Token**

---

### 4. 推送到 GitHub 并配置 Secrets

1. 在 GitHub 新建仓库，上传本项目全部文件
2. 进入仓库 **Settings → Secrets and variables → Actions → New repository secret**
3. 添加以下 Secret（按需）：

| Secret 名称 | 说明 |
|-------------|------|
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |
| `PUSHPLUS_TOKEN` | PushPlus Token |
| `SMTP_HOST` | 邮件 SMTP 主机（如 `smtp.qq.com`） |
| `SMTP_PORT` | 邮件端口（如 `465`） |
| `SMTP_SENDER` | 发件邮箱 |
| `SMTP_PASSWORD` | 邮箱授权码（非登录密码） |
| `SMTP_RECEIVER` | 收件邮箱 |

4. 在 [`config/watchlist.yaml`](config/watchlist.yaml) 的 `push.channels` 中启用对应渠道：

```yaml
push:
  channels: ["feishu", "pushplus"]  # 或 ["email"]
```

---

### 5. 启用 GitHub Actions 定时推送

1. 进入仓库 **Actions** 标签页
2. 若提示启用 workflow，点击 **I understand my workflows, go ahead and enable them**
3. 选择 **Fund Monitor Push** → **Run workflow**
4. 勾选 `force_push: true` 可立即测试（忽略交易时段）
5. 查看运行日志，确认飞书/微信收到消息

默认定时规则：每 30 分钟（UTC），周一至周五。脚本会在 **非交易时段自动跳过** 推送。

---

### 6. 启用 GitHub Pages 监控页

1. 仓库 **Settings → Pages**
2. **Source** 选择 `Deploy from a branch`
3. **Branch** 选 `main`，文件夹选 `/docs`
4. 保存后访问：`https://<你的用户名>.github.io/<仓库名>/`

---

## 本地测试

```bash
cd fund-monitor
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 强制推送测试（忽略交易时段）
export FEISHU_WEBHOOK="你的飞书Webhook"
export FORCE_PUSH=true
cd src && python monitor.py
```

---

## 项目结构

```
fund-monitor/
├── .github/workflows/monitor.yml   # 定时任务
├── config/watchlist.yaml           # 后端关注列表
├── docs/
│   ├── index.html                  # 监控页面
│   ├── app.js
│   ├── style.css
│   └── watchlist.json              # 前端关注列表（需与 yaml 同步）
├── src/
│   ├── fetcher.py                  # 数据采集
│   ├── notifier.py                 # 推送
│   ├── formatter.py                # 消息格式化
│   └── monitor.py                  # 主入口
└── requirements.txt
```

---

## 交易时段说明

| 市场 | 北京时间 |
|------|---------|
| A 股 | 9:30–11:30, 13:00–15:00 |
| 港股 | 9:30–12:00, 13:00–16:00 |
| 美股 | 21:30–04:00（次日） |

场外基金估值仅在 A 股交易时段更新。

---

## 注意事项

- GitHub Actions 定时任务可能有 5–15 分钟延迟
- 仓库需每 60 天有一次 commit，否则 GitHub 会暂停定时任务
- 公开数据源非官方接口，请勿高频调用
- 场外基金显示的是**估值估算**，与实际净值可能有偏差

---

## License

MIT
