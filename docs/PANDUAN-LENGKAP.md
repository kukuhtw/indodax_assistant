# Panduan Lengkap — Indodax AI Crypto Trading Assistant

Dokumen ini adalah panduan lengkap untuk **instalasi**, **konfigurasi**, **deploy ke VPS**, dan **penggunaan bot di Telegram**. Untuk ringkasan singkat lihat [README.md](../README.md); untuk deploy khusus platform Dokploy lihat [DOKPLOY.md](DOKPLOY.md).

> ⚠️ Aplikasi ini **bukan** penasihat keuangan dan tidak menjanjikan keuntungan. Rekomendasi AI dapat salah. Perdagangan kripto memiliki risiko volatilitas, likuiditas, slippage, dan gangguan API. Saat ini aplikasi **hanya berjalan dalam mode DRY-RUN** (simulasi) — lihat [Batasan mode LIVE](#batasan-mode-live-trading).
>
> **Disclaimer afiliasi:** Proyek ini bersifat independen dan **tidak berafiliasi, tidak bekerja sama, tidak disponsori, serta tidak didukung (endorsed) oleh Indodax / PT Indodax Nasional Indonesia** dalam bentuk apa pun. Nama "Indodax" hanya disebut sebagai referensi karena aplikasi ini memanggil [API publik/privat Indodax](https://github.com/btcid/indodax-official-api-docs) yang tersedia untuk umum sebagai pihak ketiga. Merek dagang "Indodax" adalah milik pemiliknya masing-masing. Pengguna bertanggung jawab penuh atas akun, kredensial API, dan aktivitas trading masing-masing; developer aplikasi ini tidak bertanggung jawab atas kerugian, gangguan, atau perubahan API dari pihak Indodax.

## Daftar isi

1. [Tentang aplikasi](#tentang-aplikasi)
2. [Arsitektur singkat](#arsitektur-singkat)
3. [Prasyarat](#prasyarat)
4. [Instalasi lokal (development)](#instalasi-lokal-development)
5. [Konfigurasi environment (.env)](#konfigurasi-environment-env)
6. [Membuat bot Telegram](#membuat-bot-telegram)
7. [Membuat API key Indodax](#membuat-api-key-indodax)
8. [Deploy ke VPS (manual, Docker Compose)](#deploy-ke-vps-manual-docker-compose)
9. [Deploy via Dokploy](#deploy-via-dokploy)
10. [Cara menggunakan bot di Telegram](#cara-menggunakan-bot-di-telegram)
11. [Alur konfirmasi order](#alur-konfirmasi-order)
12. [Emergency stop dan reset](#emergency-stop-dan-reset)
13. [Batasan mode LIVE trading](#batasan-mode-live-trading)
14. [Operasional: update, backup, monitoring](#operasional-update-backup-monitoring)
15. [Troubleshooting](#troubleshooting)
16. [Keamanan](#keamanan)
17. [Referensi](#referensi)

---

## Tentang aplikasi

Bot Telegram yang memungkinkan pengguna yang di-whitelist untuk:

- Melihat harga dan order book pasar Indodax.
- Melihat saldo dan riwayat order pribadi.
- Meminta rekomendasi trading dari AI (OpenAI) berbasis data pasar terkini.
- Menyiapkan order limit (beli/jual) yang **wajib dikonfirmasi** lewat tombol Telegram sebelum diproses.
- Mengatur batas risiko personal dan menghentikan trading kapan saja (`/pause`, `/stop`).

## Arsitektur singkat

| Komponen | Peran |
|---|---|
| **FastAPI** (`app/main.py`) | Menyediakan endpoint `/health` dan `/ready` untuk pemantauan; menjalankan bot Telegram di dalam lifespan-nya. |
| **python-telegram-bot** (`app/telegram/bot.py`) | Menangani perintah Telegram lewat *long polling* (tidak butuh domain/webhook publik). |
| **PostgreSQL** (`app/database.py`, Alembic) | Menyimpan user, konfigurasi risiko, order, rekomendasi AI, dan audit log. |
| **Redis** | Mengunci proses konfirmasi order agar tidak diproses dobel (`redis.lock`). |
| **httpx → Indodax API** (`app/indodax/client.py`) | Mengambil data publik (ticker, order book, pair info) dan memanggil endpoint privat (saldo, order) dengan HMAC-SHA512. |
| **OpenAI** (`app/ai/advisor.py`) | Menerima data pasar (harga, high/low 24 jam, volume) dan mengembalikan JSON rekomendasi BUY/SELL/HOLD yang divalidasi lewat skema Pydantic. AI **tidak pernah** memegang kredensial broker dan tidak dapat mengeksekusi order. |
| **Risk engine** (`app/trading/risk.py`) | Memvalidasi setiap order terhadap whitelist pair, minimum pasar, increment harga/jumlah, deviasi harga, batas order/posisi/harian, dan status pause/stop — sebelum order bisa "OPEN". |

Pair yang diizinkan dibatasi lewat `PAIR_WHITELIST` (default hanya `btc_idr`).

## Prasyarat

- **Untuk deploy dengan Docker (direkomendasikan):** Docker Engine 24+ dan Docker Compose plugin.
- **Untuk development lokal tanpa Docker:** Python 3.12, PostgreSQL 16, Redis 7.
- Akun Telegram dan akses ke [@BotFather](https://t.me/BotFather).
- Akun Indodax dengan API key (izin **view**, opsional **trade** untuk masa depan — lihat batasan LIVE di bawah).
- (Opsional) API key OpenAI jika ingin fitur `/recommend` aktif.

## Instalasi lokal (development)

### Opsi A — Docker Compose (direkomendasikan)

```bash
git clone <url-repo-anda> indodax_assistant
cd indodax_assistant
cp .env.example .env
# edit .env, isi TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, dst (lihat bagian konfigurasi)
docker compose up --build -d
docker compose logs -f app
```

Compose ini menjalankan tiga service: `app` (FastAPI + bot), `postgres`, `redis`. Saat container `app` start, ia otomatis menjalankan `alembic upgrade head` sebelum menyalakan `uvicorn`. Port aplikasi hanya di-bind ke `127.0.0.1:8000` (tidak diekspos ke jaringan luar secara default).

Cek kesehatan:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

`/ready` harus mengembalikan `status: ok` dengan `database`, `redis`, dan `indodax` berstatus `reachable`.

### Opsi B — Tanpa Docker (Python langsung)

Gunakan opsi ini hanya untuk pengembangan/debugging; Anda harus menyediakan PostgreSQL dan Redis sendiri (lokal atau remote).

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
cp .env.example .env
# edit .env: arahkan DATABASE_URL dan REDIS_URL ke instance lokal Anda

alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Untuk menjalankan test dan lint:

```bash
pytest
ruff check .
python -m compileall app
```

## Konfigurasi environment (.env)

Salin `.env.example` menjadi `.env` dan isi setiap variabel. **Jangan pernah commit `.env`** (sudah masuk `.gitignore`), dan batasi permission file-nya hanya untuk pemilik (`chmod 600 .env` di Linux).

| Variabel | Default | Keterangan |
|---|---|---|
| `APP_ENV` | `development` | Label lingkungan (`development`/`production`), untuk referensi/log saja. |
| `LOG_LEVEL` | `INFO` | Level logging. |
| `TELEGRAM_BOT_TOKEN` | — | Token dari @BotFather. Wajib diisi agar bot aktif. |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Daftar numeric Telegram user ID yang diizinkan, dipisah koma (contoh: `111111,222222`). Wajib diisi agar bot aktif; tanpa ini bot tidak start. |
| `INDODAX_API_KEY` | — | API key Indodax. Gunakan izin **view** saja pada tahap ini. |
| `INDODAX_SECRET_KEY` | — | Secret key Indodax, dipakai untuk HMAC-SHA512 signing. |
| `INDODAX_BASE_URL` | `https://indodax.com` | Base URL API Indodax. |
| `INDODAX_RECV_WINDOW` | `5000` | Jendela waktu (ms) validitas request privat. |
| `TRADING_ENABLED` | `false` | Saklar aplikasi untuk live trading. Lihat [batasan mode LIVE](#batasan-mode-live-trading) — saat ini **selalu diblokir** oleh kode terlepas dari nilai ini. |
| `LIVE_TRADING_CONFIRMATION_REQUIRED` | `true` | Bagian dari syarat `settings.live`; jangan diubah ke `false`. |
| `DRY_RUN` | `true` | Mode simulasi. Biarkan `true` — order dicatat di database tanpa dikirim ke Indodax. |
| `MAX_ORDER_IDR` | `1000000` | Batas nilai per order (IDR) tingkat sistem; juga default per-user (`/setrisk` tidak boleh melebihi ini). |
| `MAX_DAILY_LOSS_IDR` | `100000` | Batas kerugian harian (IDR) sebelum order baru ditolak. |
| `MAX_OPEN_ORDERS` | `5` | Maksimum open order bersamaan per user. |
| `MAX_POSITION_IDR` | `2000000` | Maksimum total nilai posisi (IDR) per user. |
| `MIN_CONFIDENCE` | `0.65` | Ambang confidence AI; di bawah ini rekomendasi otomatis menjadi HOLD. |
| `OPENAI_API_KEY` | — | Kosongkan untuk menonaktifkan `/recommend` (akan selalu balas HOLD "OpenAI API belum dikonfigurasi"). |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model OpenAI yang dipakai untuk rekomendasi. |
| `POSTGRES_PASSWORD` | `change-me` | Password PostgreSQL. **Wajib diganti.** Harus sama dengan password di `DATABASE_URL`. |
| `DATABASE_URL` | `postgresql+asyncpg://trader:change-me@postgres:5432/trading` | Connection string SQLAlchemy async. Jika password mengandung karakter khusus (`@ : / % #`), URL-encode bagian password-nya. |
| `REDIS_URL` | `redis://redis:6379/0` | Connection string Redis. |
| `ORDER_MONITOR_INTERVAL_SECONDS` | `10` | Interval (detik) untuk pemantauan status order (fitur pemantauan penuh belum diimplementasikan). |
| `PAIR_WHITELIST` | `btc_idr` | Pair yang diizinkan, dipisah koma (contoh: `btc_idr,eth_idr`). |

## Membuat bot Telegram

1. Buka chat dengan [@BotFather](https://t.me/BotFather) di Telegram.
2. Kirim `/newbot`, ikuti instruksi: beri nama tampilan, lalu username unik yang diakhiri `bot` (misal `IndodaxAssistantBot`).
3. BotFather akan memberikan **token** berformat `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`. Simpan sebagai `TELEGRAM_BOT_TOKEN`.
4. Dapatkan **numeric Telegram user ID** Anda — chat ke bot seperti [@userinfobot](https://t.me/userinfobot) atau [@RawDataBot](https://t.me/RawDataBot), atau lihat field `id` pada respons `getUpdates`. Isi ke `TELEGRAM_ALLOWED_USER_IDS` (boleh lebih dari satu ID, dipisah koma).
5. (Opsional) Set foto profil dan deskripsi bot lewat BotFather (`/setuserpic`, `/setdescription`).

Bot memakai **long polling**, jadi tidak perlu domain publik, webhook, atau port terbuka ke internet.

## Membuat API key Indodax

1. Login ke akun Indodax → menu **API Management**.
2. Buat API key baru dengan izin **view** (untuk saldo dan status order). Aktifkan **trade** hanya jika Anda berencana pakai fitur order (saat ini order tetap disimulasikan/DRY-RUN oleh aplikasi apa pun izinnya).
3. **Jangan pernah** mengaktifkan izin **withdraw**.
4. Batasi IP jika Indodax menyediakan fitur IP whitelist, isi dengan IP publik VPS Anda.
5. Salin API key dan secret key ke `INDODAX_API_KEY` dan `INDODAX_SECRET_KEY`.

## Deploy ke VPS (manual, Docker Compose)

Panduan ini generik untuk VPS Ubuntu 22.04/24.04 (DigitalOcean, Vultr, Contabo, Biznet, dll). Spesifikasi minimum: 1 vCPU / 1–2 GB RAM.

### 1. Siapkan server

```bash
ssh root@ip-vps-anda
apt update && apt upgrade -y
```

Buat user non-root (opsional tapi disarankan):

```bash
adduser deploy
usermod -aG sudo deploy
su - deploy
```

### 2. Install Docker Engine + Compose plugin

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 3. Amankan firewall

Aplikasi tidak butuh port publik (bot pakai polling, FastAPI hanya untuk health check lokal). Cukup buka port SSH:

```bash
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status
```

**Jangan** membuka port 5432 (PostgreSQL) atau 6379 (Redis) ke internet — di `docker-compose.yml` keduanya memang tidak dipetakan ke host, biarkan seperti itu.

### 4. Ambil kode aplikasi

```bash
git clone <url-repo-anda> /opt/indodax_assistant
cd /opt/indodax_assistant
```

Atau upload lewat `rsync`/`scp` jika tidak memakai Git di server.

### 5. Konfigurasi `.env`

```bash
cp .env.example .env
nano .env      # isi semua variabel — lihat tabel di bagian Konfigurasi
chmod 600 .env
```

Gunakan password PostgreSQL yang kuat dan pastikan sama antara `POSTGRES_PASSWORD` dan bagian password `DATABASE_URL`.

### 6. Jalankan

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Container `app` menjalankan migrasi Alembic otomatis sebelum start. Tunggu hingga `postgres` dan `redis` berstatus `healthy`, lalu `app` running.

### 7. Verifikasi

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Lalu dari Telegram, kirim `/start` ke bot dari akun yang ada di whitelist, dan coba `/price btc_idr`.

### 8. (Opsional) Nginx + HTTPS untuk akses monitoring dari luar

Hanya perlukan ini jika Anda ingin memantau `/health`/`/ready` dari luar server (misalnya lewat uptime monitor eksternal). Bot Telegram sendiri **tidak membutuhkan** ini.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Contoh server block (`/etc/nginx/sites-available/indodax-assistant`):

```nginx
server {
    listen 80;
    server_name monitor.domain-anda.com;

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
    location /ready {
        proxy_pass http://127.0.0.1:8000/ready;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/indodax-assistant /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d monitor.domain-anda.com
sudo ufw allow 'Nginx Full'
```

Jangan expose endpoint lain selain `/health` dan `/ready` — aplikasi tidak punya endpoint publik lain yang aman untuk internet.

### 9. Pastikan otomatis start ulang

`docker-compose.yml` sudah memakai `restart: unless-stopped` untuk semua service. Pastikan service Docker aktif saat boot:

```bash
sudo systemctl enable docker
```

## Deploy via Dokploy

Jika Anda memakai platform [Dokploy](https://dokploy.com/) untuk manajemen deployment (UI web, auto-deploy dari Git, environment editor), ikuti panduan khusus di [`docs/DOKPLOY.md`](DOKPLOY.md). Ringkasnya:

- Buat Service bertipe **Compose** (bukan Docker Stack), arahkan ke `dokploy-compose.yml`.
- Isi semua variabel lewat tab **Environment** Dokploy (menulis `.env` otomatis).
- Jangan tambahkan domain/public port untuk service `app`, `postgres`, atau `redis`.
- Aktifkan **Isolated Deployments** dan atur **Volume Backups** untuk volume `pgdata`.

## Cara menggunakan bot di Telegram

Semua perintah hanya bisa dipakai oleh Telegram user ID yang ada di `TELEGRAM_ALLOWED_USER_IDS`. User lain akan menerima balasan "Akses ditolak."

| Perintah | Format | Keterangan |
|---|---|---|
| `/start` | `/start` | Pesan pembuka dan status mode (DRY-RUN/LIVE). |
| `/help` | `/help` | Menampilkan daftar perintah. |
| `/status` | `/status` | Mode saat ini, status pause, status emergency stop. |
| `/price` | `/price <pair>` | Harga terakhir pair, contoh: `/price btc_idr`. |
| `/orderbook` | `/orderbook <pair>` | 3 bid dan 3 ask teratas. |
| `/balance` | `/balance` | Saldo akun Indodax (butuh `INDODAX_API_KEY`/`SECRET`). |
| `/portfolio` | `/portfolio` | Alias dari `/balance`. |
| `/recommend` | `/recommend <pair>` | Minta rekomendasi AI (BUY/SELL/HOLD) beserta confidence dan alasan. Disimpan ke riwayat `recommendations`. |
| `/buy` | `/buy <pair> <harga> <jumlah>` | Menyiapkan order beli — **butuh konfirmasi** (lihat di bawah). |
| `/sell` | `/sell <pair> <harga> <jumlah>` | Menyiapkan order jual — **butuh konfirmasi**. |
| `/orders` | `/orders` | 10 order terakhir milik Anda beserta status. |
| `/order` | `/order <pair> <id>` | Detail satu order (harga, jumlah, status, broker ID). |
| `/cancel` | `/cancel <pair> <id>` | Membatalkan order **dry-run** yang masih OPEN/PENDING_CONFIRMATION. (Order live belum bisa dibatalkan lewat bot.) |
| `/risk` | `/risk` | Menampilkan batas risiko Anda saat ini. |
| `/setrisk` | `/setrisk <max_order_idr>` | Mengubah batas nilai order maksimum Anda (tidak boleh melebihi `MAX_ORDER_IDR` sistem). |
| `/pause` | `/pause` | Menghentikan sementara order baru (bisa diaktifkan lagi dengan `/resume`). |
| `/resume` | `/resume` | Melanjutkan setelah `/pause` (tidak bisa dipakai setelah `/stop`). |
| `/stop` | `/stop` | **Emergency stop** — lihat bagian khusus di bawah. |

Contoh sesi:

```
/start
/price btc_idr
/recommend btc_idr
/buy btc_idr 950000000 0.0005
   → muncul tombol [CONFIRM] [CANCEL]
   → tekan CONFIRM
/orders
```

## Alur konfirmasi order

1. `/buy` atau `/sell` membuat order dengan status `PENDING_CONFIRMATION` di database dan menampilkan ringkasan (pair, harga, jumlah, nilai total, mode) dengan dua tombol inline: **CONFIRM** dan **CANCEL**.
2. Jika Anda menekan **CANCEL**, order langsung berstatus `CANCELLED`.
3. Jika Anda menekan **CONFIRM**:
   - Aplikasi mengunci proses lewat Redis (`redis.lock`) agar tidak diproses dua kali.
   - Order divalidasi ulang terhadap: whitelist pair, status maintenance pasar, minimum nilai/jumlah pasar, increment harga/jumlah, deviasi harga >20% dari harga terakhir, batas open order, batas kerugian harian, batas posisi, dan saldo yang cukup.
   - Jika lolos validasi dan `DRY_RUN=true` (default), order dicatat sebagai `OPEN` dengan mode `DRY_RUN` — **tidak ada order nyata yang dikirim ke Indodax**.
   - Jika validasi gagal, Anda menerima pesan error spesifik (misalnya "Nilai order melebihi batas", "Saldo IDR tidak cukup", "Batas open order tercapai", dst.) dan order tidak diproses.
4. Cek riwayat kapan saja dengan `/orders` atau detail satu order dengan `/order <pair> <id>`.

## Emergency stop dan reset

- `/pause` menghentikan order baru sementara; bisa dibatalkan dengan `/resume`.
- `/stop` mengaktifkan **emergency stop**: order baru diblokir dan **tidak bisa di-resume lewat bot**. Ini disengaja sebagai pengaman.
- `/stop` **tidak membatalkan** open order yang sudah ada — periksa dan tangani manual lewat `/orders` / `/cancel` (untuk dry-run) atau lewat antarmuka Indodax (untuk order live, yang saat ini tetap tidak pernah tercipta selama live trading dikunci).
- Untuk mereset emergency stop, operator (bukan lewat bot) perlu masuk ke database dan mengatur ulang baris `risk_configs` milik user terkait, misalnya:

```sql
UPDATE risk_configs SET emergency_stop = false, is_paused = false WHERE user_id = <id>;
```

Jalankan ini setelah memastikan penyebab stop sudah ditangani.

## Batasan mode LIVE trading

Aplikasi ini **sengaja mengunci live trading** di level kode (`app/trading/service.py`), terlepas dari nilai `TRADING_ENABLED`/`DRY_RUN` di `.env`, karena komponen berikut belum selesai/diuji:

- Pemantau perubahan status order secara real-time.
- Laporan kerugian harian dan nilai posisi riil (saat ini `daily_loss`/`position_value` di validasi risiko masih `0`).
- Perintah pembatalan order live lewat bot.
- Rekonsiliasi order berstatus `UNKNOWN` (misalnya saat request `trade` timeout — order tidak otomatis dikirim ulang).
- Alur pembatalan massal (`/stop cancel_open_orders`) belum tersedia.

Selama itu, seluruh order yang dikonfirmasi akan tetap berupa **simulasi (DRY-RUN)** memakai saldo dummy, walau kredensial Indodax valid. **Jangan mengaktifkan live trading di lingkungan produksi sebelum item di atas selesai dan diuji.**

## Operasional: update, backup, monitoring

**Update ke versi terbaru:**

```bash
cd /opt/indodax_assistant
git pull
docker compose up --build -d
docker compose logs -f app
```

Migrasi Alembic berjalan otomatis setiap start container.

**Backup database:**

```bash
docker compose exec postgres pg_dump -U trader trading > backup-$(date +%F).sql
```

Simpan file backup di luar VPS (S3, storage terpisah, dsb.). Jika pakai Dokploy, aktifkan fitur **Volume Backups** untuk volume `pgdata` dan uji proses restore-nya secara berkala.

**Monitoring:**

```bash
docker compose ps
docker compose logs -f app
curl http://127.0.0.1:8000/ready
```

Hubungkan `/health` (lewat Nginx bila diperlukan) ke uptime monitor eksternal (UptimeRobot, Better Uptime, dll.) jika ingin notifikasi downtime.

## Troubleshooting

| Gejala | Kemungkinan penyebab / solusi |
|---|---|
| `/ready` mengembalikan `degraded` | Periksa koneksi PostgreSQL, Redis, dan Indodax satu per satu lewat field hasilnya (`database`, `redis`, `indodax`). |
| Bot tidak merespons sama sekali | Periksa `TELEGRAM_BOT_TOKEN` valid, dan pastikan `TELEGRAM_ALLOWED_USER_IDS` tidak kosong (bot tidak start tanpa keduanya) — cek log `docker compose logs app`. |
| "Akses ditolak" | User ID Telegram Anda tidak ada di `TELEGRAM_ALLOWED_USER_IDS`. |
| "Pair tidak diizinkan" | Pair tidak ada di `PAIR_WHITELIST`, atau salah ketik (gunakan format `btc_idr`, huruf kecil). |
| Order ditolak saat CONFIRM | Periksa satu per satu: saldo cukup, nilai order di bawah `max_order_idr`, jumlah/harga sesuai minimum & increment pasar, batas open order, batas posisi, status pause/stop. |
| Status order `UNKNOWN` | Kegagalan koneksi ke Indodax setelah order dikirim (hanya relevan saat live trading, yang saat ini dikunci). Order tidak dikirim ulang otomatis — periksa manual. |
| Container `app` gagal start setelah deploy | Biasanya password database salah/tidak sinkron antara `POSTGRES_PASSWORD` dan `DATABASE_URL`, atau migrasi Alembic gagal — cek `docker compose logs app`. |
| `/recommend` selalu balas HOLD "OpenAI API belum dikonfigurasi" | `OPENAI_API_KEY` kosong di `.env`. |
| Log berisi `telegram.error.Conflict: terminated by other getUpdates request` | Ada **lebih dari satu proses** yang polling dengan `TELEGRAM_BOT_TOKEN` yang sama secara bersamaan — misalnya instance lokal (dev) masih jalan dengan token yang sama seperti di VPS, container lama belum mati saat redeploy, atau ada dua deployment (mis. Dokploy + VPS manual) memakai token yang sama. Pastikan hanya satu container `app` yang aktif (`docker compose ps` / cek di Dokploy), matikan instance duplikat, lalu restart. Error ini biasanya reda sendiri dalam beberapa detik setelah poller lama benar-benar berhenti; jika terus muncul, cek juga bahwa command container memakai `exec uvicorn ...` (bukan `uvicorn ...` tanpa `exec`) agar `SIGTERM` diteruskan dengan benar saat container dihentikan. |

Jalankan test dan lint sebelum deploy perubahan kode:

```bash
pytest
ruff check .
python -m compileall app
```

## Keamanan

- Simpan `.env` di luar version control dan batasi permission filenya.
- Gunakan API key Indodax **tanpa** izin withdraw.
- Wajib isi whitelist ID Telegram — jangan biarkan kosong.
- Jangan expose port PostgreSQL (5432) atau Redis (6379) ke internet.
- Akses FastAPI dari luar (jika ada) harus lewat HTTPS.
- Jika kredensial (Telegram token, Indodax key/secret, OpenAI key) bocor, cabut dan ganti segera.
- Live trading belum siap produksi — lihat [batasan mode LIVE](#batasan-mode-live-trading).

Detail tambahan ada di [SECURITY.md](../SECURITY.md).

## Referensi

- [Indodax Public REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Public-RestAPI.md)
- [Indodax Private REST API](https://github.com/btcid/indodax-official-api-docs/blob/master/Private-RestAPI.md)
- [Dokumentasi Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [Panduan deploy Dokploy](DOKPLOY.md)
