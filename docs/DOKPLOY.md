# Deploy dry-run di Dokploy

Gunakan **Docker Compose** dari Git repository, bukan Docker Stack. Pada Dokploy, buat Project dan Service bertipe **Compose**, pilih repository dan branch, lalu isi **Compose Path** `./dokploy-compose.yml`. Dokploy mendukung build dari `Dockerfile` pada Compose dan menyediakan editor Environment. Jangan menambahkan domain atau public port: bot memakai Telegram long polling, sementara FastAPI hanya dipakai untuk health check internal.

## Environment

Di tab **Environment** Dokploy, isi seluruh variabel di bawah sebagai baris `KEY=value`. Dokploy menulisnya ke `.env` di direktori Compose dan `env_file: .env` memasukkannya ke container app. Gunakan nilai rahasia milik Anda sendiri; jangan commit `.env`.

```env
APP_ENV=production
TELEGRAM_BOT_TOKEN=isi-token-bot
TELEGRAM_ALLOWED_USER_IDS=isi-id-numerik-telegram
INDODAX_API_KEY=isi-api-key-view-only
INDODAX_SECRET_KEY=isi-secret-key
INDODAX_BASE_URL=https://indodax.com
INDODAX_RECV_WINDOW=5000
TRADING_ENABLED=false
LIVE_TRADING_CONFIRMATION_REQUIRED=true
DRY_RUN=true
MAX_ORDER_IDR=1000000
MAX_DAILY_LOSS_IDR=100000
MAX_OPEN_ORDERS=5
MAX_POSITION_IDR=2000000
MIN_CONFIDENCE=0.65
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
POSTGRES_PASSWORD=isi-password-kuat
DATABASE_URL=postgresql+asyncpg://trader:isi-password-kuat@postgres:5432/trading
REDIS_URL=redis://redis:6379/0
ORDER_MONITOR_INTERVAL_SECONDS=10
PAIR_WHITELIST=btc_idr
```

`POSTGRES_PASSWORD` dan password di `DATABASE_URL` harus sama. Jika password mengandung karakter khusus URL (`@`, `:`, `/`, `%`, `#`), URL-encode bagian password pada `DATABASE_URL`. Gunakan API key Indodax dengan izin **view** saja untuk deployment saat ini dan tanpa izin withdrawal. Live trading masih dikunci dalam aplikasi.

## Deploy dan verifikasi

1. Aktifkan **Isolated Deployments** pada service Compose bila tersedia; fitur ini memberi jaringan terpisah. Jangan menambahkan domain untuk app, PostgreSQL, atau Redis.
2. Klik **Deploy**. Saat startup, container app menjalankan migrasi Alembic sebelum FastAPI dan bot aktif.
3. Di tab **Logs**, pastikan `postgres` dan `redis` healthy, migrasi berhasil, lalu `app` healthy. Jika app gagal, periksa password database dan `DATABASE_URL`.
4. Kirim `/start` ke bot dari ID yang diizinkan, lalu `/price btc_idr`. Coba `/buy btc_idr <harga> <jumlah>` dengan nilai kecil dan periksa bahwa hasilnya bertanda **DRY-RUN** setelah CONFIRM. Jangan gunakan uang nyata untuk uji ini.
5. Untuk memeriksa `/ready`, jalankan dari terminal container app: `python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"`. Status harus `ok` dengan database, redis, dan Indodax `reachable`.

Volume bernama `pgdata` menyimpan database antar deploy. Atur **Volume Backups** Dokploy untuk volume PostgreSQL dan uji pemulihannya. Jangan menghapus volume saat redeploy. Redis tidak menyimpan order; semua order dan audit disimpan di PostgreSQL.

## Batasan saat ini

Deployment ini khusus dry-run. Pemantauan status order, pembatalan order live, perhitungan kerugian harian dan posisi riil, serta rekonsiliasi order yang tidak pasti belum selesai. Mengubah variabel live tidak membuka pengiriman order nyata.
