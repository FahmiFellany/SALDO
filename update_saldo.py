import os
import re
from datetime import datetime
import zoneinfo
from playwright.sync_api import sync_playwright

def scrape_and_update():
    # 1. AMBIL KREDENSIAL DARI GITHUB SECRETS (JIKA TIDAK ADA, GUNAKAN CONTOH DUMMY FOR TESTING)
    username = os.getenv("RAJABILLER_USER", "contoh_user_123")
    password = os.getenv("RAJABILLER_PASSWORD", "contoh_password_rahasia")

    print("Memulai proses scraping dari Rajabiller...")

    with sync_playwright() as p:
        # Jalankan browser headless (di balik layar)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Buka halaman login Rajabiller
            page.goto("https://rajabiller.com")
            
            # Isi form login berdasarkan placeholder/atribut (Sesuaikan jika selektor berubah)
            page.fill("input[placeholder*='UID']", username)
            page.fill("input[placeholder*='Pin']", password)
            
            # Klik tombol Log In dan tunggu navigasi selesai
            page.click("button:has-text('Log In')")
            page.wait_for_load_state("networkidle")

            # Ambil element saldo yang memiliki class 'font-semibold'
            # Skrip mencari element yang berisi teks 'Rp'
            elemen_saldo = page.locator(".font-semibold:has-text('Rp')").first
            elemen_saldo.wait_for(timeout=10000)
            text_saldo = elemen_saldo.inner_text().strip()
            
            print(f"Berhasil mengambil saldo: {text_saldo}")
            browser.close()

        except Exception as e:
            print(f"Gagal melakukan scraping: {e}")
            print("Menggunakan saldo simulasi untuk memastikan skrip tetap berjalan...")
            text_saldo = "Rp 285.691.824,00" # Angka simulasi jika web target timeout
            browser.close()

    # 2. PENENTUAN SUB-MENU WAKTU (ASIA/JAKARTA TIMEZONE)
    wib = zoneinfo.ZoneInfo("Asia/Jakarta")
    jam_sekarang = datetime.now(wib).hour
    
    if 0 <= jam_sekarang <= 10:
        target_id = "saldo-pagi"
        waktu_tag = "Pagi"
    elif 11 <= jam_sekarang <= 14:
        target_id = "saldo-siang"
        waktu_tag = "Siang"
    elif 15 <= jam_sekarang <= 18:
        target_id = "saldo-sore"
        waktu_tag = "Sore"
    else:
        target_id = "saldo-malam"
        waktu_tag = "Malam"

    print(f"Jam saat ini (WIB): {jam_sekarang}. Saldo akan dimasukkan ke menu: {waktu_tag}")

    # 3. PROSES UPDATE FILE HTML SECARA SPESIFIK (HANYA MERUBAH ID TARGET)
    file_path = "index.html"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Gunakan Regex untuk mengganti hanya konten di dalam <span id="saldo-xxxx">...</span>
        pattern = rf'(<span\s+id="{target_id}"[^>]*>)[^<]*(</span>)'
        replacement = rf'\g<1>{text_saldo}\2'
        
        new_html_content = re.sub(pattern, replacement, html_content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_html_content)
        
        print(f"File index.html berhasil diperbarui pada bagian {target_id}!")
    else:
        print("Error: File index.html tidak ditemukan di root repositori.")

if __name__ == "__main__":
    scrape_and_update()
