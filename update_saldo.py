import os
import re
from datetime import datetime
import zoneinfo
from playwright.sync_api import sync_playwright

def scrape_and_update():
    # 1. AMBIL KREDENSIAL DARI GITHUB SECRETS
    username = os.getenv("RAJABILLER_USER")
    password = os.getenv("RAJABILLER_PASSWORD")

    if not username or not password:
        print("Error: Kredensial RAJABILLER_USER atau RAJABILLER_PASSWORD tidak ditemukan di Environment Variables.")
        return

    print("Memulai proses scraping dari Rajabiller...")
    text_saldo = None

    with sync_playwright() as p:
        # Jalankan browser headless di server cloud
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Akses halaman login Rajabiller Web Report
            page.goto("https://rajabiller.com")
            
            # Mengisi form login (Menyesuaikan selektor form login Rajabiller)
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            
            # Klik tombol login dan tunggu halaman memuat dashboard utama
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")

            # Mengambil element dengan class 'font-semibold' yang menampung informasi saldo
            elemen_saldo = page.locator(".font-semibold").first
            elemen_saldo.wait_for(timeout=15000)
            text_saldo = elemen_saldo.inner_text().strip()
            
            print(f"Berhasil mengekstrak data saldo: {text_saldo}")
            browser.close()

        except Exception as e:
            print(f"Proses scraping gagal atau timeout: {e}")
            browser.close()
            return

    # 2. LOGIKA PENENTUAN SUB-MENU WAKTU BERDASARKAN UTC KE ASIA/JAKARTA (WIB)
    wib = zoneinfo.ZoneInfo("Asia/Jakarta")
    jam_sekarang = datetime.now(wib).hour
    
    # Menentukan target ID berdasarkan parameter jam yang diminta
    if 6 <= jam_sekarang <= 8:
        target_id = "saldo-pagi"
        waktu_tag = "Pagi"
    elif 12 <= jam_sekarang <= 14:
        target_id = "saldo-siang"
        waktu_tag = "Siang"
    elif 15 <= jam_sekarang <= 17:
        target_id = "saldo-sore"
        waktu_tag = "Sore"
    elif 18 <= jam_sekarang <= 20:
        target_id = "saldo-malam"
        waktu_tag = "Malam"
    else:
        print(f"Jam saat ini ({jam_sekarang}:00 WIB) di luar rentang jadwal update. Proses dilewati.")
        return

    print(f"Waktu eksekusi: Pukul {jam_sekarang} WIB. Target menu: {waktu_tag}")

    # 3. MEMPERBARUI NILAI HTML SECARA SPESIFIK MENGGUNAKAN REGEX PENANDA ID
    file_path = "index.html"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Regex ini hanya mendeteksi dan mengganti teks di dalam ID saldo terpilih
        pattern = rf'(<span\s+id="{target_id}"[^>]*>)[^<]*(</span>)'
        replacement = rf'\g<1>{text_saldo}\2'
        
        new_html_content = re.sub(pattern, replacement, html_content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_html_content)
        
        print(f"Berkas index.html berhasil diperbarui pada elemen target #{target_id}!")
    else:
        print("Error: Berkas index.html tidak ditemukan di root repositori.")

if __name__ == "__main__":
    scrape_and_update()
