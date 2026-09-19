import os
import re
import sys
from datetime import datetime
import zoneinfo
try:
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:
    sync_playwright = None  # type: ignore

RAJABILLER_URL = "https://wr.rajabiller.com"

def get_target_slot(jam_wib: int) -> tuple[str, str]:
    """
    Menentukan ID elemen HTML berdasarkan jam WIB saat skrip dieksekusi:
    - Pagi: 06:00 - 08:00 WIB (saldo-pagi)
    - Siang: 12:00 - 14:00 WIB (saldo-siang)
    - Sore: 15:00 - 16:59 WIB (saldo-sore)
    - Malam: 17:00 - 20:59 WIB (saldo-malam)
    - Fallback: Memastikan eksekusi manual via workflow_dispatch selalu memperbarui slot yang sesuai.
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
    if not sync_playwright:
        raise ImportError("Modul 'playwright' belum terinstall di lingkungan ini. Silakan jalankan 'pip install playwright'.")

    print(f"[*] Membuka {RAJABILLER_URL} dengan Playwright Headless Browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            print(f"[*] Navigasi ke {RAJABILLER_URL}...")
            page.goto(RAJABILLER_URL, wait_until="networkidle")

            # Deteksi input Username / UID
            user_selector = None
            for sel in ['input[name="username"]', 'input[name="uid"]', '#username', '#uid', 'input[type="text"]']:
                if page.is_visible(sel):
                    user_selector = sel
                    break
            
            if not user_selector:
                page.wait_for_selector('input[type="text"]', timeout=10000)
                user_selector = 'input[type="text"]'

            print(f"[*] Memasukkan Username/UID ke selector '{user_selector}'...")
            page.fill(user_selector, username)

            # Deteksi input Password / PIN
            pass_selector = None
            for sel in ['input[name="password"]', 'input[name="pin"]', '#password', '#pin', 'input[type="password"]']:
                if page.is_visible(sel):
                    pass_selector = sel
                    break

            if not pass_selector:
                page.wait_for_selector('input[type="password"]', timeout=10000)
                pass_selector = 'input[type="password"]'

            print(f"[*] Memasukkan Password/PIN ke selector '{pass_selector}'...")
            page.fill(pass_selector, password)

            # Deteksi tombol submit
            submit_selector = 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Masuk")'
            print("[*] Menekan tombol Login...")
            page.click(submit_selector)

            # Tunggu loading dashboard / navigasi
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            print("[*] Mencari elemen saldo (class 'font-semibold')...")
            # Ambil semua elemen dengan class 'font-semibold'
            elements = page.query_selector_all(".font-semibold")
            
            extracted_saldo = None
            for el in elements:
                text = el.text_content().strip()
                # Bersihkan non-breaking space (&nbsp; / \xa0)
                text_clean = text.replace('\xa0', ' ').replace('&nbsp;', ' ').strip()
                
                if "Rp" in text_clean:
                    print(f"    -> Ditemukan calon saldo: '{text_clean}'")
                    extracted_saldo = text_clean
                    break

            if not extracted_saldo:
                raise ValueError("Elemen saldo dengan class 'font-semibold' berformat 'Rp ...' tidak ditemukan pada dashboard.")

            print(f"[SUCCESS] Saldo berhasil diekstrak: {extracted_saldo}")
            return extracted_saldo

        except Exception as e:
            print(f"[ERROR] Gagal/Timeout saat scraping Rajabiller: {e}", file=sys.stderr)
            raise
        finally:
            browser.close()

def update_html(target_id: str, text_saldo: str, now_wib: datetime):
    file_path = "index.html"
    if not os.path.exists(file_path):
        print(f"[ERROR] Berkas {file_path} tidak ditemukan.", file=sys.stderr)
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    formatted_time = now_wib.strftime("%d %b %Y, %H:%M WIB")

    # 1. Update slot spesifik (saldo-pagi, saldo-siang, saldo-sore, saldo-malam)
    pattern_slot = rf'(<span\s+id="{target_id}"[^>]*>)[^<]*(</span>)'
    if re.search(pattern_slot, html_content):
        html_content = re.sub(pattern_slot, rf'\g<1>{text_saldo}\2', html_content)

    # 2. Update saldo-terbaru (Hero Banner Utama)
    pattern_terbaru = rf'(<span\s+id="saldo-terbaru"[^>]*>)[^<]*(</span>)'
    if re.search(pattern_terbaru, html_content):
        html_content = re.sub(pattern_terbaru, rf'\g<1>{text_saldo}\2', html_content)

    # 3. Update waktu-update (Timestamp Scrape)
    pattern_waktu = rf'(<span\s+id="waktu-update"[^>]*>)[^<]*(</span>)'
    if re.search(pattern_waktu, html_content):
        html_content = re.sub(pattern_waktu, rf'\g<1>{formatted_time}\2', html_content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[SUCCESS] Berkas index.html berhasil diperbarui untuk #{target_id}, #saldo-terbaru ('{text_saldo}'), dan #waktu-update ('{formatted_time}').")
    return True

def scrape_and_update():
    print("==================================================")
    print("      SALDO SCRAPER & AUTOMATED UPDATER          ")
    print("==================================================")

    username = os.getenv("RAJABILLER_USER")
    password = os.getenv("RAJABILLER_PASSWORD")

    wib = zoneinfo.ZoneInfo("Asia/Jakarta")
    now_wib = datetime.now(wib)
    jam_sekarang = now_wib.hour
    target_id, slot_name = get_target_slot(jam_sekarang)

    print(f"[*] Waktu Eksekusi (WIB): {now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')}")
    print(f"[*] Target Sub-Menu Slot: {slot_name} -> ID: #{target_id}")

    if not username or not password:
        print("\n[WARNING] Kredensial RAJABILLER_USER / RAJABILLER_PASSWORD tidak ditemukan di Environment Variables!")
        print("[!] Mode Simulasi Dry-Run untuk pengujian struktur HTML lokal...")
        mock_saldo = "Rp 277.652.777,00"
        print(f"[*] Memperbarui index.html dengan nilai simulasi: {mock_saldo}")
        update_html(target_id, mock_saldo, now_wib)
        return

    try:
        saldo_text = scrape_saldo_rajabiller(username, password)
        update_html(target_id, saldo_text, now_wib)
        print("\n[SUCCESS] Seluruh proses scraping dan pembaruan saldo selesai.")
    except Exception as err:
        print(f"\n[FATAL ERROR] Gagal memperbarui saldo: {err}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    scrape_and_update()
