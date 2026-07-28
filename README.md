# SecVault

Gmail va parollarni shifrlab saqlaydigan, terminalda ishlaydigan CLI dastur.
Termux (Android) va oddiy Linux terminalida bir xil ishlaydi, ma'lumotlar
GitHub orqali qurilmalar o'rtasida sinxronlanadi.

## O'rnatish

```bash
pkg install python git      # Termux uchun (Linux'da: apt install python3 git)
git clone git@github.com:fayzillo95/secvault.git
cd secvault
pip install -r requirements.txt
```

## Ishga tushirish

```bash
python3 secvault.py
```

Birinchi marta ishga tushganda:
1. **Seed** (asosiy parol) so'raladi — buni eslab qolish shart, hech qayerda saqlanmaydi.
2. **Tiklash savoli va javobi** so'raladi — Seedni unutib qo'ysangiz, shu javob orqali ham kirish mumkin (ikkalasidan qay biri ham DEK kalitini ochadi).

Keyingi safar ishga tushirilganda Seed (yoki `r` yozib tiklash javobi) so'raladi.

## Menyu

```
1. To'liq list (parollar bilan)
2. Faqat emaillar
3. Masked list       — masalan use...il@gmail.com : ********
4. Yangi akkaunt qo'shish
5. Akkauntni tahrirlash
6. Akkauntni o'chirish
7. GitHub'dan yangilash (pull)
8. GitHub'ga yuborish (push)
0. Chiqish
```

**Muhim:** `add`/`edit`/`delete` faqat lokal faylni yangilaydi. GitHub'ga
yuborish uchun har doim **8-band**ni qo'lda tanlash kerak — bu ataylab shunday
qilingan, chunki avtomatik push muvaffaqiyatsiz bo'lsa, tizim chalkashib
ketishi mumkin edi.

## Xavfsizlik arxitekturasi

- Shifrlash: `cryptography.fernet` (AES asosida), kalit Seed/tiklash-javobidan
  PBKDF2HMAC (SHA256, 390000 iteratsiya) orqali hosil qilinadi.
- Ma'lumotlar bitta tasodifiy **DEK** (data encryption key) bilan shifrlanadi.
  DEK o'zi ikki marta alohida "o'raladi" — biri Seed bilan, biri tiklash
  javobi bilan (`vault.meta.json`). Ikkalasidan qay biri bilan ham ochish
  mumkin.
- `accounts.enc` va `vault.meta.json` — ikkalasi ham git orqali kuzatiladi va
  push qilinadi, lekin ikkalasi ham to'liq shifrlangan holda.
- GitHub repo **albatta private** bo'lishi kerak. Seed va tiklash javobi hech
  qachon fayllarga yozilmaydi — faqat ular orqali hosil qilingan kalitning
  shifrlangan (wrap qilingan) nusxasi saqlanadi.

## Kelajakdagi reja

Hozircha faqat Python (CPython) bilan ishlaydi. Kelajakda vault formati
til-agnostik qilinishi rejalashtirilgan — ya'ni `accounts.enc` va
`vault.meta.json` istalgan qurilmadan yuklab olinib, Python bo'lmasa ham
(masalan boshqa tilda yozilgan mos dastur bilan) decode qilib bo'ladigan
qilib qayta ishlanadi.
