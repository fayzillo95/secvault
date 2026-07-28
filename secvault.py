#!/usr/bin/env python3
import base64
import json
import os
import subprocess
import sys
import threading
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(REPO_DIR, "vault.meta.json")
DATA_PATH = os.path.join(REPO_DIR, "accounts.enc")
RESULT_PATH = os.path.join(REPO_DIR, "result.json")
PBKDF2_ITERATIONS = 390_000
RESULT_TTL_SECONDS = 120


def derive_key(secret: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def load_meta() -> dict:
    with open(META_PATH, "r") as f:
        return json.load(f)


def save_meta(meta: dict) -> None:
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def load_accounts(dek: bytes) -> dict:
    if not os.path.exists(DATA_PATH) or os.path.getsize(DATA_PATH) == 0:
        return {}
    with open(DATA_PATH, "rb") as f:
        token = f.read()
    raw = Fernet(dek).decrypt(token)
    return json.loads(raw.decode())


def save_accounts(dek: bytes, accounts: dict) -> None:
    raw = json.dumps(accounts).encode()
    token = Fernet(dek).encrypt(raw)
    with open(DATA_PATH, "wb") as f:
        f.write(token)


def push_to_github() -> None:
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print("Bu papka git repo emas, push qilib bo'lmaydi.\n")
        return
    subprocess.run(["git", "add", "accounts.enc", "vault.meta.json"], cwd=REPO_DIR)
    message = f"update: {datetime.now():%Y-%m-%d %H:%M}"
    commit = subprocess.run(["git", "commit", "-m", message], cwd=REPO_DIR, capture_output=True, text=True)
    if commit.returncode != 0:
        if "nothing to commit" in commit.stdout.lower():
            print("Push qilinadigan yangi o'zgarish yo'q.\n")
            return
        print(f"Xatolik: commit qilinmadi -> {commit.stdout.strip()}\n")
        return
    push = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True)
    if push.returncode != 0:
        print(f"Xatolik: push muvaffaqiyatsiz -> {push.stderr.strip()}")
        print("O'zgarish lokal commit qilindi, keyinroq qaytadan push qilib ko'ring.\n")
    else:
        print("GitHub'ga muvaffaqiyatli push qilindi.\n")


def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 5:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:3] + "..." + local[-2:]
    return f"{masked_local}@{domain}"


def run_init():
    print("=== Vault birinchi marta sozlanmoqda ===")
    while True:
        seed = input("Yangi Seed (asosiy parol) o'ylab toping: ")
        seed_confirm = input("Seedni qayta kiriting: ")
        if seed == seed_confirm and seed:
            break
        print("Seedlar mos kelmadi yoki bo'sh, qaytadan urinib ko'ring.\n")

    question = input("Tiklash savolini kiriting (masalan: Birinchi telefon raqamingiz?): ")
    answer = input("Tiklash javobini kiriting: ")

    dek = Fernet.generate_key()
    salt_seed = os.urandom(16)
    salt_recovery = os.urandom(16)

    meta = {
        "salt_seed": base64.b64encode(salt_seed).decode(),
        "wrapped_key_seed": Fernet(derive_key(seed, salt_seed)).encrypt(dek).decode(),
        "recovery_question": question,
        "salt_recovery": base64.b64encode(salt_recovery).decode(),
        "wrapped_key_recovery": Fernet(derive_key(answer, salt_recovery)).encrypt(dek).decode(),
    }
    save_meta(meta)
    save_accounts(dek, {})
    print("\nVault muvaffaqiyatli yaratildi.")
    print("MUHIM: Seed va tiklash javobini xavfsiz joyda saqlang, ular hech qayerda saqlanmaydi.")
    print("Eslatma: GitHub'ga yuborish uchun menyudan 'Push' bo'limini tanlang.\n")
    return dek


def unlock() -> bytes:
    meta = load_meta()
    choice = input("Seedni kiriting (tiklash uchun 'r' yozing): ")
    if choice == "r":
        print(f"Tiklash savoli: {meta['recovery_question']}")
        secret = input("Javobni kiriting: ")
        salt = base64.b64decode(meta["salt_recovery"])
        wrapped = meta["wrapped_key_recovery"]
        label = "Javob"
    else:
        secret = choice
        salt = base64.b64decode(meta["salt_seed"])
        wrapped = meta["wrapped_key_seed"]
        label = "Seed"

    key = derive_key(secret, salt)
    try:
        return Fernet(key).decrypt(wrapped.encode())
    except InvalidToken:
        print(f"Xatolik: Noto'g'ri {label}.")
        sys.exit(1)


def action_add(dek, accounts):
    email = input("Gmail: ").strip()
    if email in accounts:
        print("Bu email allaqachon mavjud, 'Tahrirlash' bo'limidan foydalaning.")
        return
    password = input("Parol: ")
    accounts[email] = password
    save_accounts(dek, accounts)
    print(f"'{email}' qo'shildi. (GitHub'ga yuborish uchun 'Push' bo'limini tanlang)")


def action_edit(dek, accounts):
    email = input("O'zgartiriladigan Gmail: ").strip()
    if email not in accounts:
        print("Bunday email topilmadi.")
        return
    new_password = input("Yangi parol: ")
    accounts[email] = new_password
    save_accounts(dek, accounts)
    print(f"'{email}' uchun parol yangilandi. (GitHub'ga yuborish uchun 'Push' bo'limini tanlang)")


def action_delete(dek, accounts):
    email = input("O'chiriladigan Gmail: ").strip()
    if email not in accounts:
        print("Bunday email topilmadi.")
        return
    confirm = input(f"'{email}' rostdan ham o'chirilsinmi? (ha/yo'q): ").strip().lower()
    if confirm != "ha":
        print("Bekor qilindi.")
        return
    del accounts[email]
    save_accounts(dek, accounts)
    print(f"'{email}' o'chirildi. (GitHub'ga yuborish uchun 'Push' bo'limini tanlang)")


def show_list(accounts, mode):
    if not accounts:
        print("Vault bo'sh.\n")
        return
    print(f"\nJami akkauntlar: {len(accounts)}")
    if mode == "full":
        for email, password in accounts.items():
            print(f"  {email} : {password}")
    elif mode == "emails":
        for email in accounts:
            print(f"  {email}")
    else:
        for email, password in accounts.items():
            print(f"  {mask_email(email)} : {'*' * len(password)}")
    print()


def export_full_list(accounts):
    if not accounts:
        print("Vault bo'sh, eksport qilinadigan narsa yo'q.\n")
        return None
    with open(RESULT_PATH, "w") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"To'liq list (ochiq parollar bilan) '{RESULT_PATH}' fayliga yozildi.")
    print(f"OGOHLANTIRISH: bu fayl SHIFRLANMAGAN. {RESULT_TTL_SECONDS} soniyadan so'ng yoki "
          "dasturdan chiqishda avtomatik o'chiriladi.\n")

    def _remove():
        if os.path.exists(RESULT_PATH):
            os.remove(RESULT_PATH)
            print(f"\n[Xavfsizlik] {RESULT_TTL_SECONDS} soniya o'tdi, result.json avtomatik o'chirildi.")

    timer = threading.Timer(RESULT_TTL_SECONDS, _remove)
    timer.daemon = True
    timer.start()
    return timer


def sync_pull():
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print("Bu papka git repo emas.\n")
        return
    result = subprocess.run(["git", "pull"], cwd=REPO_DIR, capture_output=True, text=True)
    print((result.stdout or result.stderr).strip() + "\n")


MENU = """
===== SecVault =====
1. To'liq list (parollar bilan)
2. Faqat emaillar
3. Masked list
4. Yangi akkaunt qo'shish
5. Akkauntni tahrirlash
6. Akkauntni o'chirish
7. GitHub'dan yangilash (pull)
8. GitHub'ga yuborish (push)
9. To'liq listni result.jsonga yozish
0. Chiqish
====================
"""


def main():
    if not os.path.exists(META_PATH):
        dek = run_init()
    else:
        dek = unlock()

    accounts = load_accounts(dek)
    cleanup_timer = None

    while True:
        print(MENU)
        choice = input("Tanlov: ").strip()

        if choice == "1":
            show_list(accounts, "full")
        elif choice == "2":
            show_list(accounts, "emails")
        elif choice == "3":
            show_list(accounts, "masked")
        elif choice == "4":
            action_add(dek, accounts)
        elif choice == "5":
            action_edit(dek, accounts)
        elif choice == "6":
            action_delete(dek, accounts)
        elif choice == "7":
            sync_pull()
            accounts = load_accounts(dek)
        elif choice == "8":
            push_to_github()
        elif choice == "9":
            if cleanup_timer is not None:
                cleanup_timer.cancel()
            cleanup_timer = export_full_list(accounts)
        elif choice == "0":
            if cleanup_timer is not None:
                cleanup_timer.cancel()
            if os.path.exists(RESULT_PATH):
                os.remove(RESULT_PATH)
                print("result.json o'chirildi.")
            print("Xayr!")
            break
        else:
            print("Noto'g'ri tanlov, qaytadan urinib ko'ring.\n")


if __name__ == "__main__":
    main()
