#!/usr/bin/env python3
"""
Полный аналог aspia_signer с 100% совместимостью команд.
Реализует алгоритм Ed25519 и формат подписи "1:<base64>", как в оригинальном Aspia.
Требования: pip install cryptography
"""

import argparse
import base64
import os
import sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

def load_key(key_input: str, need_private: bool = False):
    """
    Загружает ключ из файла или HEX-строки.
    Согласно документации Aspia: "Публичный ключ — это сам ключ в hex или файл, 
    содержащий закрытый ключ, которому он принадлежит".
    """
    if os.path.isfile(key_input):
        with open(key_input, "rb") as f:
            data = f.read()
        
        # 1. Пробуем формат PEM
        if data.startswith(b"-----BEGIN"):
            try:
                key = serialization.load_pem_private_key(data, password=None)
                return key if need_private else key.public_key()
            except Exception:
                return serialization.load_pem_public_key(data)
        
        # 2. Пробуем сырые байты (ровно 32 байта)
        if len(data) == 32:
            try:
                priv_key = Ed25519PrivateKey.from_private_bytes(data)
                return priv_key if need_private else priv_key.public_key()
            except Exception:
                return Ed25519PublicKey.from_public_bytes(data)
                
        # 3. Пробуем HEX-строку внутри файла (64 символа + возможные переносы строк)
        try:
            text_data = data.decode('ascii').strip()
            if len(text_data) == 64 and all(c in '0123456789abcdefABCDEF' for c in text_data):
                raw_bytes = bytes.fromhex(text_data)
                try:
                    priv_key = Ed25519PrivateKey.from_private_bytes(raw_bytes)
                    return priv_key if need_private else priv_key.public_key()
                except Exception:
                    return Ed25519PublicKey.from_public_bytes(raw_bytes)
        except UnicodeDecodeError:
            pass
            
        raise ValueError(f"Неверный формат файла ключа: {key_input}")
    else:
        # Не файл, предполагаем, что это HEX-строка, переданная напрямую в аргументе
        key_input = key_input.strip()
        if len(key_input) == 64 and all(c in '0123456789abcdefABCDEF' for c in key_input):
            raw_bytes = bytes.fromhex(key_input)
            try:
                priv_key = Ed25519PrivateKey.from_private_bytes(raw_bytes)
                return priv_key if need_private else priv_key.public_key()
            except Exception:
                return Ed25519PublicKey.from_public_bytes(raw_bytes)
                
        raise ValueError(f"Ключ не является существующим файлом или валидной 64-символьной HEX-строкой: {key_input}")


def cmd_genkey(args):
    if os.path.exists(args.private_key):
        print(f"Ошибка: Файл '{args.private_key}' уже существует.", file=sys.stderr)
        sys.exit(1)
    
    private_key = Ed25519PrivateKey.generate()
    
    # Сохраняем закрытый ключ как сырые 32 байта (компактный формат, как в оригинале)
    with open(args.private_key, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Выводим публичный ключ в HEX (64 символа) для вставки в настройки Aspia
    public_key_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()
    
    print(public_key_hex)


def cmd_sign(args):
    private_key = load_key(args.private_key, need_private=True)
    
    for file_path in args.files:
        if not os.path.isfile(file_path):
            print(f"Ошибка: Файл не найден: {file_path}", file=sys.stderr)
            continue
            
        with open(file_path, "rb") as f:
            file_data = f.read()
            
        signature = private_key.sign(file_data)
        b64_signature = base64.b64encode(signature).decode('ascii')
        tagged_signature = f"1:{b64_signature}"
        
        sig_path = file_path + ".sig"
        with open(sig_path, "w") as f:
            f.write(tagged_signature)
        print(f"Подписано: {sig_path}")


def cmd_signdir(args):
    private_key = load_key(args.private_key, need_private=True)
    
    for dir_path in args.dirs:
        if not os.path.isdir(dir_path):
            print(f"Ошибка: Директория не найдена: {dir_path}", file=sys.stderr)
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    with open(file_path, "rb") as f:
                        file_data = f.read()
                        
                    signature = private_key.sign(file_data)
                    b64_signature = base64.b64encode(signature).decode('ascii')
                    tagged_signature = f"1:{b64_signature}"
                    
                    sig_path = file_path + ".sig"
                    with open(sig_path, "w") as f:
                        f.write(tagged_signature)
                    print(f"Подписано: {sig_path}")


def cmd_verify(args):
    public_key = load_key(args.public_key, need_private=False)
    
    all_valid = True
    for file_path in args.files:
        sig_path = file_path + ".sig"
        if not os.path.isfile(file_path):
            print(f"Ошибка: Файл не найден: {file_path}", file=sys.stderr)
            all_valid = False
            continue
        if not os.path.isfile(sig_path):
            print(f"Ошибка: Файл подписи не найден: {sig_path}", file=sys.stderr)
            all_valid = False
            continue
            
        with open(file_path, "rb") as f:
            file_data = f.read()
        with open(sig_path, "r") as f:
            tagged_signature = f.read().strip()
            
        if not tagged_signature.startswith("1:"):
            print(f"Ошибка: Неверный формат подписи в {sig_path}", file=sys.stderr)
            all_valid = False
            continue
            
        try:
            signature = base64.b64decode(tagged_signature[2:])
            public_key.verify(signature, file_data)
            print(f"OK: {file_path}")
        except Exception as e:
            print(f"ПРОВАЛ: {file_path} ({e})", file=sys.stderr)
            all_valid = False
            
    if not all_valid:
        sys.exit(1)


def cmd_verifydir(args):
    public_key = load_key(args.public_key, need_private=False)
    
    all_valid = True
    for dir_path in args.dirs:
        if not os.path.isdir(dir_path):
            print(f"Ошибка: Директория не найдена: {dir_path}", file=sys.stderr)
            all_valid = False
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    sig_path = file_path + ".sig"
                    
                    if not os.path.isfile(sig_path):
                        print(f"Ошибка: Файл подписи не найден: {sig_path}", file=sys.stderr)
                        all_valid = False
                        continue
                        
                    with open(file_path, "rb") as f:
                        file_data = f.read()
                    with open(sig_path, "r") as f:
                        tagged_signature = f.read().strip()
                        
                    if not tagged_signature.startswith("1:"):
                        print(f"Ошибка: Неверный формат подписи в {sig_path}", file=sys.stderr)
                        all_valid = False
                        continue
                        
                    try:
                        signature = base64.b64decode(tagged_signature[2:])
                        public_key.verify(signature, file_data)
                        print(f"OK: {file_path}")
                    except Exception as e:
                        print(f"ПРОВАЛ: {file_path} ({e})", file=sys.stderr)
                        all_valid = False
                        
    if not all_valid:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Полный аналог aspia_signer с 100% совместимостью команд.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s genkey my_private.key
  %(prog)s sign my_private.key update.json
  %(prog)s signdir my_private.key ./updates
  %(prog)s verify 0123456789abcdef... update.json
  %(prog)s verifydir my_private.key ./updates
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды", required=True)
    
    # genkey
    p_genkey = subparsers.add_parser("genkey", help="Создает ключ и выводит его публичную половину (HEX)")
    p_genkey.add_argument("private_key", help="Путь для сохранения закрытого ключа")
    p_genkey.set_defaults(func=cmd_genkey)
    
    # sign
    p_sign = subparsers.add_parser("sign", help="Подписывает файлы, создавая <file>.sig рядом с каждым")
    p_sign.add_argument("private_key", help="Файл закрытого ключа")
    p_sign.add_argument("files", nargs="+", help="Файлы для подписи")
    p_sign.set_defaults(func=cmd_sign)
    
    # signdir
    p_signdir = subparsers.add_parser("signdir", help="Подписывает все .json файлы в указанных директориях (рекурсивно)")
    p_signdir.add_argument("private_key", help="Файл закрытого ключа")
    p_signdir.add_argument("dirs", nargs="+", help="Директории для поиска .json файлов")
    p_signdir.set_defaults(func=cmd_signdir)
    
    # verify
    p_verify = subparsers.add_parser("verify", help="Проверяет подпись <file>.sig для каждого файла")
    p_verify.add_argument("public_key", help="Публичный ключ (HEX-строка 64 символа или файл ключа)")
    p_verify.add_argument("files", nargs="+", help="Файлы для проверки")
    p_verify.set_defaults(func=cmd_verify)
    
    # verifydir
    p_verifydir = subparsers.add_parser("verifydir", help="Проверяет подписи всех .json файлов в указанных директориях")
    p_verifydir.add_argument("public_key", help="Публичный ключ (HEX-строка 64 символа или файл ключа)")
    p_verifydir.add_argument("dirs", nargs="+", help="Директории для поиска .json файлов")
    p_verifydir.set_defaults(func=cmd_verifydir)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()