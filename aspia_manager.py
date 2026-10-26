#!/usr/bin/env python3
"""
Aspia Manager: Скрипт для автоматизированного скачивания инсталляторов Aspia, 
очистки устаревших файлов, генерации релизных манифестов и управления каналами обновлений.
Настройки загружаются из файла .vars в директории скрипта.
"""

import os
import sys
import re
import json
import hashlib
import urllib.request
import urllib.error

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ И КОНСТАНТЫ
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VARS_FILE = os.path.join(SCRIPT_DIR, ".vars")

# Глобальная переменная для конфигурации, будет заполнена в main() после проверки
CONFIG = None

DEFAULT_CONFIG = {
    "TARGET_ROOT_DIR": "/var/www/aspia-updates/",
    "TARGET_STORAGE_DIR": "/var/www/aspia-updates/storage/",
    "UPDATE_BASE_URL": "https://aspia.example.com/update/storage/",
    "DOWNLOAD_MAP": {
        "client": {
            "arm64": ["apk"],
            "universal": ["pkg"],
            "x86_64": ["msi", "deb", "rpm"]
        },
        "host": {
            "arm64": ["apk"],
            "universal": ["pkg"],
            "x86": ["msi"],
            "x86_64": ["msi", "deb", "rpm"]
        },
        "router": {
            "x86_64": ["msi", "deb", "rpm"]
        },
        "relay": {
            "x86_64": ["msi", "deb", "rpm"]
        }
    },
    "ALLOWED_CHANNELS": ["stable", "beta", "alpha"]
}


def load_config():
    """
    Проверяет наличие и корректность файла .vars.
    Возвращает кортеж: (config_dict или None, сообщение об ошибке или None)
    """
    if not os.path.exists(VARS_FILE):
        return None, "Файл конфигурации '.vars' не найден в директории скрипта."
    
    try:
        with open(VARS_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        required_keys = ["TARGET_ROOT_DIR", "TARGET_STORAGE_DIR", "UPDATE_BASE_URL", "DOWNLOAD_MAP", "ALLOWED_CHANNELS"]
        for key in required_keys:
            if key not in config:
                return None, f"В файле '.vars' отсутствует обязательный параметр: '{key}'."
                
        return config, None
    except json.JSONDecodeError as e:
        return None, f"Некорректный формат JSON в файле '.vars'.\nПодробности: {e}"
    except Exception as e:
        return None, f"Неожиданная ошибка при чтении файла '.vars': {e}"


def handle_create_vars():
    """Создает файл .vars с настройками по умолчанию."""
    if os.path.exists(VARS_FILE):
        print(f"⚠️  Файл '{VARS_FILE}' уже существует.")
        response = input("Перезаписать его настройками по умолчанию? (y/N): ").strip().lower()
        if response != 'y':
            print("   ⏭️  Операция отменена.")
            return False
    
    try:
        with open(VARS_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"✅ Файл '{VARS_FILE}' успешно создан с настройками по умолчанию!")
        print("💡 Вы можете отредактировать его перед запуском других команд.")
        return True
    except PermissionError:
        print(f"❌ Ошибка: Нет прав на запись в директорию '{SCRIPT_DIR}'.")
        print("   Запустите скрипт с правами root или измените права на директорию.")
        return False
    except Exception as e:
        print(f"❌ Ошибка при создании файла конфигурации: {e}")
        return False


def get_script_name():
    """Возвращает текущее имя файла скрипта для использования в справке."""
    return os.path.basename(__file__)


def get_root_dir():
    """Возвращает абсолютный путь к корневой директории сервера обновлений."""
    return CONFIG["TARGET_ROOT_DIR"]


def get_storage_dir():
    """Возвращает абсолютный путь к директории хранения инсталляторов."""
    return CONFIG["TARGET_STORAGE_DIR"]


def get_versions_dir():
    """Возвращает абсолютный путь к директории JSON-манифестов версий (всегда внутри ROOT)."""
    return os.path.join(CONFIG["TARGET_ROOT_DIR"], "versions")


def print_manual():
    script_name = get_script_name()
    manual = f"""
================================================================================
  Aspia Manager
================================================================================
Использование:
  ./{script_name}                                     # Показать это сообщение
  ./{script_name} createvars                          # Создать файл .vars с настройками по умолчанию
  
  [Управление релизами]
  ./{script_name} download <версия>                   # Скачать файлы, очистить лишнее и создать манифест
  
  [Управление каналами обновлений]
  ./{script_name} channel create <канал>              # Создать или сбросить канал (stable, beta, alpha)
  ./{script_name} channel <канал> latest <версия>     # Установить последнюю версию для канала
  ./{script_name} channel <канал> add <источник> <цель> # Добавить правило обновления (напр. 3.0.37 @latest)
  ./{script_name} channel <канал> remove <источник>   # Удалить правило обновления для версии-источника
  ./{script_name} channel <канал> list                # Показать текущую конфигурацию канала
  
  [Проверка целостности]
  ./{script_name} check                               # Проверить целостность всей конфигурации репозитория

Параметры:
  <канал>   - Имя канала: только "stable", "beta" или "alpha"
  <версия>  - Версия Aspia в формате "3.a.b" (например: 3.1.2)
  <источник>- Версия, с которой выполняется обновление (например: 3.0.37)
  <цель>    - Версия назначения или метка "@latest"

Примеры:
  ./{script_name} createvars
  ./{script_name} download 3.1.2
  ./{script_name} channel create stable
  ./{script_name} channel stable latest 3.1.2
  ./{script_name} check

Настройка:
  Все настройки хранятся в файле '.vars' в той же директории, что и скрипт.
  Файл имеет формат JSON. Основные параметры:
  - TARGET_ROOT_DIR     : Корневая директория сервера обновлений.
  - TARGET_STORAGE_DIR  : Абсолютный путь к директории хранения инсталляторов.
  - UPDATE_BASE_URL     : Публичный URL-путь к директории storage.
  - DOWNLOAD_MAP        : Словарь, определяющий необходимые компоненты, платформы и расширения.
================================================================================
"""
    print(manual)


def validate_version(version):
    """Проверяет, что версия строго соответствует формату 3.a.b"""
    pattern = r"^3\.\d+\.\d+$"
    return bool(re.match(pattern, version))


def validate_channel(channel):
    """Проверяет, что имя канала разрешено"""
    return channel in CONFIG["ALLOWED_CHANNELS"]


def calculate_sha256(file_path):
    """Вычисляет SHA256 хэш файла"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_os_from_ext(ext):
    """Сопоставляет расширение файла с именем ОС согласно документации Aspia"""
    if ext == "apk": return "android"
    elif ext == "msi": return "windows"
    elif ext in ("deb", "rpm"): return "linux"
    elif ext == "pkg": return "macosx"
    return "unknown"


def download_file(url, dest_path):
    """Скачивает файл по URL и сохраняет его в dest_path"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(dest_path, 'wb') as out_file:
                out_file.write(response.read())
        return True, "Успешно сохранено"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "Не найдено (404) - возможно, сборка не выпущена"
        else:
            return False, f"Ошибка HTTP {e.code}"
    except Exception as e:
        return False, f"Ошибка: {e}"


def load_json_file(filepath):
    """Безопасно загружает JSON файл"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"   ❌ Ошибка чтения JSON {filepath}: {e}")
        return None


def save_json_file(filepath, data):
    """Безопасно сохраняет JSON файл"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"   ❌ Ошибка записи JSON {filepath}: {e}")
        return False


def get_expected_files_from_manifest(manifest):
    """Извлекает список всех имен файлов из манифеста версии"""
    files = []
    packages = manifest.get("packages", {})
    for component, os_dict in packages.items():
        for os_name, arch_dict in os_dict.items():
            for arch, pkg_list in arch_dict.items():
                for pkg in pkg_list:
                    if "file" in pkg:
                        files.append(pkg["file"])
    return files


def validate_version_integrity(version):
    """
    Комплексная проверка целостности версии:
    1. Наличие манифеста в директории versions/.
    2. Наличие директории версии в TARGET_STORAGE_DIR.
    3. Наличие всех файлов инсталляторов, перечисленных в манифесте.
    Возвращает кортеж: (is_valid: bool, message: str)
    """
    versions_dir = get_versions_dir()
    storage_dir = get_storage_dir()
    
    manifest_path = os.path.join(versions_dir, f"{version}.json")
    manifest = load_json_file(manifest_path)
    if not manifest:
        return False, f"Манифест версии не найден: {manifest_path}"
    
    version_storage_dir = os.path.join(storage_dir, version)
    if not os.path.isdir(version_storage_dir):
        return False, f"Директория версии не найдена: {version_storage_dir}"
    
    expected_files = get_expected_files_from_manifest(manifest)
    missing_files = []
    for filename in expected_files:
        file_path = os.path.join(version_storage_dir, filename)
        if not os.path.isfile(file_path):
            missing_files.append(filename)
            
    if missing_files:
        return False, f"Отсутствуют файлы инсталляторов ({len(missing_files)} шт.): {', '.join(missing_files[:3])}..."
    
    return True, "OK"


def handle_channel_create(channel):
    """Создает или сбрасывает файл канала"""
    if not validate_channel(channel):
        print(f"❌ Ошибка: Неверное имя канала '{channel}'. Разрешены только: {', '.join(CONFIG['ALLOWED_CHANNELS'])}")
        return False

    root_dir = get_root_dir()
    os.makedirs(root_dir, exist_ok=True)
    
    filepath = os.path.join(root_dir, f"{channel}.json")
    
    if os.path.exists(filepath):
        print(f"⚠️  Файл канала '{channel}.json' уже существует.")
        print("⚠️  ВНИМАНИЕ: Перезапись удалит ВСЕ текущие правила и настройки этого канала!")
        response = input("Продолжить и перезаписать файл? (y/N): ").strip().lower()
        if response != 'y':
            print("   ⏭️  Операция отменена пользователем.")
            return False

    initial_data = {
        "format": 1,
        "targets": {},
        "updates": []
    }
    
    if save_json_file(filepath, initial_data):
        print(f"   ✅ Канал '{channel}' успешно создан/сброшен: {filepath}")
        return True
    return False


def handle_channel_latest(channel, version):
    """Устанавливает последнюю версию для канала с полной проверкой целостности"""
    if not validate_channel(channel):
        print(f"❌ Ошибка: Неверное имя канала '{channel}'.")
        return False
    if not validate_version(version):
        print(f"❌ Ошибка: Неверный формат версии '{version}'. Ожидается формат '3.a.b'.")
        return False

    is_valid, msg = validate_version_integrity(version)
    if not is_valid:
        print(f"❌ Ошибка: Версия '{version}' не прошла проверку целостности.")
        print(f"   Причина: {msg}")
        print("   💡 Сначала скачайте и подготовьте версию командой 'download'")
        return False

    root_dir = get_root_dir()
    filepath = os.path.join(root_dir, f"{channel}.json")
    
    channel_data = load_json_file(filepath)
    if not channel_data:
        print(f"   ❌ Файл канала не найден. Сначала создайте его: ./{get_script_name()} channel create {channel}")
        return False

    channel_data["targets"]["latest"] = version
    
    if save_json_file(filepath, channel_data):
        print(f"   ✅ Версия '{version}' успешно установлена как 'latest' для канала '{channel}'")
        return True
    return False


def handle_channel_add(channel, source, target):
    """Добавляет правило обновления в канал с проверкой целостности целевой версии"""
    if not validate_channel(channel):
        print(f"❌ Ошибка: Неверное имя канала '{channel}'.")
        return False
    if not validate_version(source):
        print(f"❌ Ошибка: Неверный формат версии-источника '{source}'.")
        return False
    
    if target != "@latest" and not validate_version(target):
        print(f"❌ Ошибка: Неверный формат цели '{target}'. Ожидается версия '3.a.b' или '@latest'.")
        return False

    # Определяем, какую версию нужно проверять на целостность
    version_to_validate = target
    if target == "@latest":
        root_dir = get_root_dir()
        filepath = os.path.join(root_dir, f"{channel}.json")
        channel_data = load_json_file(filepath)
        
        if channel_data and "latest" in channel_data.get("targets", {}):
            version_to_validate = channel_data["targets"]["latest"]
        else:
            print(f"❌ Ошибка: Невозможно добавить правило с целью '@latest', так как метка 'latest' еще не установлена для канала '{channel}'.")
            print(f"   Сначала установите актуальную версию: ./{get_script_name()} channel {channel} latest <версия>")
            return False

    # Строгая проверка целостности целевой версии
    is_valid, msg = validate_version_integrity(version_to_validate)
    if not is_valid:
        print(f"❌ Ошибка: Целевая версия '{version_to_validate}' не прошла проверку целостности.")
        print(f"   Причина: {msg}")
        print("   💡 Нельзя добавить правило на версию, которая не имеет манифеста, директории или файлов.")
        print("   💡 Сначала скачайте и подготовьте версию командой 'download'")
        return False

    # Если проверка пройдена, добавляем правило
    root_dir = get_root_dir()
    filepath = os.path.join(root_dir, f"{channel}.json")
    channel_data = load_json_file(filepath)
    
    if not channel_data:
        print(f"   ❌ Файл канала не найден. Сначала создайте его: ./{get_script_name()} channel create {channel}")
        return False

    # Удаляем существующее правило для этого источника (должен быть только один entry per released version)
    original_len = len(channel_data.get("updates", []))
    channel_data["updates"] = [u for u in channel_data.get("updates", []) if u.get("source") != source]
    
    # Добавляем новое правило
    if "updates" not in channel_data:
        channel_data["updates"] = []
    channel_data["updates"].append({"source": source, "target": target})
    
    if save_json_file(filepath, channel_data):
        if original_len > len(channel_data["updates"]):
            print(f"   ⚠️  Предыдущее правило для источника '{source}' было заменено.")
        print(f"   ✅ Добавлено правило обновления: {source} -> {target} в канале '{channel}'")
        print(f"   ℹ️  Целевая версия '{version_to_validate}' успешно прошла проверку целостности.")
        return True
    return False


def handle_channel_remove(channel, source):
    """Удаляет правило обновления из канала"""
    if not validate_channel(channel):
        print(f"❌ Ошибка: Неверное имя канала '{channel}'.")
        return False
    if not validate_version(source):
        print(f"❌ Ошибка: Неверный формат версии-источника '{source}'.")
        return False

    root_dir = get_root_dir()
    filepath = os.path.join(root_dir, f"{channel}.json")
    channel_data = load_json_file(filepath)
    
    if not channel_data:
        print(f"   ❌ Файл канала не найден.")
        return False

    original_len = len(channel_data.get("updates", []))
    channel_data["updates"] = [u for u in channel_data.get("updates", []) if u.get("source") != source]
    
    if len(channel_data["updates"]) == original_len:
        print(f"   ⚠️  Правило для источника '{source}' не найдено в канале '{channel}'.")
        return False
        
    if save_json_file(filepath, channel_data):
        print(f"   ✅ Правило обновления для источника '{source}' удалено из канала '{channel}'")
        return True
    return False


def handle_channel_list(channel):
    """Выводит текущую конфигурацию канала"""
    if not validate_channel(channel):
        print(f"❌ Ошибка: Неверное имя канала '{channel}'.")
        return False

    root_dir = get_root_dir()
    filepath = os.path.join(root_dir, f"{channel}.json")
    channel_data = load_json_file(filepath)
    
    if not channel_data:
        print(f"   ❌ Файл канала '{channel}.json' не найден.")
        return False

    print(f"\n📊 Конфигурация канала: {channel.upper()}")
    print("-" * 50)
    
    targets = channel_data.get("targets", {})
    print("🎯 Цели (targets):")
    if not targets:
        print("   (пусто)")
    else:
        for key, value in targets.items():
            print(f"   - {key}: {value}")
            
    updates = channel_data.get("updates", [])
    print("\n🔄 Правила обновлений (updates):")
    if not updates:
        print("   (пусто)")
    else:
        # Сортировка правил по полю source в числовом (версионном) порядке
        # Например: "3.0.2" -> [3, 0, 2], "3.0.19" -> [3, 0, 19]
        sorted_updates = sorted(
            updates, 
            key=lambda x: [int(p) for p in x.get("source", "0").split(".")]
        )
        for rule in sorted_updates:
            print(f"   - {rule.get('source')} -> {rule.get('target')}")
    print("-" * 50 + "\n")
    return True


def handle_repo_check():
    """Комплексная проверка целостности всей конфигурации репозитория"""
    print("\n" + "="*80)
    print("🔍 ПРОВЕРКА КОНФИГУРАЦИИ РЕПОЗИТОРИЯ")
    print("="*80)
    
    root_dir = get_root_dir()
    versions_dir = get_versions_dir()
    storage_dir = get_storage_dir()
    
    issues = []
    
    # 1. Проверка наличия всех трех файлов каналов
    print("\n📂 1. Проверка файлов каналов:")
    for ch in CONFIG["ALLOWED_CHANNELS"]:
        ch_file = os.path.join(root_dir, f"{ch}.json")
        if os.path.isfile(ch_file):
            print(f"   ✅ {ch}.json найден")
        else:
            print(f"   ❌ {ch}.json ОТСУТСТВУЕТ")
            issues.append(f"Отсутствует файл канала: {ch}.json")
    
    # 2. Сбор всех целевых версий из конфигурации каналов
    versions_to_check = set()
    print("\n📂 2. Анализ правил каналов:")
    for ch in CONFIG["ALLOWED_CHANNELS"]:
        ch_file = os.path.join(root_dir, f"{ch}.json")
        if not os.path.isfile(ch_file):
            continue
        
        ch_data = load_json_file(ch_file)
        if not ch_data:
            continue
        
        # Проверка targets.latest
        if "latest" in ch_data.get("targets", {}):
            ver = ch_data["targets"]["latest"]
            versions_to_check.add(ver)
            print(f"   ℹ️  Канал '{ch}': latest -> {ver}")
        
        # Сортируем правила для красивого вывода при проверке
        updates = ch_data.get("updates", [])
        sorted_updates = sorted(
            updates, 
            key=lambda x: [int(p) for p in x.get("source", "0").split(".")]
        )
        
        for rule in sorted_updates:
            target = rule.get("target")
            if target and target != "@latest" and validate_version(target):
                versions_to_check.add(target)
                print(f"   ℹ️  Канал '{ch}': правило {rule.get('source')} -> {target}")
            elif target == "@latest":
                print(f"   ℹ️  Канал '{ch}': правило {rule.get('source')} -> @latest (проверяется через latest)")

    # 3. Проверка целостности каждой уникальной целевой версии
    print("\n📦 3. Проверка целостности целевых версий:")
    if not versions_to_check:
        print("   ⚠️  Целевые версии не найдены в конфигурации каналов.")
    else:
        for ver in sorted(list(versions_to_check), reverse=True):
            print(f"\n   🔹 Версия: {ver}")
            is_valid, msg = validate_version_integrity(ver)
            if is_valid:
                print("      ✅ Целостность подтверждена (манифест, директория и все файлы на месте)")
            else:
                print(f"      ❌ ОШИБКА: {msg}")
                issues.append(f"Версия {ver}: {msg}")
    
    # Итоговый отчет
    print("\n" + "="*80)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("="*80)
    if not issues:
        print("   ✅ Все проверки пройдены успешно. Репозиторий настроен корректно.")
    else:
        print(f"   ❌ Обнаружено проблем: {len(issues)}")
        for issue in issues:
            print(f"      - {issue}")
        print("\n   💡 Используйте команду 'download <версия>' для исправления отсутствующих файлов.")
    print("="*80 + "\n")


def main():
    global CONFIG
    
    if len(sys.argv) < 2:
        print_manual()
        sys.exit(0)
    
    command = sys.argv[1]
    
    # ==========================================================================
    # ОБРАБОТКА КОМАНДЫ CREATEVARS (без проверки конфигурации)
    # ==========================================================================
    if command == "createvars":
        success = handle_create_vars()
        sys.exit(0 if success else 1)

    # ==========================================================================
    # ПРОВЕРКА КОНФИГУРАЦИИ ДЛЯ ВСЕХ ОСТАЛЬНЫХ КОМАНД
    # ==========================================================================
    config, error = load_config()
    if error:
        print(f"❌ Ошибка конфигурации: {error}")
        print(f"\n💡 Для создания файла с настройками по умолчанию выполните команду:")
        print(f"   ./{get_script_name()} createvars\n")
        sys.exit(1)
    
    CONFIG = config

    # ==========================================================================
    # ОБРАБОТКА КОМАНДЫ CHECK
    # ==========================================================================
    if command == "check":
        handle_repo_check()
        sys.exit(0)

    # ==========================================================================
    # ОБРАБОТКА КОМАНДЫ CHANNEL
    # ==========================================================================
    if command == "channel":
        if len(sys.argv) < 3:
            print("❌ Ошибка: Не указано действие или имя канала.")
            print_manual()
            sys.exit(1)
            
        subcommand = sys.argv[2]
        
        if subcommand == "create":
            if len(sys.argv) < 4:
                print("❌ Ошибка: Не указано имя канала.")
                print(f"   Использование: ./{get_script_name()} channel create <канал>")
                sys.exit(1)
            handle_channel_create(sys.argv[3])
            
        elif subcommand in CONFIG["ALLOWED_CHANNELS"]:
            channel = subcommand
            if len(sys.argv) < 4:
                print(f"❌ Ошибка: Не указано действие для канала '{channel}'.")
                print("   Доступные действия: latest, add, remove, list")
                sys.exit(1)
                
            action = sys.argv[3]
            
            if action == "latest":
                if len(sys.argv) < 5:
                    print(f"❌ Ошибка: Не указана версия.")
                    print(f"   Использование: ./{get_script_name()} channel {channel} latest <версия>")
                    sys.exit(1)
                handle_channel_latest(channel, sys.argv[4])
                
            elif action == "add":
                if len(sys.argv) < 6:
                    print(f"❌ Ошибка: Не указаны источник и цель.")
                    print(f"   Использование: ./{get_script_name()} channel {channel} add <источник> <цель>")
                    sys.exit(1)
                handle_channel_add(channel, sys.argv[4], sys.argv[5])
                
            elif action == "remove":
                if len(sys.argv) < 5:
                    print(f"❌ Ошибка: Не указан источник.")
                    print(f"   Использование: ./{get_script_name()} channel {channel} remove <источник>")
                    sys.exit(1)
                handle_channel_remove(channel, sys.argv[4])
                
            elif action == "list":
                handle_channel_list(channel)
                
            else:
                print(f"❌ Неизвестное действие '{action}' для канала.")
                print("   Доступные действия: latest, add, remove, list")
                sys.exit(1)
                
        else:
            print(f"❌ Неизвестная подкоманда или неверное имя канала: '{subcommand}'")
            print(f"   Разрешенные каналы: {', '.join(CONFIG['ALLOWED_CHANNELS'])}")
            print("   Используйте 'create' для создания нового канала.")
            sys.exit(1)
            
        sys.exit(0)

    # ==========================================================================
    # ОБРАБОТКА КОМАНДЫ DOWNLOAD
    # ==========================================================================
    if command != "download":
        print(f"❌ Неизвестная команда: '{command}'")
        print_manual()
        sys.exit(1)
        
    if len(sys.argv) < 3:
        print("❌ Ошибка: Не указана версия.")
        print_manual()
        sys.exit(1)
        
    version = sys.argv[2]
    
    if not validate_version(version):
        print(f"❌ Ошибка: Неверный формат версии '{version}'.")
        print("   Версия должна соответствовать формату '3.a.b' (например, 3.1.2).")
        sys.exit(1)
        
    storage_dir = get_storage_dir()
    versions_dir = get_versions_dir()
    version_storage_dir = os.path.join(storage_dir, version)
    
    # Создаем необходимые директории
    for d in [version_storage_dir, versions_dir]:
        try:
            os.makedirs(d, exist_ok=True)
        except PermissionError:
            print(f"❌ Ошибка: Нет прав для создания директории '{d}'. Запустите от имени root или проверьте права.")
            sys.exit(1)
            
    print(f"📁 Директория хранения  : {version_storage_dir}")
    print(f"📁 Директория манифестов: {versions_dir}")
    
    # ЭТАП 1: ОЧИСТКА УСТАРЕВШИХ ФАЙЛОВ
    print("\n" + "="*80)
    print("🧹 ЭТАП 1: Проверка и очистка устаревших файлов")
    print("="*80)
    
    expected_files = set()
    for component, platforms in CONFIG["DOWNLOAD_MAP"].items():
        for platform, extensions in platforms.items():
            for ext in extensions:
                filename = f"aspia-{component}-{version}-{platform}.{ext}"
                expected_files.add(filename)
                expected_files.add(filename + ".sha256")
    
    cleaned_count = 0
    if os.path.exists(version_storage_dir):
        for item in os.listdir(version_storage_dir):
            item_path = os.path.join(version_storage_dir, item)
            if os.path.isfile(item_path) and item not in expected_files:
                try:
                    os.remove(item_path)
                    print(f"   🗑️  Удален устаревший файл: {item}")
                    cleaned_count += 1
                except Exception as e:
                    print(f"   ⚠️  Не удалось удалить {item}: {e}")
    
    if cleaned_count == 0:
        print("   ✅ Устаревшие файлы не найдены, директория чиста.")
    else:
        print(f"   ✅ Очистка завершена. Удалено файлов: {cleaned_count}")

    # ЭТАП 2: СКАЧИВАНИЕ И ВЫЧИСЛЕНИЕ ХЭШЕЙ
    print("\n" + "="*80)
    print("🚀 ЭТАП 2: Скачивание и обработка файлов")
    print("="*80)
    
    download_map = CONFIG["DOWNLOAD_MAP"]
    base_github_url = "https://github.com/dchapyshev/aspia/releases/download"
    
    manifest = {
        "format": 1,
        "version": version,
        "description": f"Aspia {version} release",
        "path": CONFIG["UPDATE_BASE_URL"].rstrip('/') + "/" + version,
        "packages": {
            "host": {}, "client": {}, "router": {}, "relay": {}
        }
    }
    
    for component, platforms in download_map.items():
        if component not in manifest["packages"]:
            continue
        for platform, extensions in platforms.items():
            for ext in extensions:
                os_name = get_os_from_ext(ext)
                if os_name == "unknown":
                    continue
                
                if os_name not in manifest["packages"][component]:
                    manifest["packages"][component][os_name] = {}
                if platform not in manifest["packages"][component][os_name]:
                    manifest["packages"][component][os_name][platform] = []
                
                filename = f"aspia-{component}-{version}-{platform}.{ext}"
                manifest["packages"][component][os_name][platform].append({
                    "format": ext,
                    "file": filename,
                    "sha256": ""
                })

    success_count = 0
    fail_count = 0
    
    for component, platforms in download_map.items():
        for platform, extensions in platforms.items():
            for ext in extensions:
                filename = f"aspia-{component}-{version}-{platform}.{ext}"
                url = f"{base_github_url}/v{version}/{filename}"
                dest_path = os.path.join(version_storage_dir, filename)
                sha256_file_path = dest_path + ".sha256"
                
                print(f"\n📦 Файл: {filename}")
                
                file_exists = os.path.exists(dest_path)
                if file_exists:
                    print("   ├─ Статус : Уже существует (пропуск скачивания)")
                    download_success = True
                else:
                    print("   ├─ Статус : Загрузка...")
                    download_success, msg = download_file(url, dest_path)
                    if download_success:
                        print("   ├─ Статус : Успешно скачано")
                    else:
                        print(f"   ├─ Статус : ❌ Ошибка ({msg})")
                        fail_count += 1
                        continue
                
                print("   ├─ SHA256 : Вычисление хэша...")
                try:
                    sha256_hash = calculate_sha256(dest_path)
                    print(f"   │           {sha256_hash}")
                except Exception as e:
                    print(f"   │           ❌ Ошибка вычисления хэша: {e}")
                    fail_count += 1
                    continue
                
                try:
                    with open(sha256_file_path, "w", encoding="utf-8") as f:
                        f.write(f"{sha256_hash}  {filename}\n")
                    print(f"   └─ Файл   : Сохранен {os.path.basename(sha256_file_path)}")
                except Exception as e:
                    print(f"   └─ Файл   : ❌ Ошибка сохранения .sha256 ({e})")
                    fail_count += 1
                    continue
                
                os_name = get_os_from_ext(ext)
                if os_name != "unknown" and component in manifest["packages"]:
                    if os_name in manifest["packages"][component] and platform in manifest["packages"][component][os_name]:
                        for pkg in manifest["packages"][component][os_name][platform]:
                            if pkg["file"] == filename:
                                pkg["sha256"] = sha256_hash
                                break
                
                success_count += 1

    # ЭТАП 3: ГЕНЕРАЦИЯ JSON МАНИФЕСТА
    print("\n" + "="*80)
    print("📄 ЭТАП 3: Генерация JSON манифеста")
    print("="*80)
    
    json_filename = f"{version}.json"
    json_filepath = os.path.join(versions_dir, json_filename)
    
    if save_json_file(json_filepath, manifest):
        print(f"   ✅ Манифест успешно сохранен: {json_filepath}")
    else:
        fail_count += 1
        
    # ИТОГОВЫЙ ОТЧЕТ
    print("\n" + "="*80)
    print("📊 ЗАВЕРШЕНИЕ РАБОТЫ")
    print("="*80)
    print(f"   ✅ Успешно обработано файлов : {success_count}")
    print(f"   ❌ Ошибки или пропуски       : {fail_count}")
    print(f"   🗑️  Удалено устаревших файлов: {cleaned_count}")
    print(f"   📁 Директория хранения       : {version_storage_dir}")
    print(f"   📄 Путь к манифесту версии   : {json_filepath}")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()