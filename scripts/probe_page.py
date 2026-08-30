# coding: utf-8
"""大麦页面选择器校准工具。

打开指定演出详情页，输出与抢票相关的 SKU 元素、按钮文案、日期/场次/票档卡片，
用于核对 ticket_script.py 里的选择器是否已随页面改版而变化。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.config_manager import load_concert_config  # noqa: E402
from scripts.real_grab import _create_stealth_driver  # noqa: E402


def _dump_element(driver, by, value: str, label: str, limit: int = 40) -> None:
    try:
        from selenium.webdriver.common.by import By

        els = driver.find_elements(by, value)
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] 定位异常: {exc}")
        return
    print(f"[{label}] 数量={len(els)}")
    for idx, el in enumerate(els[:limit]):
        try:
            text = (el.text or "").strip().replace("\n", " / ")[:80]
        except Exception:  # noqa: BLE001
            text = ""
        cls = ""
        try:
            cls = el.get_attribute("class") or ""
        except Exception:  # noqa: BLE001
            pass
        print(f"    - {idx}: class='{cls}' text='{text}'")


def probe(url: str, headless: bool, wait: float, driver_path: str = "") -> int:
    driver, backend = _create_stealth_driver(headless=headless, driver_path=driver_path)
    try:
        print(f"打开 {url}")
        driver.get(url)
        time.sleep(wait)
        print(f"\n== 状态 ==")
        print(f"title: {driver.title}")
        print(f"url  : {driver.current_url}")
        print(f"backend: {backend}")

        from selenium.webdriver.common.by import By

        print("\n== 购票/登录相关元素 ==")
        _dump_element(driver, By.CLASS_NAME, "login-user", "login-user")
        _dump_element(driver, By.CLASS_NAME, "buy__button", "buy__button")
        _dump_element(driver, By.CLASS_NAME, "sku-footer-buy-button", "sku-footer-buy-button")
        _dump_element(driver, By.CLASS_NAME, "bui-dm-sku-calendar", "bui-dm-sku-calendar")
        _dump_element(driver, By.CLASS_NAME, "bui-calendar-day-box", "bui-calendar-day-box")
        _dump_element(driver, By.CLASS_NAME, "sku-times-card", "sku-times-card")
        _dump_element(driver, By.CLASS_NAME, "sku-tickets-card", "sku-tickets-card")
        _dump_element(driver, By.CLASS_NAME, "bui-dm-sku-card-item", "bui-dm-sku-card-item")
        _dump_element(driver, By.CLASS_NAME, "item-tag", "item-tag")
        _dump_element(driver, By.CLASS_NAME, "bui-dm-sku-counter", "bui-dm-sku-counter")
        _dump_element(driver, By.CLASS_NAME, "plus-enable", "plus-enable")
        _dump_element(driver, By.CLASS_NAME, "realname-popup", "realname-popup")

        print("\n== 可见可点按钮（按文案关键字） ==")
        from selenium.webdriver.common.by import By as _By

        keywords = ["立即购买", "立即预订", "选座购买", "即将开抢", "缺货", "提交缺货登记", "提交订单"]
        for kw in keywords:
            try:
                els = driver.find_elements(_By.XPATH, f"//*[contains(text(),'{kw}')]")
                print(f"  文案「{kw}」: {len(els)} 处")
                for el in els[:6]:
                    try:
                        tag = el.tag_name
                    except Exception:  # noqa: BLE001
                        tag = "?"
                    print(f"      <{tag}> {el.text.strip()[:60]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  文案「{kw}」查询异常: {exc}")

        print("\n== 建议 ==")
        print("核对上面的 class / 文案是否和 ticket_script.py 里的选择器一致；不一致就更新它。")
        return 0
    finally:
        driver.quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="大麦页面选择器校准")
    parser.add_argument("--url", default=None, help="演出详情页 URL（缺省读取 local_config 的 event_url）")
    parser.add_argument("--config", default=None, help="自定义 Concert 配置 JSON")
    parser.add_argument("--headless", action="store_true", help="无头运行")
    parser.add_argument("--wait", type=float, default=4.0, help="等待页面加载秒数")
    args = parser.parse_args(argv)

    cfg = load_concert_config(args.config)
    url = args.url
    if not url:
        url = cfg.get("event_url") or ""
    if not url:
        print("请用 --url 指定演出详情页，或先填写 config/local_config.json 的 event_url。")
        return 1
    return probe(url, args.headless, args.wait, cfg.get("driver_path") or "")


if __name__ == "__main__":
    raise SystemExit(main())
