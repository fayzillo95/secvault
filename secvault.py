#!/usr/bin/env python3
import base64
import getpass
import json
import os
import subprocess
import sys
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(REPO_DIR, "vault.meta.json")
DATA_PATH = os.path.join(REPO_DIR, "accounts.enc")
PBKDF2_ITERATIONS = 390_000


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


def git_sync(message: str) -> None:
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print("Ogohlantirish: bu papka git repo emas, push o'tkazib yuborildi.")
        return
    subprocess.run(["git", "add", "accounts.enc", "vault.meta.json"], cwd=REPO_DIR)
    commit = subprocess.run(["git", "commit", "-m", message], cwd=REPO_DIR, capture_output=True, text=True)
    if commit.returncode != 0:
        if "nothing to commit" in commit.stdout.lower():
            return
        print(f"Ogohlantirish: commit qilinmadi -> {commit.stdout.strip()}")
        return
    push = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True)
    if push.returncode != 0:
        print(f"Ogohlantirish: push muvaffaqiyatsiz -> {push.stderr.strip()}")
        print("Keyinroq qo'lda 'git push' qiling.")
    else:
        print("GitHub'ga muvaffaqiyatli push qilindi.")


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
        seed = getpass.getpass("Yangi Seed (asosiy parol) o'ylab toping: ")
        seed_confirm = getpass.getpass("Seedni qayta kiriting: ")
        if seed == seed_confirm and seed:
            break
        print("Seedlar mos kelmadi yoki bo'sh, qaytadan urinib ko'ring.\n")

    question = input("Tiklash savolini kiriting (masalan: Birinchi telefon raqamingiz?): ")
    answer = getpass.getpass("Tiklash javobini kiriting: ")

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
    print("MUHIM: Seed va tiklash javobini xavfsiz joyda saqlang, ular hech qayerda saqlanmaydi.\n")
    git_sync("init: vault yaratildi")
    return dek


def unlock() -> bytes:
    meta = load_meta()
    choice = getpass.getpass("Seedni kiriting (tiklash uchun 'r' yozing): ")
    if choice == "r":
        print(f"Tiklash savoli: {meta['recovery_question']}")
        secret = getpass.getpass("Javobni kiriting: ")
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
    password = getpass.getpass("Parol: ")
    accounts[email] = password
    save_accounts(dek, accounts)
    print(f"'{email}' qo'shildi.")
    git_sync(f"add: {mask_email(email)} - {datetime.now():%Y-%m-%d %H:%M}")


def action_edit(dek, accounts):
    email = input("O'zgartiriladigan Gmail: ").strip()
    if email not in accounts:
        print("Bunday email topilmadi.")
        return
    new_password = getpass.getpass("Yangi parol: ")
    accounts[email] = new_password
    save_accounts(dek, accounts)
    print(f"'{email}' uchun parol yangilandi.")
    git_sync(f"edit: {mask_email(email)} - {datetime.now():%Y-%m-%d %H:%M}")


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
    print(f"'{email}' o'chirildi.")
    git_sync(f"delete: {mask_email(email)} - {datetime.now():%Y-%m-%d %H:%M}")


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
7. GitHub'dan yangilash (sync)
0. Chiqish
====================
"""


def main():
    if not os.path.exists(META_PATH):
        dek = run_init()
    else:
        dek = unlock()

    accounts = load_accounts(dek)

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
        elif choice == "0":
            print("Xayr!")
            break
        else:
            print("Noto'g'ri tanlov, qaytadan urinib ko'ring.\n")


if __name__ == "__main__":
    main()
