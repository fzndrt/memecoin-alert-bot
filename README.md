# Memecoin Narrative & Accumulation Alert Bot

Bot pemantau narasi/volume memecoin & altcoin di DexScreener + CoinGecko,
dengan alert otomatis ke Telegram saat sebuah token menunjukkan **kombinasi**
antara pola akumulasi pasar (lonjakan volume, tekanan beli, likuiditas
memadai) **dan** narasi/identitas proyek yang kuat -- website & sosial
media resmi ada, deskripsi proyek jelas, dan mulai banyak orang
membicarakannya (follower/anggota channel & watchlist yang tumbuh).

Sistem ini sengaja MENITIKBERATKAN sinyal narasi, bukan cuma volume --
token yang harganya naik tapi tidak punya identitas/cerita yang jelas
(tanpa website, tanpa sosmed, tanpa deskripsi) akan diberi skor rendah
dan tidak dialert meski volumenya melonjak, sedangkan token dengan
identitas jelas & komunitas yang mulai terbangun akan diprioritaskan dan
ditampilkan lebih dulu.

> ⚠️ **Disclaimer penting**: Ini adalah alat bantu screening berbasis data
> publik, **bukan sinyal trading yang terjamin akurat dan bukan saran
> finansial**. Pasar memecoin sangat volatil dan rawan manipulasi
> (pump-and-dump, wash trading, rug pull). Pengecekan keamanan kontrak
> (GoPlus) bersifat heuristik, bukan jaminan. Selalu DYOR (Do Your Own
> Research) dan jangan menaruh dana lebih dari yang siap Anda hilangkan.

---

## 1. Struktur Proyek

```
memecoin-alert-bot/
├── main.py                 # Entry point: Flask health server + scheduler
├── config.py                # Semua konfigurasi via environment variables
├── state.py                  # Anti-duplikat alert (file JSON lokal)
├── analyzer.py               # Logika filter & scoring "akumulasi"
├── narrative.py               # Skor kekuatan narasi/identitas proyek
├── telegram_alert.py         # Format & kirim pesan Telegram
├── data_sources/
│   ├── dexscreener.py         # DexScreener API (boosts, profiles, pairs)
│   ├── coingecko.py           # CoinGecko trending + lookup contract (gratis)
│   └── social.py              # Twitter/X API (opsional, butuh key berbayar)
├── security/
│   └── goplus.py               # GoPlus Security API (deteksi honeypot dasar)
├── requirements.txt
├── Procfile
├── .env.example
└── .gitignore
```

## 2. Cara Kerja Singkat

1. **Kandidat token** diambil dari endpoint DexScreener `token-boosts` (token
   yang baru dipromosikan) dan `token-profiles` (token baru dengan deskripsi
   proyek) — sumber ini tersedia untuk hampir semua token, termasuk yang
   sangat baru, tanpa perlu API sosial media berbayar.
2. Untuk tiap kandidat, data pair (volume, likuiditas, perubahan harga,
   jumlah transaksi beli/jual) diambil dari DexScreener.
3. **Filter akumulasi pasar** (`analyzer.py`) menyaring token yang: likuiditas
   cukup, volume 1 jam jauh di atas rata-rata per-jam 24 jam (indikasi
   lonjakan baru), rasio beli:jual positif, dan **belum** naik terlalu
   tinggi dalam 24 jam (agar tidak alert setelah pump terjadi).
4. Token yang lolos dicek keamanan dasarnya lewat **GoPlus** (honeypot,
   pajak jual/beli, kontrak mintable, dll).
5. **Skor narasi** (`narrative.py`) dihitung dari dua sumber:
   - Profil DexScreener: ada/tidaknya deskripsi proyek & link resmi
     (website/Twitter/Telegram).
   - CoinGecko (lookup gratis via alamat kontrak, jika token sudah
     terindeks): deskripsi, link resmi, jumlah follower Twitter, anggota
     Telegram, dan `watchlist_portfolio_users` — sinyal kuat "orang mulai
     memantau/membicarakan koin ini" karena datang dari perilaku organik
     pengguna CoinGecko, bukan volume trading semata.
   Token dengan skor di bawah `MIN_NARRATIVE_SCORE` **tidak dialert** —
   ini titik penekanan utama sistem: volume tinggi saja tidak cukup, harus
   dibarengi identitas/narasi yang jelas.
6. Token yang lolos SEMUA tahap di atas diurutkan dari **skor narasi
   tertinggi** → alert dikirim ke Telegram (skor & label kekuatan narasi
   ikut ditampilkan di pesan), dicatat di `state.py` agar tidak dikirim
   berulang dalam periode cooldown.
7. Semua berjalan otomatis lewat scheduler (`APScheduler`) tiap
   `POLL_INTERVAL_MINUTES`.

Semua ambang batas (threshold) bisa diubah lewat environment variable —
lihat `.env.example`.

**Catatan tentang keterbatasan sinyal narasi**: token yang baru berumur
beberapa jam biasanya belum terindeks di CoinGecko, jadi skor narasinya
hanya berasal dari profil DexScreener (deskripsi & link) sampai CoinGecko
mengindeksnya. Ini wajar — artinya sistem ini lebih cocok menangkap token
yang sudah mulai membangun identitas & komunitas (fase "narasi mulai
menyebar"), bukan token yang baru saja di-deploy dalam hitungan menit.

## 3. Setup Bot Telegram

1. Chat `@BotFather` di Telegram → `/newbot` → ikuti instruksi → catat
   **token** yang diberikan (`TELEGRAM_BOT_TOKEN`).
2. Kirim pesan apa saja ke bot Anda (atau tambahkan ke grup/channel Anda).
3. Untuk mendapatkan **chat ID**:
   - Buka `https://api.telegram.org/bot<TOKEN>/getUpdates` di browser
     setelah mengirim pesan ke bot.
   - Cari nilai `"chat":{"id": ...}` pada respons JSON — itulah
     `TELEGRAM_CHAT_ID` Anda (untuk grup, biasanya berupa angka negatif).

## 4. Jalankan di Lokal

```bash
git clone <repo-anda>
cd memecoin-alert-bot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env, isi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID minimal

python main.py
```

Buka `http://localhost:10000/` untuk cek status, atau
`http://localhost:10000/run-now` untuk memicu pipeline manual tanpa menunggu
jadwal scheduler.

## 5. Upload ke GitHub

```bash
git init
git add .
git commit -m "Initial commit: memecoin accumulation alert bot"
git branch -M main
git remote add origin https://github.com/<username>/<repo>.git
git push -u origin main
```

`.env` sudah dimasukkan ke `.gitignore` — **jangan pernah** commit token bot
atau kredensial lain ke repo publik.

## 6. Deploy ke Render

1. Di [Render Dashboard](https://dashboard.render.com/) → **New → Web
   Service** → hubungkan repo GitHub Anda.
2. Konfigurasi:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py` (Render akan otomatis mengenali
     `Procfile`, tapi mengisi Start Command secara eksplisit lebih aman)
3. Tab **Environment** → tambahkan environment variables sesuai
   `.env.example` (minimal `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID`).
   Render menyimpan nilai ini terenkripsi dan tidak menampilkannya di log —
   jangan pernah menaruhnya langsung di kode.
4. Set juga `PORT` — Render biasanya menyuntikkan variabel `PORT` sendiri
   secara otomatis; kode ini sudah membaca `os.getenv("PORT")` lewat
   `config.PORT`, jadi kompatibel dengan itu.
5. Deploy. Setelah live, endpoint root Anda akan berbentuk:
   `https://<nama-service>.onrender.com/`

**Catatan plan Render**: pada instance gratis, layanan akan "tidur" setelah
~15 menit tanpa traffic HTTP masuk (ini alasan langkah UptimeRobot di bawah
diperlukan), dan disk bersifat sementara (state alert bisa hilang saat
restart/redeploy). Untuk kebutuhan produksi jangka panjang, pertimbangkan
plan berbayar atau memindahkan `state.py` ke Redis/DB eksternal.

## 7. Jaga Bot Tetap Aktif dengan UptimeRobot

1. Daftar/masuk ke [UptimeRobot](https://uptimerobot.com/) (ada plan gratis).
2. **Add New Monitor**:
   - Monitor Type: `HTTP(s)`
   - URL: `https://<nama-service>.onrender.com/`
   - Monitoring Interval: `5 menit`
3. Simpan. UptimeRobot akan melakukan ping ke endpoint root setiap 5 menit,
   yang mencegah Render free-tier menidurkan service Anda.

Ping ini hanya menjaga service tetap "bangun" — jadwal deteksi tetap
dikendalikan oleh `POLL_INTERVAL_MINUTES` lewat `APScheduler` di dalam
aplikasi, bukan oleh UptimeRobot.

## 8. Menyesuaikan Kriteria Deteksi

Semua ambang batas ada di `.env` / environment variables Render, contoh:

| Variabel | Default | Arti |
|---|---|---|
| `MIN_LIQUIDITY_USD` | 5000 | Likuiditas minimum pool (USD) |
| `MIN_VOLUME_SPIKE_RATIO` | 3.0 | Vol 1 jam harus ≥ N× rata-rata vol/jam 24h |
| `MAX_PRICE_CHANGE_H24` | 60 | Lewati token yang sudah naik >X% dlm 24 jam |
| `MIN_BUY_SELL_RATIO_H1` | 1.3 | Minimal rasio transaksi beli:jual 1 jam terakhir |
| `MIN_NARRATIVE_SCORE` | 2.5 | Skor narasi minimum agar dialert (naikkan utk lebih ketat) |
| `ALERT_COOLDOWN_HOURS` | 24 | Jeda sebelum token yang sama boleh dialert lagi |

Untuk benar-benar hanya menangkap token dengan narasi **kuat** (bukan
sekadar "ada narasi"), naikkan `MIN_NARRATIVE_SCORE` ke sekitar 5–6 —
lihat `narrative.label_for_score()` di `narrative.py` untuk arti tiap
level skor (Baru mulai / Sedang / Kuat).

Mulai dengan nilai default, lalu sesuaikan berdasarkan seberapa banyak/sedikit
alert yang Anda terima dan seberapa relevan hasilnya.

## 9. Batasan yang Perlu Diketahui

- **Twitter/X**: endpoint pencarian volume tweet terjadwal kini umumnya
  butuh tier API berbayar. `data_sources/social.py` disediakan sebagai
  kerangka opsional (`ENABLE_TWITTER=true` + `TWITTER_BEARER_TOKEN`); tanpa
  itu, sinyal "narasi" diambil dari data boost & profil token DexScreener.
- **Deteksi scam tidak sempurna**: GoPlus membantu menyaring honeypot/pajak
  ekstrem yang jelas, tapi tidak bisa mendeteksi semua bentuk rug pull
  (misalnya liquidity yang bisa ditarik developer meski lolos pengecekan).
- **Rate limit**: DexScreener (~300 req/menit) dan CoinGecko publik
  (~10-30 req/menit) punya batas. Jangan set `POLL_INTERVAL_MINUTES` terlalu
  rendah agar tidak terkena limit.
