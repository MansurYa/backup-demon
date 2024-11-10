import argparse
import json
import os
import re
import time
import hashlib
import shutil
import sys
import atexit
import logging
from signal import signal, SIGTERM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("backupd.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

PATH_TO_CONFIG_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
PATH_TO_CHECKSUMS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checksums.json')


def remove_escape_characters(path):
    """
    Удаляет экранирующие символы (обратные слеши) из строки пути.

    Args:
        path (str): Строка пути с экранирующими символами.

    Returns:
        str: Строка без экранирующих символов.
    """
    return path.replace('\\', '')


def is_valid_mac_path(path):
    """
    Проверяет валидность пути в Mac OS.

    Args:
        path (str): Путь для проверки.

    Returns:
        bool: True, если путь валиден, иначе False.
    """
    path = remove_escape_characters(path)
    if not path.startswith('/'):
        return False
    if re.search(r'[\\:]', path):
        return False
    return True


def get_config_file(path):
    """
    Загружает конфигурационный файл и проверяет его содержимое.

    Args:
        path (str): Путь к конфигурационному файлу.

    Returns:
        dict: Содержимое конфигурационного файла.
    """
    try:
        with open(path, 'r+') as file:
            config = json.load(file)

            # Проверка обязательных полей
            if 'interval' not in config or not isinstance(config['interval'], int) or config['interval'] < 0:
                config['interval'] = 300  # Значение по умолчанию
                logging.warning("Некорректное значение 'interval' в конфигурации. Установлено значение по умолчанию 300.")

            if 'backup_destination' not in config or not isinstance(config['backup_destination'], str) or not is_valid_mac_path(config['backup_destination']):
                config_folder = os.path.dirname(os.path.abspath(path))
                config['backup_destination'] = os.path.join(config_folder, 'backup/')
                logging.warning("Некорректное значение 'backup_destination' в конфигурации. Установлен путь по умолчанию.")

            if 'items_to_backup' not in config or not isinstance(config['items_to_backup'], list) or \
                    not all(isinstance(item, str) and is_valid_mac_path(item) for item in config['items_to_backup']):
                config['items_to_backup'] = []  # Пустой список по умолчанию
                logging.warning("Некорректное значение 'items_to_backup' в конфигурации. Установлен пустой список.")

            # Сохраняем обновлённую конфигурацию
            file.seek(0)
            json.dump(config, file, indent=4)
            file.truncate()

            logging.info(f"Конфигурационный файл '{path}' успешно загружен.")
            return config

    except FileNotFoundError:
        logging.warning(f"Файл '{path}' не найден. Создаётся новый файл с настройками по умолчанию.")
        config = {
            "interval": 300,
            "backup_destination": os.path.join(os.path.dirname(os.path.abspath(path)), 'backup/'),
            "items_to_backup": []
        }
        with open(path, 'w+') as file:
            json.dump(config, file, indent=4)
        return config

    except json.JSONDecodeError:
        logging.error(f"Файл '{path}' содержит некорректные данные JSON.")
        sys.exit(1)


def save_json_file(json_object, path_to_json_file):
    """
    Сохраняет объект JSON в указанный файл.

    Args:
        json_object (dict): Объект для сохранения.
        path_to_json_file (str): Путь к файлу.

    Returns:
        None
    """
    try:
        with open(path_to_json_file, 'w', encoding='utf-8') as config_file:
            json.dump(json_object, config_file, ensure_ascii=False, indent=4)
        logging.info(f"Конфигурация успешно сохранена в '{path_to_json_file}'.")
    except Exception as e:
        logging.error(f"Ошибка при сохранении конфигурации: {e}")


def is_path_exist(path):
    """
    Проверяет существование директории или файла по указанному пути.

    Args:
        path (str): Путь для проверки.

    Returns:
        str: 'file' если файл, 'directory' если директория, 'not exists' если не существует.
    """
    if os.path.exists(path):
        if os.path.isfile(path):
            return 'file'
        elif os.path.isdir(path):
            return 'directory'
    else:
        return 'not exists'


def not_included_in_other_directories(path, list_of_paths):
    """
    Проверяет, не является ли путь поддиректорией другого пути в списке.

    Args:
        path (str): Путь для проверки.
        list_of_paths (list): Список путей.

    Returns:
        bool: True, если путь не является поддиректорией другого пути.
    """
    for other_path in list_of_paths:
        if path != other_path and os.path.commonpath([path, other_path]) == other_path:
            return False
    return True


def get_files_from_directory(directory_path):
    """
    Рекурсивно собирает все файлы из директории и её поддиректорий.

    Args:
        directory_path (str): Путь к директории.

    Returns:
        list: Список файлов.
    """
    files_list = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            files_list.append(os.path.join(root, file))
    return files_list


def get_filtered_files_list(list_of_paths):
    """
    Фильтрует список путей, оставляя только существующие файлы и директории,
    исключая вложенные пути.

    Args:
        list_of_paths (list): Список путей для фильтрации.

    Returns:
        list: Отфильтрованный список файлов.
    """
    absolute_paths = [os.path.realpath(path) for path in list_of_paths]
    existing_paths = [(path, is_path_exist(path)) for path in absolute_paths if is_path_exist(path) != 'not exists']
    existing_paths_set = set([p[0] for p in existing_paths])
    pre_filtered_paths = []
    for path, path_type in existing_paths:
        if not_included_in_other_directories(path, existing_paths_set):
            pre_filtered_paths.append((path, path_type))
    final_paths = set()
    for path, path_type in pre_filtered_paths:
        if path_type == 'directory':
            final_paths.update(get_files_from_directory(path))
        elif path_type == 'file':
            final_paths.add(path)
    return list(final_paths)


def calculate_checksum(file_path):
    """
    Вычисляет контрольную сумму MD5 для указанного файла.

    Args:
        file_path (str): Путь к файлу.

    Returns:
        str: Контрольная сумма или None, если файл не найден.
    """
    try:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except (FileNotFoundError, PermissionError) as e:
        logging.error(f"Ошибка доступа к файлу '{file_path}': {e}")
        return None
    except Exception as e:
        logging.error(f"Ошибка при вычислении контрольной суммы файла '{file_path}': {e}")
        return None


def get_checksums_json(path):
    """
    Загружает файл с контрольными суммами.

    Args:
        path (str): Путь к файлу контрольных сумм.

    Returns:
        dict: Содержимое файла с контрольными суммами.
    """
    try:
        with open(path, 'r+') as file:
            checksums = json.load(file)
        logging.info(f"Файл контрольных сумм '{path}' успешно загружен.")
        return checksums
    except FileNotFoundError:
        logging.warning(f"Файл контрольных сумм '{path}' не найден. Создаётся новый файл.")
        checksums = {}
        with open(path, 'w+') as file:
            json.dump(checksums, file, indent=4)
        return checksums
    except json.JSONDecodeError:
        logging.error(f"Файл контрольных сумм '{path}' содержит некорректные данные JSON.")
        sys.exit(1)


def copy_file(source, destination):
    """
    Копирует файл из источника в назначение, сохраняя метаданные.

    Args:
        source (str): Путь к исходному файлу.
        destination (str): Путь к файлу назначения.

    Returns:
        None
    """
    try:
        if os.path.isdir(destination):
            raise IsADirectoryError(f"'{destination}' является директорией, а не файлом.")
        if os.path.exists(destination) and os.path.samefile(source, destination):
            raise ValueError("Исходный и целевой файлы совпадают. Копирование невозможно.")
        destination_folder = os.path.dirname(destination)
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        shutil.copy2(source, destination)
        logging.info(f"Файл '{source}' успешно скопирован в '{destination}'.")
    except Exception as e:
        logging.error(f"Ошибка при копировании файла из '{source}' в '{destination}': {e}")


def daemon_main():
    """
    Основная функция демона, выполняющая резервное копирование.
    """
    while True:
        config = get_config_file(PATH_TO_CONFIG_JSON)
        list_of_file_paths = get_filtered_files_list(config['items_to_backup'])
        checksums = get_checksums_json(PATH_TO_CHECKSUMS_JSON)

        for file_path in list_of_file_paths:
            file_checksum = calculate_checksum(file_path)
            if file_checksum is None:
                continue  # Пропускаем файлы, которые не удалось обработать

            backup_file_checksum = checksums.get(file_path, "0")

            if file_checksum != backup_file_checksum:
                checksums[file_path] = file_checksum
                backup_destination = os.path.join(config['backup_destination'], os.path.relpath(file_path, '/'))
                copy_file(file_path, backup_destination)

        save_json_file(checksums, PATH_TO_CHECKSUMS_JSON)
        logging.info("Цикл резервного копирования завершён. Ожидание следующего запуска...")
        time.sleep(config["interval"])


def start_daemon():
    """
    Запускает демона резервного копирования.
    """
    pidfile = '/tmp/backupd.pid'

    if os.path.exists(pidfile):
        with open(pidfile, 'r') as f:
            pid = f.read().strip()
            if pid:
                logging.error(f"Демон уже запущен с PID: {pid}")
                print(f"Демон уже запущен с PID: {pid}")
                sys.exit(1)

    def remove_pidfile():
        os.remove(pidfile)
        logging.info("Демон остановлен и PID-файл удалён.")

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logging.error(f"Ошибка форка: {e}")
        sys.exit(1)

    os.setsid()

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        logging.error(f"Ошибка второго форка: {e}")
        sys.exit(1)

    sys.stdout.flush()
    sys.stderr.flush()

    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())

    with open('/dev/null', 'a') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())

    with open('/dev/null', 'a') as f:
        os.dup2(f.fileno(), sys.stderr.fileno())

    with open(pidfile, 'w') as f:
        f.write(str(os.getpid()))

    atexit.register(remove_pidfile)
    signal(SIGTERM, lambda signum, frame: sys.exit(0))

    logging.info("Демон успешно запущен.")
    daemon_main()


def stop_daemon():
    """
    Останавливает демона резервного копирования.
    """
    pidfile = '/tmp/backupd.pid'
    if os.path.exists(pidfile):
        with open(pidfile, 'r') as f:
            pid = int(f.read().strip())
            try:
                os.kill(pid, SIGTERM)
                logging.info(f"Демон с PID {pid} успешно остановлен.")
            except OSError as e:
                logging.error(f"Ошибка при остановке демона с PID {pid}: {e}")
        os.remove(pidfile)
        logging.info(f"PID-файл {pidfile} удалён.")
    else:
        logging.warning(f"PID-файл не найден. Демон, возможно, не был запущен.")


def list_backup_items():
    """
    Выводит список файлов и папок, которые находятся в процессе резервного копирования.
    """
    config = get_config_file(PATH_TO_CONFIG_JSON)
    items = config.get('items_to_backup', [])

    if items:
        logging.info("Получен список файлов и папок для резервного копирования.")
        print("Список файлов и папок для резервного копирования:")
        for item in items:
            print(f" - {item}")
    else:
        logging.info("Список файлов и папок для резервного копирования пуст.")
        print("Список файлов и папок для резервного копирования пуст.")


def add_backup_item(item_path):
    """
    Добавляет файл или папку в список резервного копирования.

    :param item_path: Путь к файлу или папке.
    """
    absolute_path = os.path.realpath(item_path)
    absolute_path = remove_escape_characters(absolute_path)

    if not is_valid_mac_path(absolute_path):
        logging.error(f"Ошибка: Путь '{item_path}' некорректен.")
        print(f"Ошибка: Путь '{item_path}' некорректен.")
        return

    path_type = is_path_exist(absolute_path)
    if path_type == 'not exists':
        logging.error(f"Ошибка: Путь '{absolute_path}' не существует.")
        print(f"Ошибка: Путь '{absolute_path}' не существует.")
        return

    config = get_config_file(PATH_TO_CONFIG_JSON)
    items_to_backup = config.get('items_to_backup', [])

    if absolute_path in items_to_backup:
        logging.info(f"Путь '{absolute_path}' уже находится в списке резервного копирования.")
        print(f"Путь '{absolute_path}' уже находится в списке резервного копирования.")
        return

    items_to_backup.append(absolute_path)
    config['items_to_backup'] = items_to_backup
    save_json_file(config, PATH_TO_CONFIG_JSON)

    logging.info(f"Путь '{absolute_path}' успешно добавлен в список резервного копирования.")
    print(f"Путь '{absolute_path}' успешно добавлен в список резервного копирования.")


def remove_backup_item(item_path):
    """
    Удаляет файл или папку из списка резервного копирования.

    :param item_path: Путь к файлу или папке.
    """
    absolute_path = os.path.realpath(item_path)
    absolute_path = remove_escape_characters(absolute_path)

    if not is_valid_mac_path(absolute_path):
        logging.error(f"Ошибка: Путь '{item_path}' некорректен.")
        print(f"Ошибка: Путь '{item_path}' некорректен.")
        return

    path_type = is_path_exist(absolute_path)
    if path_type == 'not exists':
        logging.error(f"Ошибка: Путь '{absolute_path}' не существует.")
        print(f"Ошибка: Путь '{absolute_path}' не существует.")
        return

    config = get_config_file(PATH_TO_CONFIG_JSON)
    items_to_backup = config.get('items_to_backup', [])

    if absolute_path in items_to_backup:
        items_to_backup.remove(absolute_path)
        config['items_to_backup'] = items_to_backup
        save_json_file(config, PATH_TO_CONFIG_JSON)
        logging.info(f"Путь '{absolute_path}' успешно удалён из списка резервного копирования.")
        print(f"Путь '{absolute_path}' успешно удалён из списка резервного копирования.")
    else:
        logging.warning(f"Путь '{absolute_path}' не найден в списке резервного копирования.")
        print(f"Путь '{absolute_path}' не найден в списке резервного копирования.")


def update_sleep_interval(interval):
    """
    Изменяет интервал времени между резервными копиями.

    :param interval: Время в секундах.
    """
    if not isinstance(interval, int) or interval <= 0:
        logging.error(f"Ошибка: Интервал '{interval}' должен быть положительным целым числом.")
        print(f"Ошибка: Интервал '{interval}' должен быть положительным целым числом.")
        return

    config = get_config_file(PATH_TO_CONFIG_JSON)
    config['interval'] = interval
    save_json_file(config, PATH_TO_CONFIG_JSON)

    logging.info(f"Интервал резервного копирования успешно изменён на {interval} секунд.")
    print(f"Интервал резервного копирования успешно изменён на {interval} секунд.")


def change_backup_destination(new_path):
    """
    Изменяет папку для хранения резервных копий, переносит файлы в новую папку,
    удаляет старую папку и очищает файл с контрольными суммами.

    :param new_path: Путь к новой папке.
    """
    absolute_new_path = os.path.realpath(new_path)
    absolute_new_path = remove_escape_characters(absolute_new_path)

    # Проверка валидности нового пути
    if not is_valid_mac_path(absolute_new_path):
        logging.error(f"Ошибка: Путь '{new_path}' некорректен.")
        print(f"Ошибка: Путь '{new_path}' некорректен.")
        return

    # Проверка, что новый путь существует и является директорией
    if is_path_exist(absolute_new_path) != 'directory':
        try:
            os.makedirs(absolute_new_path)
            logging.info(f"Создана новая директория для резервных копий: '{absolute_new_path}'.")
        except OSError as e:
            logging.error(f"Ошибка при создании директории '{absolute_new_path}': {e}")
            print(f"Ошибка при создании директории '{absolute_new_path}': {e}")
            return

    # Получаем текущую конфигурацию и старую папку резервного копирования
    config = get_config_file(PATH_TO_CONFIG_JSON)
    old_backup_folder = config.get('backup_destination', '')

    if is_path_exist(old_backup_folder) != 'directory':
        logging.error(f"Ошибка: Старая папка резервного копирования '{old_backup_folder}' не существует.")
        print(f"Ошибка: Старая папка резервного копирования '{old_backup_folder}' не существует.")
        return

    try:
        # Переносим файлы из старой папки в новую
        for root, dirs, files in os.walk(old_backup_folder):
            relative_path = os.path.relpath(root, old_backup_folder)
            destination_dir = os.path.join(absolute_new_path, relative_path)

            if not os.path.exists(destination_dir):
                os.makedirs(destination_dir)

            for file in files:
                source_file = os.path.join(root, file)
                destination_file = os.path.join(destination_dir, file)
                try:
                    shutil.move(source_file, destination_file)
                    logging.info(f"Файл '{file}' перемещен в '{destination_file}'.")
                except Exception as e:
                    logging.error(f"Ошибка при перемещении файла '{source_file}': {e}")

        # Удаляем старую папку после успешного переноса всех файлов
        shutil.rmtree(old_backup_folder)
        logging.info(f"Старая папка резервного копирования '{old_backup_folder}' успешно удалена.")
        print(f"Старая папка резервного копирования '{old_backup_folder}' успешно удалена.")

        # Очищаем файл с контрольными суммами
        if os.path.exists(PATH_TO_CHECKSUMS_JSON):
            try:
                with open(PATH_TO_CHECKSUMS_JSON, 'w') as checksums_file:
                    json.dump({}, checksums_file, indent=4)
                logging.info(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' успешно очищен.")
                print(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' успешно очищен.")
            except Exception as e:
                logging.error(f"Ошибка при очистке файла контрольных сумм '{PATH_TO_CHECKSUMS_JSON}': {e}")
        else:
            logging.warning(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' не найден для очистки.")
            print(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' не найден для очистки.")

        # Обновляем путь для резервных копий в конфигурации
        config['backup_destination'] = absolute_new_path
        save_json_file(config, PATH_TO_CONFIG_JSON)
        logging.info(f"Папка для резервного копирования успешно изменена на '{absolute_new_path}'.")
        print(f"Папка для резервного копирования успешно изменена на '{absolute_new_path}'.")

    except Exception as e:
        logging.error(f"Ошибка при перемещении файлов или изменении папки резервного копирования: {e}")
        print(f"Ошибка при перемещении файлов или изменении папки резервного копирования: {e}")


def clear_backup_folder():
    """
    Полностью очищает папку, в которую копируются все резервные копии, и обнуляет файл с контрольными суммами.
    """
    config = get_config_file(PATH_TO_CONFIG_JSON)
    backup_folder = config.get('backup_destination', '')

    if is_path_exist(backup_folder) != 'directory':
        logging.error(f"Ошибка: Папка для резервного копирования '{backup_folder}' не существует или не является директорией.")
        print(f"Ошибка: Папка для резервного копирования '{backup_folder}' не существует или не является директорией.")
        return

    try:
        # Очищаем файлы и директории в папке резервного копирования
        for root, dirs, files in os.walk(backup_folder):
            for file in files:
                try:
                    os.remove(os.path.join(root, file))
                except Exception as e:
                    logging.error(f"Ошибка при удалении файла '{file}': {e}")
            for dir in dirs:
                try:
                    shutil.rmtree(os.path.join(root, dir))
                except Exception as e:
                    logging.error(f"Ошибка при удалении директории '{dir}': {e}")

        logging.info(f"Папка для резервного копирования '{backup_folder}' успешно очищена.")
        print(f"Папка для резервного копирования '{backup_folder}' успешно очищена.")

        # Проверка существования файла с контрольными суммами и его очистка
        if os.path.exists(PATH_TO_CHECKSUMS_JSON):
            try:
                with open(PATH_TO_CHECKSUMS_JSON, 'w') as checksums_file:
                    json.dump({}, checksums_file, indent=4)
                logging.info(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' успешно очищен.")
                print(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' успешно очищен.")
            except Exception as e:
                logging.error(f"Ошибка при очистке файла контрольных сумм '{PATH_TO_CHECKSUMS_JSON}': {e}")
        else:
            logging.warning(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' не найден для очистки.")
            print(f"Файл контрольных сумм '{PATH_TO_CHECKSUMS_JSON}' не найден для очистки.")

    except Exception as e:
        logging.error(f"Ошибка при очистке папки или файла контрольных сумм: {e}")
        print(f"Ошибка при очистке папки или файла контрольных сумм: {e}")


def paste_backup(target_dir):
    """
    Вставляет файлы из резервной копии в указанную папку.

    :param target_dir: Путь к папке для вставки.
    :return: None
    """
    absolute_target_dir = os.path.realpath(target_dir)
    absolute_target_dir = remove_escape_characters(absolute_target_dir)

    if not is_valid_mac_path(absolute_target_dir):
        logging.error(f"Ошибка: Путь '{target_dir}' некорректен.")
        print(f"Ошибка: Путь '{target_dir}' некорректен.")
        return

    if is_path_exist(absolute_target_dir) != 'directory':
        logging.error(f"Ошибка: Путь '{absolute_target_dir}' не существует или не является директорией.")
        print(f"Ошибка: Путь '{absolute_target_dir}' не существует или не является директорией.")
        return

    config = get_config_file(PATH_TO_CONFIG_JSON)
    backup_folder = config.get('backup_destination', '')

    if is_path_exist(backup_folder) != 'directory':
        logging.error(f"Ошибка: Папка для резервного копирования '{backup_folder}' не существует.")
        print(f"Ошибка: Папка для резервного копирования '{backup_folder}' не существует.")
        return

    try:
        for root, dirs, files in os.walk(backup_folder):
            relative_path = os.path.relpath(root, backup_folder)
            destination_dir = os.path.join(absolute_target_dir, relative_path)

            if not os.path.exists(destination_dir):
                os.makedirs(destination_dir)

            for file in files:
                source_file = os.path.join(root, file)
                destination_file = os.path.join(destination_dir, file)
                shutil.copy2(source_file, destination_file)

        logging.info(f"Файлы успешно восстановлены из резервной копии в папку '{absolute_target_dir}'.")
        print(f"Файлы успешно восстановлены из резервной копии в папку '{absolute_target_dir}'.")
    except Exception as e:
        logging.error(f"Ошибка при восстановлении файлов: {e}")
        print(f"Ошибка при восстановлении файлов: {e}")


def show_logs():
    """
    Выводит последние строки из файла логов.
    """
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backupd.log')

    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()[-50:]  # Последние 50 строк
            for line in lines:
                print(line, end="")
    except FileNotFoundError:
        logging.warning(f"Файл логов '{log_file}' не найден.")
        print(f"Файл логов '{log_file}' не найден.")
    except Exception as e:
        logging.error(f"Ошибка при чтении файла логов: {e}")
        print(f"Ошибка при чтении файла логов: {e}")


def restart():
    """
    Перезапускает демона резервного копирования.
    Сначала останавливает текущий экземпляр, затем запускает его снова.
    """
    try:
        logging.info("Попытка перезапуска демона...")
        print("Перезапуск демона...")

        # Остановка демона
        stop_daemon()

        # Запуск демона
        start_daemon()

        logging.info("Демон успешно перезапущен.")
        print("Демон успешно перезапущен.")

    except Exception as e:
        logging.error(f"Ошибка при перезапуске демона: {e}")
        print(f"Ошибка при перезапуске демона: {e}")


def main():
    parser = argparse.ArgumentParser(description='Утилита для управления демоном резервного копирования')

    subparser = parser.add_subparsers(dest='command', help='Команды для управления демоном')

    parser_start = subparser.add_parser('start', help='Запускает демона резервного копирования')

    parser_stop = subparser.add_parser('stop', help='Останавливает демона резервного копирования')

    parser_list = subparser.add_parser('list', help='Показывает список файлов и папок для резервного копирования')

    parser_add = subparser.add_parser('add', help='Добавляет файл или папку для резервного копирования')
    parser_add.add_argument('path_to_file', type=str, help='Путь к файлу или папке для добавления')

    parser_remove = subparser.add_parser('remove', help='Удаляет файл или папку из списка резервного копирования')
    parser_remove.add_argument('path_to_file', type=str, help='Путь к файлу или папке для удаления')

    parser_set_interval = subparser.add_parser('set_interval', help='Устанавливает интервал резервного копирования')
    parser_set_interval.add_argument('interval', type=int, help='Интервал в секундах между резервными копиями.')

    parser_change_destination = subparser.add_parser('change_destination', help='Изменяет папку для резервных копий')
    parser_change_destination.add_argument('path_to_folder', type=str, help='Путь к новой папке для резервных копий')

    parser_clear_destination = subparser.add_parser('clear_destination', help='Полностью очищает папку для резервных копий')

    # parser_restore = subparser.add_parser('restore', help='Восстанавливает файлы из резервной копии')
    # parser_restore.add_argument('target_dir', type=str, nargs='?', default=None, help='Путь к папке для восстановления (необязательно)')
    # parser_restore.add_argument() - папка или файл который нужно востановить

    parser_paste = subparser.add_parser('paste', help='Вставляет файлы из резервной копии в указанную папку')
    parser_paste.add_argument('target_dir', type=str, default=None, help='Путь к папке для вставки')

    parser_logs = subparser.add_parser('logs', help='Выводит логи работы демона')

    parser_restart = subparser.add_parser('restart', help='Перезапускает демона резервного копирования')

    args = parser.parse_args()

    if args.command == 'start':
        start_daemon()
    elif args.command == 'stop':
        stop_daemon()
    elif args.command == 'list':
        list_backup_items()
    elif args.command == 'add':
        add_backup_item(args.path_to_file)
    elif args.command == 'remove':
        remove_backup_item(args.path_to_file)
    elif args.command == 'set_interval':
        update_sleep_interval(args.interval)
    elif args.command == 'change_destination':
        change_backup_destination(args.path_to_folder)
    elif args.command == 'clear_destination':
        clear_backup_folder()
    elif args.command == 'paste':
        paste_backup(args.target_dir)
    elif args.command == 'logs':
        show_logs()
    elif args.command == 'restart':
        restart()


if __name__ == "__main__":
    main()
