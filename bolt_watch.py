#!/usr/bin/env python3
"""Стежить, коли McDonald's (або інший заклад) у Bolt Food знову приймає замовлення.

1) Налаштування (на Mac):  python3 bolt_watch.py --setup
   Відкриється браузер: вкажіть адресу доставки в Боярці, відкрийте McDonald's,
   скопіюйте URL і закрийте вікно. Збережеться bolt_state.json (cookies з адресою).
2a) Локально:        python3 bolt_watch.py "<URL>" [--interval 90]
2b) GitHub Actions:  python3 bolt_watch.py "<URL>" --once  (одна перевірка)

Telegram: змінні TG_TOKEN (від @BotFather) і TG_CHAT_ID.
Cookies: файл bolt_state.json або змінна BOLT_STATE (base64 цього файлу).
"""
import argparse, base64, datetime, os, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_FILE = Path(__file__).with_name("bolt_state.json")
CLOSED = ["зачинено", "закрито", "не приймає", "тимчасово недоступ", "недоступний",
          "closed", "unavailable", "not accepting", "currently not", "opens at", "відкриється"]
OPEN = ["додати в кошик", "до кошика", "add to cart", "add to basket"]


def telegram(msg):
    token, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not (token and chat):
        print("Telegram: TG_TOKEN або TG_CHAT_ID не задано")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=15)
    except Exception as e:
        print(f"Telegram помилка: {e}")
        return False
    return True


def notify(msg):
    telegram(msg)
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg}" with title "Bolt Food" sound name "Glass"'])
        subprocess.run(["say", "Макдональдс знову доступний"], check=False)


def storage_state():
    if os.environ.get("BOLT_STATE"):
        path = Path("/tmp/bolt_state.json") if sys.platform != "win32" else Path("bolt_state.json")
        path.write_bytes(base64.b64decode(os.environ["BOLT_STATE"]))
        return str(path)
    return str(STATE_FILE) if STATE_FILE.exists() else None


def check(page, url):
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    text = page.inner_text("body").lower()
    hit_closed = [w for w in CLOSED if w in text]
    hit_open = [w for w in OPEN if w in text]
    return (not hit_closed), hit_closed, hit_open


def gh_output(key, value):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{key}={value}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default=os.environ.get("BOLT_URL"))
    ap.add_argument("--interval", type=int, default=90, help="секунд між перевірками")
    ap.add_argument("--once", action="store_true", help="одна перевірка (для GitHub Actions)")
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--test", action="store_true", help="лише надіслати тестове повідомлення в Telegram")
    a = ap.parse_args()

    if a.test:
        ok = telegram("✅ Тест: бот Bolt watch працює і зможе вам написати.")
        print("Тестове повідомлення надіслано" if ok else "Не вдалося надіслати")
        sys.exit(0 if ok else 1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.setup)
        ctx = browser.new_context(locale="uk-UA", storage_state=storage_state(),
                                  user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                                             "Chrome/124.0 Safari/537.36")
        page = ctx.new_page()

        if a.setup:
            page.goto("https://food.bolt.eu/uk-UA/")
            print("Вкажіть адресу, відкрийте McDonald's, скопіюйте URL і закрийте вікно.")
            page.wait_for_event("close", timeout=0)
            ctx.storage_state(path=str(STATE_FILE))
            print(f"Збережено {STATE_FILE}. Для GitHub секрету BOLT_STATE:")
            print(f"  base64 -i {STATE_FILE} | pbcopy")
            return
        if not a.url:
            sys.exit("Вкажіть URL сторінки закладу (аргумент або BOLT_URL)")

        if not a.once:
            telegram(f"👀 Почав стежити за McDonald's: {a.url}")
            print(f"Стежу за {a.url} кожні {a.interval} с. Ctrl+C — стоп.")
        while True:
            now = datetime.datetime.now().strftime("%H:%M:%S")
            try:
                ok, closed, opened = check(page, a.url)
            except Exception as e:
                print(f"[{now}] помилка: {e}")
                if a.once:
                    return
                time.sleep(a.interval)
                continue
            if ok:
                print(f"[{now}] ✅ ДОСТУПНИЙ ({opened or 'немає ознак закриття'})")
                notify(f"🍔 McDonald's знову приймає замовлення! {a.url}")
                gh_output("open", "true")
                return
            print(f"[{now}] ще недоступний ({', '.join(closed)})")
            gh_output("open", "false")
            if a.once:
                return
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
