# Backup Daemon

## Описание

Backup Daemon — это инструмент для автоматического регулярного резервного копирования данных. Он работает в фоновом режиме и позволяет пользователям легко управлять процессом резервного копирования через командную строку. Демон поддерживает гибкую настройку, включая выбор каталогов для резервного копирования и установку интервала между копиями.

## Требования

- Python 3.9 или выше
- Ubuntu 22
- Необходимые библиотеки из `requirements.txt`

## Установка

1. **Клонирование репозитория:**

   Сначала клонируйте репозиторий на ваш локальный компьютер:

   ```bash
   git clone https://github.com/MansurYa/backup-demon.git
   cd backup-demon
   ```

2. **Установка зависимостей:**

   Установите необходимые зависимости с помощью pip:

   ```bash
   pip install -r requirements.txt
   ```

3. **Настройка системы:**

   Создайте необходимые директории и установите права доступа:

   ```bash
   sudo mkdir -p /etc/backupd
   sudo mkdir -p /var/lib/backupd
   sudo mkdir -p /var/log/backupd
   sudo mkdir -p /opt/backupd
   ```

   Скопируйте файлы `backupd.py` и `config.json`:

   ```bash
   sudo cp main.py /opt/backupd/backupd.py
   sudo cp config.json /etc/backupd/config.json
   ```

   Создайте системного пользователя `backupd`:

   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin backupd
   ```

   Установите правильные права доступа:

   ```bash
   sudo chown backupd:backupd /opt/backupd/backupd.py
   sudo chmod 750 /opt/backupd/backupd.py
   sudo chown backupd:backupd /etc/backupd/config.json
   sudo chmod 640 /etc/backupd/config.json
   sudo chown -R backupd:backupd /var/lib/backupd
   sudo chmod -R 750 /var/lib/backupd
   sudo chown -R backupd:backupd /var/log/backupd
   sudo chmod -R 750 /var/log/backupd
   ```

4. **Создание службы systemd:**

   Создайте файл службы `/etc/systemd/system/backupd.service`:

   ```bash
   sudo nano /etc/systemd/system/backupd.service
   ```

   Вставьте в него следующий контент:

   ```
   [Unit]
   Description=Backup Daemon
   After=network.target

   [Service]
   Type=simple
   User=backupd
   Group=backupd
   ExecStart=/opt/backupd/backupd.py start
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   Перезагрузите конфигурацию systemd и запустите службу:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable backupd.service
   sudo systemctl start backupd.service
   ```

   Проверьте статус службы:

   ```bash
   sudo systemctl status backupd.service
   ```

5. **Создание команды `backupd`:**

   Сделайте скрипт `backupd.py` исполняемым:

   ```bash
   sudo chmod +x /opt/backupd/backupd.py
   ```

   Создайте символическую ссылку для команды `backupd`:

   ```bash
   sudo ln -s /opt/backupd/backupd.py /usr/local/bin/backupd
   ```

   Теперь вы можете вызывать команду `backupd` из любой директории.

## Настройка

- Отредактируйте файл `config.json`, чтобы указать каталоги для резервного копирования и установить интервал между копиями. Пример содержимого файла:

  ```json
  {
      "interval": 500,
      "backup_destination": "/path/to/backup/directory",
      "items_to_backup": ["/path/to/source/directory"]
  }
  ```

## Использование

- **Запуск демона:**

  Чтобы запустить демон, используйте команду:

  ```bash
  backupd start
  ```

- **Остановка демона:**

  Чтобы остановить демон, используйте команду:

  ```bash
  backupd stop
  ```

- **Просмотр списка файлов для резервного копирования:**

  Чтобы увидеть список файлов и папок, которые находятся в процессе резервного копирования, используйте:

  ```bash
  backupd list
  ```

- **Добавление файла или папки для резервного копирования:**

  Чтобы добавить файл или папку в список резервного копирования, используйте:

  ```bash
  backupd add /path/to/your/file_or_directory
  ```

- **Удаление файла или папки из списка резервного копирования:**

  Чтобы удалить файл или папку из списка резервного копирования, используйте:

  ```bash
  backupd remove /path/to/your/file_or_directory
  ```

- **Установка интервала резервного копирования:**

  Чтобы установить интервал времени (в секундах) между резервными копиями, используйте:

  ```bash
  backupd set_interval 600
  ```

- **Изменение папки для резервных копий:**

  Чтобы изменить папку для хранения резервных копий, используйте:

  ```bash
  backupd change_destination /new/backup/directory
  ```

- **Очистка папки для резервных копий:**

  Чтобы полностью очистить папку, в которую копируются все резервные копии, используйте:

  ```bash
  backupd clear_destination
  ```

- **Восстановление файлов из резервной копии:**

  Чтобы вставить файлы из резервной копии в указанную папку, используйте:

  ```bash
  backupd paste /path/to/restore/directory
  ```

- **Просмотр логов работы демона:**

  Чтобы вывести последние строки из файла логов, используйте:

  ```bash
  backupd logs
  ```

- **Перезапуск демона:**

  Чтобы перезапустить демон, используйте:

  ```bash
  backupd restart
  ```

## Логи и мониторинг

- Логи работы демона сохраняются в файл `/var/log/backupd/backupd.log`. Вы можете просматривать их для отладки и мониторинга работы демона.
