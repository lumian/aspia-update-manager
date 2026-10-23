# Aspia update manager

## Использование:
```
  ./aspia_manager.py                                     # Показать это сообщение

  [Управление релизами]
  ./aspia_manager.py download <версия>                   # Скачать файлы, очистить лишнее и создать манифест

  [Управление каналами обновлений]
  ./aspia_manager.py channel create <канал>              # Создать или сбросить канал (stable, beta, alpha)
  ./aspia_manager.py channel <канал> latest <версия>     # Установить последнюю версию для канала
  ./aspia_manager.py channel <канал> add <источник> <цель> # Добавить правило обновления (напр. 3.0.37 @latest)
  ./aspia_manager.py channel <канал> remove <источник>   # Удалить правило обновления для версии-источника
  ./aspia_manager.py channel <канал> list                # Показать текущую конфигурацию канала

  [Проверка целостности]
  ./aspia_manager.py check                               # Проверить целостность всей конфигурации репозитория
```

## Параметры:
```
  <канал>   - Имя канала: только "stable", "beta" или "alpha"
  <версия>  - Версия Aspia в формате "3.a.b" (например: 3.1.2)
  <источник>- Версия, с которой выполняется обновление (например: 3.0.37)
  <цель>    - Версия назначения или метка "@latest"
```
## Примеры:
```
  ./aspia_manager.py download 3.1.2
  ./aspia_manager.py channel create stable
  ./aspia_manager.py channel stable latest 3.1.2
  ./aspia_manager.py channel stable add 3.0.37 @latest
  ./aspia_manager.py check
```

## Настройка:
```
  Откройте скрипт в текстовом редакторе и измените переменные в блоке CONFIG:
  - TARGET_ROOT_DIR     : Корневая директория сервера обновлений (здесь лежат <канал>.json и папка versions/).
  - TARGET_STORAGE_DIR  : Абсолютный путь к директории хранения инсталляторов.
  - UPDATE_BASE_URL     : Публичный URL-путь к директории storage.
  - DOWNLOAD_MAP        : Словарь, определяющий необходимые компоненты, платформы и расширения.
```

*Примечание: создано с помощью ИИ*