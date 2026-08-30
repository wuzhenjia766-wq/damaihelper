# 大麦真抢（半自动）使用说明

区别于 Web 控制台的 dry-run 逻辑演练，`scripts/real_grab.py` 会真实启动浏览器操作大麦购票页。
默认**半自动**：脚本负责刷新、选日期/场次/票档、设票数、勾实名观演人，抢到后停在“提交订单”前，
由你本人确认并付款。

## 1. 依赖

```powershell
python -m pip install undetected-chromedriver
```

仓库自带的 `chromedriver.exe` 与本地 Chrome 版本可能不匹配，真抢走 `undetected-chromedriver`
（或 Selenium Manager 自动匹配驱动），不要手动指定旧版驱动。

> 本机 Chrome 版本与包内 `chromedriver.exe` 很可能不一致（例如 Chrome 152 vs 驱动 113）。
> 请先跑 `chromedriver --version` 与 Chrome 版本比对；不一致时优先让 uc / Selenium Manager
> 自动下载匹配驱动；若网络下载慢，也可从 Chrome for Testing 镜像获取与 Chrome 同大版本的
> `chromedriver.exe`，放到仓库根目录并给 `config/local_config.json` 的 `driver_path` 填绝对路径。

## 2. 填写本地配置（不入库）

复制示例为本地配置并填入真实信息：

```powershell
Copy-Item config/local_config.json.example config/local_config.json
```

字段说明：

| 字段 | 说明 |
|------|------|
| `event_url` | 大麦演出详情页链接 |
| `auto_buy_time` | 开售时间（参考用） |
| `date` / `sess` / `price` | 日期 / 场次 / 票档的优先级（1 起，数字越大优先级越低） |
| `tickets` | 购买票数 |
| `viewers` | 已添加的实名观演人索引（0 起） |
| `driver_path` | 留空即可 |

> `config/local_config.json` 已被 `.gitignore` 忽略，包含真实链接/账号也不会入库。

## 3. 扫码登录一次

```powershell
python scripts/real_grab.py --login-only
```

浏览器会打开大麦，用手机大麦 App 扫码（或手机号验证）登录，登录后回到终端按回车，程序把登录态存到
`cookies.pkl`（已在 `.gitignore`）。之后运行真抢会复用该登录态。

## 4. 校准选择器（首次建议）

大麦页面经常改版，先跑一次校准工具核对 `ticket_script.py` 里的选择器：

```powershell
python scripts/probe_page.py --url "https://detail.damai.cn/item.htm?id=你的演出ID"
```

重点核对 `buy__button`、`bui-dm-sku-calendar`、`sku-times-card`、`sku-tickets-card`、
`bui-dm-sku-card-item`、`sku-footer-buy-button`、`bui-dm-sku-counter`、`plus-enable` 以及
“立即购买 / 即将开抢 / 缺货 / 提交缺货登记”等按钮文案。若与当前页不符，更新对应选择器。

## 5. 开始真抢（半自动）

```powershell
python scripts/real_grab.py
```

流程：打开购票页 → 持续刷新（未开售/缺货自动重试）→ 锁到场次后选票档、设票数、勾观演人 →
停在“提交订单”前按回车提示 → 你在浏览器手动点“提交订单” → 进入付款页自行付款。

> 抢票期间不要关闭浏览器窗口；若需整轮重试，脚本会自动回到购票页继续。

## 6. 只读检测（模拟）

不确定当前能否购买时，先跑只读检测，只判读状态、不点购票按钮、不循环：

```powershell
python scripts/real_grab.py --simulate
```

会输出 `AVAILABLE / PRESALE / SOLD_OUT / WEB_BLOCKED / UNKNOWN` 之一及命中文案。
仅当检测到 `AVAILABLE`（可购买按钮出现）时才进入半自动购票；其余情况打印结论后退出。

> 部分演出网页端会提示「该渠道不支持购买，请到大麦App扫码购票」或「缺货/预售」，
> 此时网页抢票无法下单，需使用大麦 App 或等待正式开票。

## 7. 盯票模式（电脑半自动抢）

网页端暂时不可购但想等开票/捡漏时，用盯票模式：电脑登录后挂在页面上，每隔 `--interval`
秒刷新检测，一旦页面变为可购（`AVAILABLE`）就自动进入半自动选座，停在提交前等你确认。

```powershell
python scripts/real_grab.py --watch --interval 4
```

`Ctrl+C` 可停止，停止后浏览器保持打开。注意：当前页面的购票 DOM 与原 `ticket_script` 选择器
可能不一致，若半自动选座不匹配，会提示你人工在打开的浏览器里完成选座与提交。

## 8. 风险与免责

- 不保证抢到票；成功率受网络、放票量、风控、页面改版影响。
- 自动化购票可能违反平台条款，账号存在被风控/限制风险，后果自行承担。
- 请遵守大麦平台规则与当地法律法规，勿用于商业倒卖。

## 9. 常见问题

**Q: 启动时报 `WinError 17 系统无法将文件移到不同的磁盘驱动器`？**  
`undetected-chromedriver` 在下载驱动后跨盘搬运失败。在 `config/local_config.json` 的
`driver_path` 填一个与 Chrome 版本匹配的 `chromedriver.exe` 绝对路径即可绕过下载与搬运。

**Q: 卡在下载驱动 / Selenium Manager 无输出？**  
通常是网络无法稳定访问驱动源。下载与 Chrome 同大版本的 `chromedriver.exe` 放到仓库根目录，
然后给 `driver_path` 填绝对路径。

**Q: 打开详情页后按钮文案/类名对不上？**  
用 `python scripts/probe_page.py --url "..."` 校准，更新 `ticket_script.py` 对应选择器。
