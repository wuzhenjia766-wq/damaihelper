# coding: utf-8
"""大麦真抢运行器（半自动）：扫码登录存 cookie → 隐身浏览器 → 循环抢票 → 停在人工提交。

与 dry-run 的 task_runner 不同，本模块会真实启动浏览器并操作大麦购票页。
默认半自动：脚本负责刷新、选日期/场次/票档、设票数、勾实名观演人，抢到后停在
“提交订单”前，由你本人确认并付款。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from pickle import dumps, loads

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.config_manager import load_concert_config  # noqa: E402


COOKIES_FILE = ROOT / "cookies.pkl"


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def _create_stealth_driver(headless: bool = False, driver_path: str = ""):
    """创建隐身浏览器：优先 undetected-chromedriver，失败则回退 selenium + Selenium Manager。

    仓库自带的 chromedriver.exe 是旧版本（如 113），与本地 Chrome（如 152）不匹配，
    因此这里不走 executable_path，而是交给 uc / Selenium Manager 自动匹配驱动。
    若你在 local_config 里指定了与 Chrome 匹配的 driver_path，会优先复用，避免 uc 下载/跨盘搬运。
    """
    # 1) undetected-chromedriver（更抗自动化检测）。无头模式在本机 Chrome 152 上会闪退，跳过。
    if not headless:
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.chrome.options import Options

            opts = Options()
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument("--start-maximized")
            kwargs = {"options": opts, "headless": headless}
            if driver_path and os.path.exists(driver_path):
                kwargs["driver_executable_path"] = driver_path
            driver = uc.Chrome(**kwargs)
            _log("已启用 undetected-chromedriver 隐身浏览器")
            return driver, "undetected-chromedriver"
        except Exception as exc:  # noqa: BLE001
            _log(f"undetected-chromedriver 启动失败({exc})，回退到 Selenium")

    # 2) selenium（Selenium Manager 自动下载匹配驱动）
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--no-first-run")
    opts.add_argument("--start-maximized")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    if headless:
        opts.add_argument("--headless=new")
    if driver_path and os.path.exists(driver_path):
        driver = webdriver.Chrome(service=Service(executable_path=driver_path), options=opts)
    else:
        driver = webdriver.Chrome(options=opts)
    _log("已启用 Selenium 隐身浏览器")
    return driver, "selenium"


def _inject_cookies(driver) -> bool:
    if not COOKIES_FILE.exists():
        return False
    try:
        cookies = loads(COOKIES_FILE.read_bytes())
    except Exception as exc:  # noqa: BLE001
        _log(f"读取 cookies.pkl 失败：{exc}")
        return False
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:  # noqa: BLE001
            continue
    _log("已注入 cookies.pkl 登录态")
    return True


def _save_cookies(driver) -> None:
    COOKIES_FILE.write_bytes(dumps(driver.get_cookies()))
    _log("已保存登录状态到 cookies.pkl")


def ensure_login(driver, damai_url: str, force_login: bool = False) -> None:
    """确保大麦登录态。cookies.pkl 存在时优先复用，否则/强制时引导扫码登录。"""
    logged_in = False
    if not force_login and COOKIES_FILE.exists():
        # 先访问目标域并注入 cookie
        driver.get(damai_url)
        logged_in = _inject_cookies(driver)

    if logged_in and not force_login:
        return

    driver.get(damai_url)
    _log("### 请在弹出的浏览器中登录大麦（手机大麦 App 扫码 / 手机号验证均可） ###")
    _log("### 登录成功后回到本终端按回车，程序将保存登录态 ###")
    try:
        input("登录完成后按回车继续：")
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("用户取消登录")
    _save_cookies(driver)


def open_target(driver, target_url: str) -> None:
    _log(f"打开购票页：{target_url}")
    driver.get(target_url)
    time.sleep(1.0)


def _build_concert(cfg, driver):
    from ticket_script import Concert

    con = Concert(
        date=cfg["date"],
        session=cfg["sess"],
        price=cfg["price"],
        real_name=cfg.get("real_name") or "",
        nick_name=cfg.get("nick_name") or "",
        ticket_num=cfg["tickets"],
        viewer_person=cfg["viewers"],
        damai_url=cfg["damai_url"],
        target_url=cfg["event_url"],
        driver_path=cfg.get("driver_path") or "",
        manual_submit=True,
    )
    return con.set_driver(driver)


def run_grab(cfg, headless: bool = False) -> int:
    target_url = cfg.get("event_url") or ""
    if not target_url:
        _log("未配置 event_url，无法真抢。请先填写 config/local_config.json。")
        return 1

    driver, backend = _create_stealth_driver(headless=headless, driver_path=cfg.get("driver_path") or "")
    try:
        ensure_login(driver, cfg["damai_url"], force_login=cfg.get("force_login", False))
        open_target(driver, target_url)

        con = _build_concert(cfg, driver)
        _log(f"平台=大麦 场次优先级={cfg['sess']} 票档优先级={cfg['price']} 票数={cfg['tickets']} 观演人索引={cfg['viewers']}")
        _log("进入抢票循环……未开售或缺货会持续刷新，直到锁到场次。")

        while True:
            try:
                con.choose_ticket()
                con.check_order()
            except (KeyboardInterrupt, EOFError):
                _log("已中断，浏览器保持打开，可手动处理订单。")
                return 0
            except Exception as exc:  # noqa: BLE001
                _log(f"本轮未成功：{exc}")
                # 回到购票页继续下一轮
                try:
                    driver.get(target_url)
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.5)
                continue

            if con.status == 6:
                _log("### 抢票成功，已锁定座位，请在浏览器中完成付款 ###")
                return 0
    finally:
        # 半自动：保留浏览器让用户付款，不自动 quit
        _log("运行结束，浏览器保持打开（请手动作业）。如需关闭请手动关闭窗口。")


def detect_buy_state(driver) -> dict:
    """只读判读当前购票状态，返回 {state, reason, evidence, body_sample}。

    state ∈ {AVAILABLE, PRESALE, SOLD_OUT, WEB_BLOCKED, UNKNOWN}
    """
    from selenium.webdriver.common.by import By

    time.sleep(2.0)  # 有界等待渲染，不做重试
    body_text = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:  # noqa: BLE001
        pass

    available_hints = ["立即购买", "立即预订", "选座购买", "提交订单", "马上抢", "立即抢购"]
    blocked_hints = ["该渠道不支持购买", "该渠道不支持购票", "大麦APP扫码购票", "请到大麦App购买", "请到大麦APP购买"]
    soldout_hints = ["缺货", "已售罄", "无票", "售罄"]
    presale_hints = ["预售", "尚未开售", "即将开抢", "敬请期待", "未开售"]

    # 购票按钮类名命中
    btn_classes = ["buy__button", "sku-footer-buy-button", "bui-btn-contained", "bui-btn-full"]
    found_buttons = []
    try:
        for cls in btn_classes:
            for el in driver.find_elements(By.CLASS_NAME, cls)[:3]:
                t = (el.text or "").strip()
                if t and any(k in t for k in available_hints):
                    found_buttons.append(f"{cls}:{t}")
    except Exception:  # noqa: BLE001
        pass

    def hit(hints):
        return [h for h in hints if h in body_text]

    blocked = hit(blocked_hints)
    available = hit(available_hints)
    soldout = hit(soldout_hints)
    presale = hit(presale_hints)

    if blocked:
        return {
            "state": "WEB_BLOCKED",
            "reason": "网页端不支持购买，需大麦App或等正式开票",
            "evidence": blocked,
            "body_sample": body_text[:160],
        }
    if available and not soldout:
        return {
            "state": "AVAILABLE",
            "reason": "检测到可购买按钮",
            "evidence": available + found_buttons,
            "body_sample": body_text[:160],
        }
    if soldout:
        return {
            "state": "SOLD_OUT",
            "reason": "当前缺货/售罄",
            "evidence": soldout,
            "body_sample": body_text[:160],
        }
    if presale:
        return {
            "state": "PRESALE",
            "reason": "预售/尚未开售",
            "evidence": presale,
            "body_sample": body_text[:160],
        }
    return {
        "state": "UNKNOWN",
        "reason": "未能判读页面状态",
        "evidence": [],
        "body_sample": body_text[:160],
    }


def simulate(cfg, headless: bool = False) -> int:
    """只读检测：登录 → 打开页面 → 判读购票状态 → 报告；仅在 AVAILABLE 时转半自动。"""
    target_url = cfg.get("event_url") or ""
    if not target_url:
        _log("未配置 event_url，无法检测。请先填写 config/local_config.json。")
        return 1

    driver, backend = _create_stealth_driver(headless=headless, driver_path=cfg.get("driver_path") or "")
    keep_open = False
    try:
        ensure_login(driver, cfg["damai_url"], force_login=cfg.get("force_login", False))
        open_target(driver, target_url)
        info = detect_buy_state(driver)

        _log(f"【只读检测】购票状态: {info['state']}")
        _log(f"【只读检测】结论: {info['reason']}")
        if info["evidence"]:
            _log(f"【只读检测】命中文案/按钮: {info['evidence']}")
        _log(f"【只读检测】购票链接: {target_url}")

        if info["state"] == "AVAILABLE":
            _log("检测到可购买，转入半自动购票（选座后停在提交前，请人工确认）……")
            keep_open = True
            con = _build_concert(cfg, driver)
            try:
                con.choose_ticket()
                con.check_order()
            except (KeyboardInterrupt, EOFError):
                _log("已中断，浏览器保持打开。")
                keep_open = True
                return 0
            _log("半自动购票流程结束，浏览器保持打开，请人工确认付款。")
            keep_open = True
            return 0

        _log("本次为只读检测，未点击任何购票按钮。")
        return 0
    finally:
        if not keep_open:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass


def watch(cfg, headless: bool = False, interval: float = 4.0) -> int:
    """电脑半自动抢：登录后挂在页面上，等页面变为可购再进半自动选座。

    与 simulate（只读一次）不同：watch 会以 interval 间隔刷新页面，直到 detect_buy_state
    返回 AVAILABLE 才转入购票；其他状态只记录并继续等。可用 Ctrl+C 停止。
    """
    target_url = cfg.get("event_url") or ""
    if not target_url:
        _log("未配置 event_url，无法盯票。请先填写 config/local_config.json。")
        return 1

    driver, backend = _create_stealth_driver(headless=headless, driver_path=cfg.get("driver_path") or "")
    keep_open = False
    try:
        ensure_login(driver, cfg["damai_url"], force_login=cfg.get("force_login", False))
        open_target(driver, target_url)
        _log(f"已进入盯票模式，每 {interval}s 检查一次；检测到可购会自动进入半自动。Ctrl+C 可停止。")

        while True:
            info = detect_buy_state(driver)
            _log(f"当前状态: {info['state']}（{info['reason']}）")

            if info["state"] == "AVAILABLE":
                _log("### 检测到可购！转入半自动选座 ###")
                keep_open = True
                con = _build_concert(cfg, driver)
                try:
                    con.choose_ticket()
                    con.check_order()
                except (KeyboardInterrupt, EOFError):
                    _log("已中断，浏览器保持打开，请手动完成购买。")
                    return 0
                except Exception as exc:  # noqa: BLE001
                    _log(f"半自动选择器未完全匹配（{exc}）。")
                    _log("浏览器已保持打开，请人工在页面内完成选座与提交。")
                    return 0
                _log("半自动购票流程结束，浏览器保持打开，请人工确认付款。")
                return 0

            # 未可购：等待后刷新继续
            try:
                time.sleep(max(1.0, interval))
            except KeyboardInterrupt:
                _log("已停止盯票，浏览器保持打开。")
                keep_open = True
                return 0
            try:
                driver.get(target_url)
            except Exception:  # noqa: BLE001
                pass
    finally:
        if not keep_open:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="大麦真抢（半自动）")
    parser.add_argument("--config", default=None, help="指向自定义 Concert 配置 JSON（默认 config/local_config.json）")
    parser.add_argument("--login-only", action="store_true", help="只执行一次扫码登录并保存 cookies.pkl")
    parser.add_argument("--force-login", action="store_true", help="即使存在 cookies.pkl 也重新扫码")
    parser.add_argument("--headless", action="store_true", help="无头模式（不建议真抢，用于调试）")
    parser.add_argument("--simulate", action="store_true", help="只读检测：判读当前购票状态并报告，不进入抢票循环")
    parser.add_argument("--watch", action="store_true", help="盯票模式：等页面变为可购再进半自动选座")
    parser.add_argument("--interval", type=float, default=4.0, help="盯票轮询间隔秒数（默认 4s）")
    args = parser.parse_args(argv)

    cfg = load_concert_config(args.config)
    # 确保 auto_buy_time 只是参考，不强制等待；真抢以策略为准
    if args.login_only or args.force_login:
        driver, _ = _create_stealth_driver(headless=args.headless, driver_path=cfg.get("driver_path") or "")
        try:
            ensure_login(driver, cfg["damai_url"], force_login=True)
        finally:
            driver.quit()
        _log("登录态已就绪，可运行 `python scripts/real_grab.py` 进行真抢。")
        return 0

    if args.simulate:
        return simulate(cfg, headless=args.headless)

    if args.watch:
        return watch(cfg, headless=args.headless, interval=args.interval)

    return run_grab(cfg, headless=args.headless)


if __name__ == "__main__":
    raise SystemExit(main())
