# Keamanan

Simpan `.env` di luar Git dan batasi izinnya. Gunakan API key Indodax tanpa izin withdrawal. Whitelist ID numerik Telegram wajib diisi. Jangan buka port PostgreSQL atau Redis ke internet. Akses FastAPI dari luar harus melalui HTTPS. Jika kunci bocor, cabut dan ganti segera. Live trading belum siap untuk produksi karena batasan yang dijelaskan di README.

Proyek ini independen dan tidak berafiliasi, tidak bekerja sama, serta tidak didukung oleh Indodax. Aplikasi hanya bertindak sebagai klien pihak ketiga terhadap API publik/privat Indodax menggunakan kredensial milik pengguna sendiri.
