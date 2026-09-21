# Indodax AI Crypto Trading Assistant

Bot Telegram untuk melihat pasar Indodax, meminta rekomendasi AI, dan menyiapkan limit order dengan konfirmasi. Ini bukan penasihat keuangan dan tidak menjanjikan keuntungan. Rekomendasi dapat salah; perdagangan memiliki risiko volatilitas, likuiditas, slippage, dan gangguan API.

> **Disclaimer:** Proyek ini **independen** dan **tidak berafiliasi, tidak bekerja sama, tidak disponsori, dan tidak didukung (endorsed)** oleh PT Indodax Nasional Indonesia atau Indodax dalam bentuk apa pun. "Indodax" adalah merek dagang milik pemiliknya masing-masing dan disebut di sini semata untuk interoperabilitas, karena aplikasi ini memanggil [API publik Indodax](https://github.com/btcid/indodax-official-api-docs) yang tersedia untuk umum. Segala risiko penggunaan API pihak ketiga, termasuk perubahan atau gangguan API tanpa pemberitahuan, ditanggung sendiri oleh pengguna.

## Dokumentasi

Panduan lengkap instalasi, konfigurasi, deploy ke VPS, dan cara pakai di Telegram: [docs/PANDUAN-LENGKAP.md](docs/PANDUAN-LENGKAP.md).

## Menjalankan

Untuk Dokploy, gunakan [panduan deployment](docs/DOKPLOY.md) dan `dokploy-compose.yml`.

1. Buat bot melalui `@BotFather` dan catat tokennya. Dapatkan numeric Telegram user ID Anda.
2. Buat API key Indodax dengan izin **view** dan, hanya jika akan memakai live trading, **trade**. Jangan aktifkan izin **withdraw**.
3. Salin `.env.example` menjadi `.env`. Isi token, whitelist ID, API key, dan secret. Ubah `POSTGRES_PASSWORD` dan samakan password pada `DATABASE_URL`. Batasi izin file `.env` hanya untuk pemiliknya.
4. Jalankan `docker compose up --build -d`. Periksa `http://127.0.0.1:8000/health` dan `/ready`. Port aplikasi hanya terikat ke localhost; gunakan Nginx dan HTTPS bila perlu akses dari luar.

Default `DRY_RUN=true` dan `TRADING_ENABLED=false`. Live trading saat ini dikunci oleh aplikasi, termasuk jika `DRY_RUN=false` dan `TRADING_ENABLED=true`, karena batas risiko riil dan rekonsiliasi belum selesai. Setiap order dry-run memerlukan tombol CONFIRM.

## Perintah

`/start`, `/help`, `/status`, `/price btc_idr`, `/orderbook btc_idr`, `/balance`, `/portfolio`, `/recommend btc_idr`, `/buy btc_idr 100000000 0.001`, `/sell btc_idr 120000000 0.001`, `/orders`, `/risk`, `/setrisk 500000`, `/pause`, `/resume`, `/stop`.

`/buy` dan `/sell` juga menerima nominal Rupiah langsung, jumlah koin dihitung otomatis: `/buy btc_idr 100000000 idr 500000`.

`/stop` memblokir order baru dan tidak membatalkan open order. Periksa `/orders` untuk meninjau posisi. Emergency stop tidak dapat dihapus lewat bot; operator harus memeriksa keadaan dan meresetnya secara administratif.

## Arsitektur dan batasan

FastAPI menyediakan health check, bot Telegram memakai polling, PostgreSQL menyimpan order dan audit, Redis mengunci konfirmasi, dan `httpx` mengakses Indodax. AI hanya menerima data pasar dan mengembalikan JSON yang divalidasi; tidak memegang kunci broker. Pair awal dibatasi dengan `PAIR_WHITELIST=btc_idr`. Dry run menggunakan saldo simulasi dan tidak mengirim order.

**Belum lengkap untuk produksi live:** pemantau perubahan status order, laporan kerugian harian dan nilai posisi riil, perintah pembatalan order live, dan rekonsiliasi order UNKNOWN. Karena itu jangan aktifkan live trading sebelum komponen tersebut selesai dan diuji. Order UNKNOWN tidak dikirim ulang otomatis. Alur pembatalan massal `/stop cancel_open_orders` belum tersedia.

## Pengujian dan masalah umum

Jalankan `pytest`, `ruff check .`, dan `python -m compileall app`. Jika `/ready` degraded, periksa koneksi PostgreSQL, Redis, dan Indodax. Jika bot tidak merespons, periksa token dan `TELEGRAM_ALLOWED_USER_IDS`. Jika order ditolak, periksa whitelist pair, saldo, minimum serta increment pair, dan batas risiko. Kegagalan API setelah submit menghasilkan status UNKNOWN untuk diperiksa manual.

Dokumentasi resmi: [Public REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md) dan [Private REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md).
