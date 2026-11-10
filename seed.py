"""Начальное наполнение базы данных: разделы, статьи, новости, баннеры, тестовые учётные записи.

Запускается автоматически при первом старте приложения (если файла БД ещё нет)
или вручную:  python seed.py  (пересоздаёт базу с нуля).
"""
import os
import sys
from datetime import datetime, timedelta

from textfmt import word_count

SECTIONS = [
    ("korporativ", "Корпоративные мероприятия", "Корпоративы",
     "Новогодние праздники, конференции, презентации и бюджеты: как организовать деловое событие, которое решает задачу.",
     "stage"),
    ("svadby", "Свадьбы и юбилеи", "Свадьбы и юбилеи",
     "Личные праздники с сильным сценарием: подготовка свадьбы, тайминг дня, камерные форматы и юбилейные вечера.",
     "rings"),
    ("vyezd", "Выездные мероприятия и тимбилдинг", "Выезды и тимбилдинг",
     "Командные программы, квесты и выездные конференции: форматы, логистика и оценка результата.",
     "team"),
    ("tehnika", "Техническое обеспечение", "Техобеспечение",
     "Звук, свет, экраны и электропитание: что нужно знать о технической стороне мероприятия.",
     "sound"),
    ("ploshadki", "Подбор площадок", "Площадки",
     "Как выбрать зал или загородную локацию, осмотреть её и заключить договор без неприятных сюрпризов.",
     "venue"),
]

BANNERS = [
    ("Новогодние корпоративы: запись открыта",
     "Подберём площадку, программу, звук и свет. Первые декабрьские даты уже бронируются.",
     "/razdel/korporativ/novogodniy-korporativ", "Читать календарь подготовки", "stage"),
    ("Свадьбы и юбилеи со сценарием, а не по шаблону",
     "Тайминг дня, подрядчики и координатор на площадке: вы занимаетесь праздником, мы работой.",
     "/razdel/svadby", "Смотреть материалы", "rings"),
    ("Звук и свет без сюрпризов",
     "Своя техническая группа, резервное оборудование и репетиция перед каждым событием.",
     "/razdel/tehnika", "Раздел «Техническое обеспечение»", "sound"),
    ("Площадка под ваш формат",
     "Сравним залы, лофты и загородные локации, организуем осмотр и проверим договор.",
     "/razdel/ploshadki", "Подобрать площадку", "venue"),
    ("Тимбилдинг, после которого хочется работать вместе",
     "Квесты, выездные конференции и командные игры с измеримым результатом.",
     "/razdel/vyezd", "Выбрать формат", "team"),
]

TEST_USERS = [
    # логин, почта, имя, телефон, пароль, роль
    ("admin", "admin@vektor.example.invalid", "Соколова Ирина Павловна", "+7 (000) 000-00-01", "Admin2025vektor", "admin"),
    ("manager", "manager@vektor.example.invalid", "Лебедев Михаил Андреевич", "+7 (000) 000-00-02", "Manager2025vektor", "manager"),
    ("client", "client@vektor.example.invalid", "Орлова Анна Сергеевна", "+7 (000) 000-00-03", "Client2025vektor", "client"),
]


def check_content(articles_by_section, news):
    """Контроль объёма: в каждом разделе не меньше 5 статей по 250-500 слов, новостей не меньше 6."""
    for slug, items in articles_by_section.items():
        assert len(items) >= 5, "В разделе %s меньше 5 статей" % slug
        for a in items:
            n = word_count(a["body"])
            assert 250 <= n <= 500, "Статья %s: %d слов" % (a["slug"], n)
    assert len(news) >= 6, "Новостей меньше шести"


def fill(conn):
    from app_hash import hash_password  # отдельный модуль без Flask, см. ниже
    import content_a, content_b, content_c

    by_section = {
        "korporativ": content_a.KORPORATIV,
        "svadby": content_a.SVADBY,
        "vyezd": content_b.VYEZD,
        "tehnika": content_b.TEHNIKA,
        "ploshadki": content_c.PLOSHADKI,
    }
    check_content(by_section, content_c.NEWS)
    now = datetime.now()

    user_ids = {}
    for login, email, name, phone, password, role in TEST_USERS:
        cur = conn.execute(
            "INSERT INTO users (login, email, full_name, phone, password_hash, role, created_at) VALUES (?,?,?,?,?,?,?)",
            (login, email, name, phone, hash_password(password), role, now.strftime("%Y-%m-%d %H:%M")))
        user_ids[login] = cur.lastrowid

    for pos, (slug, title, short, descr, art) in enumerate(SECTIONS, start=1):
        cur = conn.execute(
            "INSERT INTO sections (slug, title, short_title, description, art_key, position) VALUES (?,?,?,?,?,?)",
            (slug, title, short, descr, art, pos))
        sid = cur.lastrowid
        items = by_section[slug]
        for i, a in enumerate(items):
            published = (now - timedelta(days=60 - pos * 3 - i * 2)).strftime("%Y-%m-%d 10:00")
            conn.execute(
                "INSERT INTO articles (section_id, slug, title, summary, body, author_id, published_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (sid, a["slug"], a["title"], a["summary"], a["body"], user_ids["manager"], published))

    for n in content_c.NEWS:
        published = (now - timedelta(days=n["days_ago"])).strftime("%Y-%m-%d 12:00")
        conn.execute(
            "INSERT INTO news (slug, title, summary, body, author_id, published_at) VALUES (?,?,?,?,?,?)",
            (n["slug"], n["title"], n["summary"], n["body"], user_ids["manager"], published))

    for pos, (title, text, url, link_text, art) in enumerate(BANNERS, start=1):
        conn.execute(
            "INSERT INTO banners (title, text, link_url, link_text, art_key, position) VALUES (?,?,?,?,?,?)",
            (title, text, url, link_text, art, pos))
    conn.commit()


if __name__ == "__main__":
    import db
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.ensure_db()
    print("База создана:", db.DB_PATH)
    sys.exit(0)
