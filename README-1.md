# SUMATERA MENFESS BOT

Bot Telegram menfess anonim dengan moderasi otomatis, sistem balas/like/report,
anti-spam, dan panel admin.

## Fitur

- Kirim menfess anonim: `#sumboy @username <pesan>` atau `#sumgirl @username <pesan>`
- Avatar otomatis sesuai kategori (biru untuk #sumboy, pink untuk #sumgirl)
- Menfess tayang di channel DAN dikirim sebagai DM ke penerima (jika penerima
  sudah pernah `/start` bot)
- Tombol ❤️ Like, 💬 Balas (anonim, via deep-link), 🚩 Report
- Tanpa moderasi otomatis — semua menfess langsung tayang. Kontrol konten
  sepenuhnya manual lewat sistem Report: admin bisa hapus menfess dan/atau
  ban pengirimnya dari tombol report yang masuk
- Anti-spam: batas jumlah kirim per jam + jeda minimal antar kirim (`config.py`)
- Panel admin `/admin`: statistik, reports pending, daftar banned + unban
- `/broadcast <pesan>` untuk kirim pengumuman ke semua user terdaftar

## Environment Variables

| Variable | Keterangan |
|---|---|
| `BOT_TOKEN` | Token dari @BotFather |
| `CHANNEL_ID` | Username (`@nama_channel`) atau chat id channel tujuan |
| `BOT_USERNAME` | Username bot tanpa `@`, contoh `SUMATERA_MENFESS_BOT` |
| `ADMIN_IDS` | Telegram user ID admin, pisahkan koma. Contoh: `111111,222222` |
| `RATE_LIMIT_MAX_PER_HOUR` | Default `5` |
| `RATE_LIMIT_MIN_INTERVAL_SECONDS` | Default `30` |

Cara cek Telegram user ID kamu sendiri: chat ke bot `@userinfobot`.

## Catatan penting

- **Tanpa moderasi otomatis.** Semua menfess langsung tayang begitu dikirim.
  Kalau ada yang bermasalah, penerima/pembaca channel bisa tekan 🚩 Report,
  lalu admin memutuskan lewat panel `/admin` (hapus menfess dan/atau ban
  pengirim).
- **Fitur Balas** memakai deep-link (`t.me/BOTUSERNAME?start=reply_<id>`)
  karena bot tidak bisa membalas user secara langsung dari tombol channel.
- Database SQLite (`menfess.db`) bersifat lokal — kalau deploy ke platform
  dengan filesystem ephemeral (Render, Railway, dst), tambahkan persistent
  disk supaya data user/menfess/report tidak hilang saat redeploy.
- Admin harus pernah `/start` bot ini sendiri agar bisa menerima notifikasi
  menfess pending & report.
