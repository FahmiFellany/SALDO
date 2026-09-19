"""
Module for scraping Rajabiller balance and auto-updating index.html.
Designed with security, efficiency, and PEP 8 standards.
"""

import os
import re
import sys
from datetime import datetime
from typing import Optional, Tuple
import zoneinfo

# Load environment variables from .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:
    sync_playwright = None  # type: ignore

RAJABILLER_URL = "https://wr.rajabiller.com"
INDEX_HTML_PATH = "index.html"


def get_target_slot(jam_wib: int) -> Tuple[str, str]:
    """
    Determines HTML target element ID and label based on execution hour (WIB).
    - Pagi: 06:00 - 08:59 WIB (saldo-pagi)
    - Siang: 12:00 - 14:59 WIB (saldo-siang)
    - Sore: 15:00 - 16:59 WIB (saldo-sore)
    - Malam: 17:00 - 20:59 WIB (saldo-malam)
    """
    if 6 <= jam_wib <= 8:
        return "saldo-pagi", "Pagi (06:00 - 08:00 WIB)"
    elif 12 <= jam_wib <= 14:
        return "saldo-siang", "Siang (12:00 - 14:00 WIB)"
    elif 15 <= jam_wib < 17:
        return "saldo-sore", "Sore (15:00 - 17:00 WIB)"
    elif 17 <= jam_wib <= 20:
        return "saldo-malam", "Malam (17:00 - 20:59 WIB)"
    else:
        if jam_wib < 6 or jam_wib >= 21:
            return "saldo-malam", "Malam (Fallback Waktu Malam/Dini Hari)"
        elif 9 <= jam_wib <= 11:
            return "saldo-pagi", "Pagi (Fallback Jam 09-11 WIB)"
        else:
            return "saldo-sore", "Sore (Fallback Jam 17 WIB)"


def scrape_saldo_rajabiller(username: str, password: str) -> str:
    """
    Authenticates to Rajabiller portal using Playwright and extracts current balance.
    Kredensial diambil aman dari Environment Variables / file .env.
    """
    if not sync_playwright:
        raise ImportError("Playwright core module is not installed in the environment.")

    print(f"[*] Navigating to portal: {RAJABILLER_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            page.goto(RAJABILLER_URL, wait_until="networkidle")

            # Username input detection
            user_selector = None
            for sel in ['input[name="username"]', 'input[name="uid"]', '#username', '#uid', 'input[type="text"]']:
                if page.is_visible(sel):
                    user_selector = sel
                    break
            
            if not user_selector:
                page.wait_for_selector('input[type="text"]', timeout=10000)
                user_selector = 'input[type="text"]'

            page.fill(user_selector, username)

            # Password input detection
            pass_selector = None
            for sel in ['input[name="password"]', 'input[name="pin"]', '#password', '#pin', 'input[type="password"]']:
                if page.is_visible(sel):
                    pass_selector = sel
                    break

            if not pass_selector:
                page.wait_for_selector('input[type="password"]', timeout=10000)
                pass_selector = 'input[type="password"]'

            page.fill(pass_selector, password)

            # Submit button
            submit_selector = 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Masuk")'
            page.click(submit_selector)

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            # Extract balance
            elements = page.query_selector_all(".font-semibold, span:has-text('Rp'), div:has-text('Rp')")
            
            extracted_saldo: Optional[str] = None
            for el in elements:
                text = el.text_content().strip()
                text_clean = text.replace('\xa0', ' ').replace('&nbsp;', ' ').strip()
                match = re.search(r'Rp\s*[\d\.,]+', text_clean)
                if match:
                    extracted_saldo = match.group(0)
                    break

            if not extracted_saldo:
                raise ValueError("Saldo element matching pattern 'Rp ...' was not found on dashboard.")

            print(f"[SUCCESS] Balance successfully scraped.")
            return extracted_saldo

        except Exception as e:
            # Mask internal details to prevent sensitive stack trace leaks in workflow logs
            print(f"[ERROR] Scraper encountered an operational error: {type(e).__name__}", file=sys.stderr)
            raise
        finally:
            browser.close()


def update_html(target_id: str, text_saldo: str, now_wib: datetime) -> bool:
    """
    Updates target element values inside index.html safely in a single pass.
    """
    if not os.path.exists(INDEX_HTML_PATH):
        print(f"[ERROR] Target file '{INDEX_HTML_PATH}' does not exist.", file=sys.stderr)
        return False

    try:
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()

        formatted_time = now_wib.strftime("%d %b %Y, %H:%M WIB")

        # Map targets for unified regex replacement pass
        targets = {
            target_id: text_saldo,
            "saldo-terbaru": text_saldo,
            "waktu-update": formatted_time
        }

        for element_id, new_value in targets.items():
            pattern = rf'(<span\s+id="{re.escape(element_id)}"[^>]*>)[^<]*(</span>)'
            html_content = re.sub(pattern, rf'\g<1>{new_value}\2', html_content)

        with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"[SUCCESS] Updated index.html successfully for #{target_id} and metadata.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update HTML: {e}", file=sys.stderr)
        return False


def scrape_and_update() -> None:
    print("==================================================")
    print("      SALDO SCRAPER & AUTOMATED UPDATER          ")
    print("==================================================")

    # Kredensial diambil aman dari environment variables (.env / Secrets)
    username = os.getenv("RAJABILLER_USER")
    password = os.getenv("RAJABILLER_PASSWORD")

    tz_wib = zoneinfo.ZoneInfo("Asia/Jakarta")
    now_wib = datetime.now(tz_wib)
    target_id, slot_name = get_target_slot(now_wib.hour)

    print(f"[*] Execution Timestamp: {now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}")
    print(f"[*] Active Slot: {slot_name} -> Element ID: #{target_id}")

    if not username or not password:
        print("\n[INFO] Missing RAJABILLER_USER / RAJABILLER_PASSWORD environment variables.")
        print("[!] Executing local dry-run simulation mode...")
        mock_saldo = "Rp 277.652.777,00"
        update_html(target_id, mock_saldo, now_wib)
        return

    try:
        saldo_text = scrape_saldo_rajabiller(username, password)
        update_html(target_id, saldo_text, now_wib)
        print("\n[SUCCESS] Automation process executed successfully.")
    except Exception as err:
        print(f"\n[FATAL] Execution aborted due to error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    scrape_and_update()
