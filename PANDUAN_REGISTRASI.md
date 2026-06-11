# 📖 Panduan Registrasi BrainRanger

Panduan untuk menambahkan keluarga baru ke BrainRanger. Ada 3 peran:

| Peran | Siapa | Bisa apa |
|---|---|---|
| 👑 Superadmin | Pemilik bot (Angela) | Buat undangan keluarga, lihat semua keluarga, kontrol cost |
| 👨‍👩‍👧 Parent | Orang tua tiap keluarga | Daftarkan anak, terima laporan belajar anaknya sendiri |
| 🦸 Ranger | Anak | Belajar: /mulai, /latihan, /ulang, /ujian |

---

## Langkah 1 — Superadmin: buat kode undangan

Di chat bot, ketik:

```
/invite
```

Bot membalas dengan kode seperti `BRGR-8FYJFJ`. Kirim kode ini ke orang tua
keluarga baru (via WA/Telegram). **Kode berlaku 7 hari dan hanya bisa dipakai
sekali** — satu kode untuk satu keluarga.

## Langkah 2 — Orang tua: daftar

Minta orang tua keluarga baru:

1. Buka bot BrainRanger di Telegram (kirimkan username bot-nya)
2. Tekan **Start**, lalu ketik:

```
/daftar BRGR-8FYJFJ
```

Selesai — keluarganya langsung terbentuk (plan **trial**). Nama orang tua
diambil otomatis dari profil Telegram-nya.

## Langkah 3 — Orang tua: daftarkan anak

Orang tua ketik:

```
/tambahanak
```

Bot akan bertanya:
1. **Nama anak** — ketik namanya
2. **Jenjang** — pilih 1 (SD kelas 1-3), 2 (SD kelas 4-6), atau 3 (SMP)

Bot lalu memberikan kode seperti `ANAK-K3WM7P`. Bisa diulang untuk anak
berikutnya (maksimal **5 anak per keluarga**).

## Langkah 4 — Anak: gabung

Si anak (di HP/akun Telegram-nya sendiri):

1. Buka bot BrainRanger, tekan **Start**
2. Kirim kodenya sebagai pesan biasa: `ANAK-K3WM7P`

Bot langsung menyambut: anak mendapat warna Ranger otomatis (Merah, Hijau,
Ungu, dst.) dan bisa langsung ketik `/mulai` untuk sesi belajar pertama.

---

## Yang terjadi otomatis setelah keluarga terdaftar

- 🔔 Anak menerima reminder belajar harian (19:00 WIB)
- ⚠️ Jam 20:00 WIB: anak yang belum belajar diingatkan + orang tua dinotif
- 📊 Jam 21:00 WIB: orang tua menerima digest belajar anaknya
- ✅ Setiap anak selesai sesi/ujian/skip → notifikasi ke orang tuanya
- Orang tua bisa cek status kapan saja dengan `/squad`

## Batas pemakaian (plan trial)

Per anak per hari: **3 sesi belajar**, **2 dokumen PDF/Word**, 10 foto per
sesi, 150 evaluasi jawaban. Lewat batas → bot menolak dengan ramah dan anak
tetap bisa `/latihan` & `/ulang` dari bank soal.

## Monitoring untuk superadmin

| Perintah | Fungsi |
|---|---|
| `/squad` | Status semua Ranger di semua keluarga |
| `/usage` | Pemakaian AI & estimasi cost per keluarga (7 hari) |
| `/pause` / `/resume` | Matikan/hidupkan fitur AI manual |
| `/invite` | Buat kode undangan keluarga baru |

Budget otomatis: jika estimasi spend hari ini melewati `DAILY_BUDGET_USD`
(default $2), semua fitur AI pause sendiri sampai besok dan superadmin
mendapat alert.

## Troubleshooting

| Masalah | Solusi |
|---|---|
| "Kode tidak valid atau sudah dipakai" | Kode sekali pakai — buat kode baru (`/invite` atau `/tambahanak`) |
| "Kode sudah kedaluwarsa" | Kode hanya berlaku 7 hari — buat kode baru |
| "Kamu sudah terdaftar" | Satu akun Telegram hanya bisa di satu keluarga |
| Anak salah jenjang | Belum ada perintah edit — hubungi superadmin untuk edit `families.json` |
| Bot tidak merespon | Superadmin: ketik `/restart` |
