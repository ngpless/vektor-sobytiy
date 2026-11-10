# Вектор событий

Учебный сайт вымышленного агентства по организации праздников (эксплуатационная практика, направление «Бизнес-информатика»). Язык: Python, фреймворк Flask 3.1.3, база данных SQLite, оформление и скрипты написаны вручную. CMS и конструкторы сайтов не используются. Агентство, адрес, телефон и почта условные.

## Состав

- 9 страниц с контентом: главная, «Об агентстве», пять разделов (по пять статей), новости, контакты; карта сайта (`/sitemap`) и страница 404.
- Пять компонентов: баннеры, контакты, обмен сообщениями, лента новостей, поиск.
- Два стиля оформления: стандартный и версия для слабовидящих (ГОСТ Р 52872-2019); выбор запоминается.
- Три роли: клиент, менеджер, администратор; два сценария создания пользователя (регистрация и создание клиента сотрудником).

## Запуск на своём компьютере

Нужен Python 3.9 или новее. Из папки проекта (Windows):

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Linux и macOS: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python3 app.py`.

Сайт откроется по адресу http://127.0.0.1:5000/. База данных создаётся и заполняется при первом запуске (25 статей, 8 новостей, 5 баннеров, 3 тестовые записи). Чтобы вернуть начальное состояние, остановите сервер, удалите `instance/vektor.db` и запустите снова. Другой порт: переменная окружения `PORT`.

Необязательные переменные окружения: `VEKTOR_SECRET` (секретный ключ сессий; если не задан, ключ создаётся в `instance/secret.key`), `VEKTOR_DB` (путь к файлу базы данных).

## Тестовые учётные записи

| Роль | Логин | Пароль |
|---|---|---|
| Клиент | `client` | `Client2025vektor` |
| Менеджер | `manager` | `Manager2025vektor` |
| Администратор | `admin` | задаётся в `seed.py` |

Вход: `/login`. В базе хранятся только хеши паролей (scrypt).

## Запуск через Apache из XAMPP (обратный прокси)

1. Запустить Flask (порт 5000) и не закрывать окно.
2. В `C:\xampp\apache\conf\httpd.conf` включить модули `proxy_module`, `proxy_http_module`, `headers_module` (в XAMPP по умолчанию закомментирован только `proxy_http_module`) и строку `Include conf/extra/httpd-vhosts.conf`.
3. В `C:\xampp\apache\conf\extra\httpd-vhosts.conf` добавить:

```
<VirtualHost *:80>
    ServerName vektor.localhost
    ServerAlias localhost
    ProxyPreserveHost On
    ProxyRequests Off
    ProxyPass        / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/
</VirtualHost>
```

4. Запустить Apache в панели XAMPP и открыть http://vektor.localhost/. Если порт 80 занят, изменить `Listen 80` на `Listen 8080` в `httpd.conf` и `*:80` на `*:8080` в блоке виртуального хоста.

## Размещение на бесплатном хостинге (PythonAnywhere)

1. Зарегистрироваться на pythonanywhere.com (тариф Beginner).
2. В консоли Bash получить код проекта (`git clone <ссылка на репозиторий>`) и создать окружение: `python3 -m venv ~/venv-vektor && source ~/venv-vektor/bin/activate && pip install -r requirements.txt`.
3. Вкладка Web: Add a new web app, Manual configuration, версия Python 3.10 или новее; указать Source code и Working directory (папка проекта) и Virtualenv (`~/venv-vektor`).
4. В WSGI-файле хостинга вставить:

```
import sys, os
path = '/home/ЛОГИН/vektor-events'
if path not in sys.path:
    sys.path.insert(0, path)
os.environ['VEKTOR_SECRET'] = 'длинная-случайная-строка'
from wsgi import application
```

5. Нажать Reload и открыть `https://ЛОГИН.pythonanywhere.com/`.

## Структура файлов

`app.py` (маршруты), `db.py` (схема SQLite), `seed.py` (начальное наполнение), `security.py` (CSRF, роли, проверка пароля), `app_hash.py` (хеширование), `textfmt.py` (разметка статей), `content_a.py`, `content_b.py`, `content_c.py` (тексты статей и новостей), `wsgi.py` (точка входа WSGI), `templates/` (шаблоны Jinja2), `static/` (стили, скрипты, значок сайта).
