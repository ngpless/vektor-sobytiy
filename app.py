"""Сайт вымышленного агентства мероприятий «Вектор событий».

Python 3 + Flask + Jinja2 + sqlite3. Без CMS и без ORM.
Запуск:  python app.py   или   flask --app app run
"""
import os
import re
import secrets
from datetime import datetime

from flask import (Flask, abort, flash, g, make_response, redirect,
                   render_template, request, session, url_for)
from markupsafe import Markup

import db
from security import (EMAIL_RE, LOGIN_RE, ROLE_TITLES, check_csrf, clear_fails,
                      csrf_token, generate_password, hash_password,
                      login_required, password_problem, register_fail,
                      roles_required, too_many_attempts, verify_password)
from textfmt import highlight, parse_body, word_count

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)


def _load_secret():
    """Секретный ключ: из переменной окружения или из файла instance/secret.key."""
    env = os.environ.get("VEKTOR_SECRET")
    if env:
        return env
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    path = os.path.join(BASE_DIR, "instance", "secret.key")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


app.config.update(
    SECRET_KEY=_load_secret(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    JSON_AS_ASCII=False,
    MAX_CONTENT_LENGTH=256 * 1024,
)

db.ensure_db()

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
STATUS_REQUEST = {"new": "Новая", "work": "В работе", "done": "Выполнена", "rejected": "Отклонена"}
EVENT_TYPES = ["Корпоративное мероприятие", "Свадьба", "Юбилей", "Выездное мероприятие или тимбилдинг",
               "Техническое обеспечение (звук, свет)", "Подбор площадки", "Другое"]
FEEDBACK_TOPICS = ["Общий вопрос", "Расчёт стоимости", "Сотрудничество", "Замечание по работе сайта"]
ART_KEYS = {"stage": "Сцена и свет", "confetti": "Праздник", "sound": "Звук", "venue": "Площадка",
            "rings": "Свадьба", "team": "Выезд и команда"}
DEFAULT_A11Y = {"on": False, "size": 1, "scheme": "bw", "img": True}


# ---------------------------------------------------------------- база данных

def get_db():
    if "db" not in g:
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------- общее

def read_a11y():
    """Настройки версии для слабовидящих хранятся в cookie vektor_a11y = on:size:scheme:img."""
    state = dict(DEFAULT_A11Y)
    raw = request.cookies.get("vektor_a11y", "")
    parts = raw.split(":")
    if len(parts) == 4:
        state["on"] = parts[0] == "1"
        state["size"] = int(parts[1]) if parts[1] in ("1", "2", "3") else 1
        state["scheme"] = parts[2] if parts[2] in ("bw", "wb", "bl") else "bw"
        state["img"] = parts[3] != "0"
    return state


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    uid = session.get("uid")
    if uid:
        user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        if user and user["is_active"]:
            g.user = user
        else:
            session.pop("uid", None)
    if request.method == "POST":
        check_csrf()
    # Сотрудник создал клиенту временный пароль: сначала смена пароля.
    if (g.user and g.user["must_change"] and request.endpoint
            and request.endpoint not in ("password_change", "logout", "static")):
        return redirect(url_for("password_change"))


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


@app.context_processor
def inject_globals():
    nav_sections = query("SELECT slug, short_title, title FROM sections ORDER BY position")
    unread = 0
    if g.user:
        if g.user["role"] == "client":
            unread = query(
                "SELECT COUNT(*) c FROM messages m JOIN dialogs d ON d.id = m.dialog_id "
                "WHERE d.client_id = ? AND m.sender_id != ? AND m.is_read = 0",
                (g.user["id"], g.user["id"]), one=True)["c"]
        else:
            unread = query(
                "SELECT COUNT(*) c FROM messages m JOIN dialogs d ON d.id = m.dialog_id "
                "WHERE m.sender_id = d.client_id AND m.is_read = 0", one=True)["c"]
    return {
        "csrf_token": csrf_token,
        "me": g.user,
        "nav_sections": nav_sections,
        "a11y": read_a11y(),
        "unread": unread,
        "ROLE_TITLES": ROLE_TITLES,
        "STATUS_REQUEST": STATUS_REQUEST,
        "ART_KEYS": ART_KEYS,
        "current_year": datetime.now().year,
    }


@app.template_filter("ru_date")
def ru_date(value):
    try:
        d = datetime.strptime(value[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return value or ""
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


@app.template_filter("ru_datetime")
def ru_datetime(value):
    try:
        d = datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value or ""
    return "%d %s %d, %02d:%02d" % (d.day, MONTHS[d.month - 1], d.year, d.hour, d.minute)


@app.template_filter("blocks")
def blocks_filter(text):
    return parse_body(text)


@app.template_filter("reading_time")
def reading_time(text):
    return max(1, round(word_count(text) / 180))


app.jinja_env.globals["highlight"] = highlight
app.jinja_env.globals["csrf_token"] = csrf_token


def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def translit(text):
    table = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                      "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    out = "".join(table.get(ch, ch) for ch in text.lower())
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out[:60] or "material"


def unique_slug(table, base):
    slug, n = base, 2
    while query("SELECT 1 FROM %s WHERE slug = ?" % table, (slug,), one=True):
        slug = "%s-%d" % (base, n)
        n += 1
    return slug


# ---------------------------------------------------------------- публичные страницы

@app.route("/")
def index():
    banners = query("SELECT * FROM banners WHERE is_active = 1 ORDER BY position, id")
    sections = query(
        "SELECT s.*, (SELECT COUNT(*) FROM articles a WHERE a.section_id = s.id AND a.is_published = 1) AS cnt "
        "FROM sections s ORDER BY position")
    latest_news = query("SELECT * FROM news WHERE is_published = 1 ORDER BY published_at DESC, id DESC LIMIT 3")
    fresh_articles = query(
        "SELECT a.*, s.title AS section_title, s.slug AS section_slug, s.art_key FROM articles a "
        "JOIN sections s ON s.id = a.section_id WHERE a.is_published = 1 "
        "ORDER BY a.published_at DESC, a.id DESC LIMIT 4")
    stats = {
        "articles": query("SELECT COUNT(*) c FROM articles WHERE is_published = 1", one=True)["c"],
        "news": query("SELECT COUNT(*) c FROM news WHERE is_published = 1", one=True)["c"],
        "sections": len(sections),
    }
    return render_template("index.html", banners=banners, sections=sections, latest_news=latest_news,
                           fresh_articles=fresh_articles, stats=stats)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/razdel/<slug>")
def section(slug):
    sec = query("SELECT * FROM sections WHERE slug = ?", (slug,), one=True)
    if sec is None:
        abort(404)
    articles = query("SELECT * FROM articles WHERE section_id = ? AND is_published = 1 "
                     "ORDER BY published_at, id", (sec["id"],))
    return render_template("section.html", sec=sec, articles=articles)


@app.route("/razdel/<slug>/<article_slug>")
def article(slug, article_slug):
    sec = query("SELECT * FROM sections WHERE slug = ?", (slug,), one=True)
    if sec is None:
        abort(404)
    art = query("SELECT * FROM articles WHERE slug = ? AND section_id = ? AND is_published = 1",
                (article_slug, sec["id"]), one=True)
    if art is None:
        abort(404)
    siblings = query("SELECT slug, title FROM articles WHERE section_id = ? AND is_published = 1 "
                     "ORDER BY published_at, id", (sec["id"],))
    idx = [s["slug"] for s in siblings].index(art["slug"])
    prev_a = siblings[idx - 1] if idx > 0 else None
    next_a = siblings[idx + 1] if idx + 1 < len(siblings) else None
    others = query(
        "SELECT a.slug, a.title, s.slug AS section_slug, s.short_title FROM articles a "
        "JOIN sections s ON s.id = a.section_id WHERE a.section_id != ? AND a.is_published = 1 "
        "ORDER BY (a.id * 7 + ?) % 11, a.id LIMIT 3", (sec["id"], art["id"]))
    author = query("SELECT full_name FROM users WHERE id = ?", (art["author_id"],), one=True)
    return render_template("article.html", sec=sec, art=art, prev_a=prev_a, next_a=next_a,
                           siblings=siblings, others=others, author=author)


@app.route("/news")
def news_list():
    page = request.args.get("page", "1")
    page = int(page) if page.isdigit() and int(page) > 0 else 1
    per_page = 6
    total = query("SELECT COUNT(*) c FROM news WHERE is_published = 1", one=True)["c"]
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    items = query("SELECT * FROM news WHERE is_published = 1 ORDER BY published_at DESC, id DESC "
                  "LIMIT ? OFFSET ?", (per_page, (page - 1) * per_page))
    return render_template("news_list.html", items=items, page=page, pages=pages, total=total)


@app.route("/news/<slug>")
def news_item(slug):
    item = query("SELECT * FROM news WHERE slug = ? AND is_published = 1", (slug,), one=True)
    if item is None:
        abort(404)
    more = query("SELECT slug, title, published_at FROM news WHERE is_published = 1 AND id != ? "
                 "ORDER BY published_at DESC, id DESC LIMIT 3", (item["id"],))
    return render_template("news_item.html", item=item, more=more)


@app.route("/contacts", methods=["GET", "POST"])
def contacts():
    form = {"name": "", "email": "", "topic": FEEDBACK_TOPICS[0], "message": ""}
    errors = []
    if g.user:
        form["name"], form["email"] = g.user["full_name"], g.user["email"]
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if len(form["name"]) < 2 or len(form["name"]) > 80:
            errors.append("Укажите имя (от 2 до 80 символов).")
        if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
            errors.append("Укажите адрес электронной почты в формате name@example.ru.")
        if form["topic"] not in FEEDBACK_TOPICS:
            errors.append("Выберите тему обращения из списка.")
        if len(form["message"]) < 10 or len(form["message"]) > 2000:
            errors.append("Сообщение должно содержать от 10 до 2000 символов.")
        if not errors:
            execute("INSERT INTO feedback (name, email, topic, message, created_at) VALUES (?,?,?,?,?)",
                    (form["name"], form["email"], form["topic"], form["message"], now_str()))
            flash("Спасибо! Ваше обращение принято, менеджер ответит на указанную почту.", "ok")
            return redirect(url_for("contacts"))
    return render_template("contacts.html", form=form, errors=errors, topics=FEEDBACK_TOPICS)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()[:100]
    articles, news = [], []
    if q:
        like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        articles = query(
            "SELECT a.*, s.title AS section_title, s.slug AS section_slug FROM articles a "
            "JOIN sections s ON s.id = a.section_id WHERE a.is_published = 1 AND "
            "(PYLOWER(a.title) LIKE ? ESCAPE '\\' OR PYLOWER(a.summary) LIKE ? ESCAPE '\\' "
            "OR PYLOWER(a.body) LIKE ? ESCAPE '\\') ORDER BY a.published_at DESC, a.id", (like, like, like))
        news = query(
            "SELECT * FROM news WHERE is_published = 1 AND (PYLOWER(title) LIKE ? ESCAPE '\\' "
            "OR PYLOWER(summary) LIKE ? ESCAPE '\\' OR PYLOWER(body) LIKE ? ESCAPE '\\') "
            "ORDER BY published_at DESC, id", (like, like, like))
    return render_template("search.html", q=q, articles=articles, news=news)


@app.route("/sitemap")
def sitemap():
    sections = query("SELECT * FROM sections ORDER BY position")
    articles = query("SELECT a.slug, a.title, s.slug AS section_slug FROM articles a "
                     "JOIN sections s ON s.id = a.section_id WHERE a.is_published = 1 ORDER BY a.published_at, a.id")
    news = query("SELECT slug, title FROM news WHERE is_published = 1 ORDER BY published_at DESC, id DESC")
    return render_template("sitemap.html", sections=sections, articles=articles, news=news)


@app.route("/sitemap.xml")
def sitemap_xml():
    base = request.url_root.rstrip("/")
    urls = ["/", "/about", "/news", "/contacts", "/sitemap", "/search", "/register", "/login"]
    urls += ["/razdel/" + s["slug"] for s in query("SELECT slug FROM sections")]
    urls += ["/razdel/%s/%s" % (a["section_slug"], a["slug"]) for a in query(
        "SELECT a.slug, s.slug AS section_slug FROM articles a JOIN sections s ON s.id = a.section_id "
        "WHERE a.is_published = 1")]
    urls += ["/news/" + n["slug"] for n in query("SELECT slug FROM news WHERE is_published = 1")]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += ["<url><loc>%s%s</loc></url>" % (base, u) for u in urls]
    xml.append("</urlset>")
    resp = make_response("\n".join(xml))
    resp.mimetype = "application/xml"
    return resp


@app.route("/robots.txt")
def robots():
    body = ("User-agent: *\nDisallow: /cabinet\nDisallow: /manager\nDisallow: /admin\nDisallow: /dialog\n"
            "Sitemap: %s/sitemap.xml\n" % request.url_root.rstrip("/"))
    resp = make_response(body)
    resp.mimetype = "text/plain"
    return resp


# ---------------------------------------------------------------- вход и регистрация

@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("cabinet"))
    form = {"full_name": "", "login": "", "email": "", "phone": ""}
    errors = []
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        errors = validate_new_user(form, password, password2)
        if not errors:
            uid = execute(
                "INSERT INTO users (login, email, full_name, phone, password_hash, role, created_at) "
                "VALUES (?,?,?,?,?, 'client', ?)",
                (form["login"], form["email"].lower(), form["full_name"], form["phone"],
                 hash_password(password), now_str()))
            session.clear()
            session["uid"] = uid
            flash("Регистрация завершена. Добро пожаловать в личный кабинет!", "ok")
            return redirect(url_for("cabinet"))
    return render_template("register.html", form=form, errors=errors)


def validate_new_user(form, password, password2=None):
    errors = []
    if len(form["full_name"]) < 3 or len(form["full_name"]) > 80:
        errors.append("Укажите имя и фамилию (от 3 до 80 символов).")
    if not LOGIN_RE.match(form["login"]):
        errors.append("Логин: от 3 до 30 символов, только латинские буквы, цифры и знаки _ . -")
    elif query("SELECT 1 FROM users WHERE login = ?", (form["login"],), one=True):
        errors.append("Такой логин уже занят, выберите другой.")
    if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
        errors.append("Укажите адрес электронной почты в формате name@example.ru.")
    elif query("SELECT 1 FROM users WHERE email = ?", (form["email"].lower(),), one=True):
        errors.append("Пользователь с такой почтой уже зарегистрирован.")
    if form.get("phone") and not re.match(r"^[0-9+()\-\s]{5,20}$", form["phone"]):
        errors.append("Телефон: только цифры, пробелы, скобки, плюс и дефис.")
    if password is not None:
        problem = password_problem(password)
        if problem:
            errors.append(problem)
        elif password2 is not None and password != password2:
            errors.append("Пароль и подтверждение не совпадают.")
    return errors


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("cabinet"))
    nxt = safe_next(request.values.get("next"))
    error, ident = None, ""
    if request.method == "POST":
        ident = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        key = "%s|%s" % (ident.lower(), request.remote_addr)
        if too_many_attempts(key):
            error = "Слишком много неудачных попыток. Подождите пять минут и повторите вход."
        else:
            user = query("SELECT * FROM users WHERE login = ? OR email = ?", (ident, ident.lower()), one=True)
            if user and user["is_active"] and verify_password(user["password_hash"], password):
                clear_fails(key)
                session.clear()
                session["uid"] = user["id"]
                flash("Вы вошли как %s." % user["full_name"], "ok")
                if user["must_change"]:
                    return redirect(url_for("password_change"))
                return redirect(nxt or url_for("cabinet"))
            register_fail(key)
            if user and not user["is_active"]:
                error = "Учётная запись отключена администратором."
            else:
                error = "Неверный логин или пароль."
    return render_template("login.html", error=error, ident=ident, nxt=nxt)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из личного кабинета.", "ok")
    return redirect(url_for("index"))


@app.route("/cabinet/password", methods=["GET", "POST"])
@login_required
def password_change():
    errors = []
    if request.method == "POST":
        old = request.form.get("old", "")
        new = request.form.get("new", "")
        new2 = request.form.get("new2", "")
        if not verify_password(g.user["password_hash"], old):
            errors.append("Текущий пароль указан неверно.")
        else:
            problem = password_problem(new)
            if problem:
                errors.append(problem)
            elif new != new2:
                errors.append("Новый пароль и подтверждение не совпадают.")
            elif new == old:
                errors.append("Новый пароль должен отличаться от текущего.")
        if not errors:
            execute("UPDATE users SET password_hash = ?, must_change = 0 WHERE id = ?",
                    (hash_password(new), g.user["id"]))
            flash("Пароль изменён.", "ok")
            return redirect(url_for("cabinet"))
    return render_template("password.html", errors=errors)


# ---------------------------------------------------------------- кабинет клиента

@app.route("/cabinet")
@login_required
def cabinet():
    if g.user["role"] == "manager":
        return redirect(url_for("manager_home"))
    if g.user["role"] == "admin":
        return redirect(url_for("admin_home"))
    requests_ = query("SELECT * FROM requests WHERE client_id = ? ORDER BY id DESC", (g.user["id"],))
    dialogs = query(
        "SELECT d.*, (SELECT COUNT(*) FROM messages m WHERE m.dialog_id = d.id AND m.sender_id != d.client_id "
        "AND m.is_read = 0) AS unread FROM dialogs d WHERE d.client_id = ? ORDER BY d.updated_at DESC",
        (g.user["id"],))
    return render_template("cabinet.html", requests_=requests_, dialogs=dialogs)


@app.route("/cabinet/zayavka", methods=["GET", "POST"])
@roles_required("client")
def request_new():
    form = {"event_type": EVENT_TYPES[0], "event_date": "", "guests": "", "budget": "", "comment": ""}
    errors = []
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if form["event_type"] not in EVENT_TYPES:
            errors.append("Выберите тип мероприятия из списка.")
        try:
            d = datetime.strptime(form["event_date"], "%Y-%m-%d")
            if d.date() < datetime.now().date():
                errors.append("Дата мероприятия не может быть в прошлом.")
        except ValueError:
            errors.append("Укажите дату мероприятия.")
        if not form["guests"].isdigit() or not (1 <= int(form["guests"]) <= 5000):
            errors.append("Количество гостей: целое число от 1 до 5000.")
        if len(form["budget"]) > 60:
            errors.append("Поле «Ориентировочный бюджет» не длиннее 60 символов.")
        if len(form["comment"]) > 1500:
            errors.append("Комментарий не длиннее 1500 символов.")
        if not errors:
            ts = now_str()
            subject = "Заявка: %s, %s" % (form["event_type"], ru_date(form["event_date"]))
            did = execute("INSERT INTO dialogs (client_id, subject, created_at, updated_at) VALUES (?,?,?,?)",
                          (g.user["id"], subject, ts, ts))
            text = "Новая заявка на мероприятие.\nТип: %s\nДата: %s\nГостей: %s\nБюджет: %s\nКомментарий: %s" % (
                form["event_type"], ru_date(form["event_date"]), form["guests"],
                form["budget"] or "не указан", form["comment"] or "нет")
            execute("INSERT INTO messages (dialog_id, sender_id, body, created_at) VALUES (?,?,?,?)",
                    (did, g.user["id"], text, ts))
            execute("INSERT INTO requests (client_id, dialog_id, event_type, event_date, guests, budget, comment, "
                    "created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (g.user["id"], did, form["event_type"], form["event_date"], int(form["guests"]),
                     form["budget"], form["comment"], ts))
            flash("Заявка отправлена. Менеджер ответит в диалоге.", "ok")
            return redirect(url_for("dialog_view", dialog_id=did))
    return render_template("request_new.html", form=form, errors=errors, event_types=EVENT_TYPES,
                           today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/dialogs/new", methods=["GET", "POST"])
@roles_required("client")
def dialog_new():
    form = {"subject": "", "body": ""}
    errors = []
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if len(form["subject"]) < 3 or len(form["subject"]) > 120:
            errors.append("Тема диалога: от 3 до 120 символов.")
        if len(form["body"]) < 2 or len(form["body"]) > 3000:
            errors.append("Сообщение: от 2 до 3000 символов.")
        if not errors:
            ts = now_str()
            did = execute("INSERT INTO dialogs (client_id, subject, created_at, updated_at) VALUES (?,?,?,?)",
                          (g.user["id"], form["subject"], ts, ts))
            execute("INSERT INTO messages (dialog_id, sender_id, body, created_at) VALUES (?,?,?,?)",
                    (did, g.user["id"], form["body"], ts))
            flash("Диалог создан. Менеджер ответит в ближайшее время.", "ok")
            return redirect(url_for("dialog_view", dialog_id=did))
    return render_template("dialog_new.html", form=form, errors=errors)


@app.route("/dialog/<int:dialog_id>", methods=["GET", "POST"])
@login_required
def dialog_view(dialog_id):
    dlg = query("SELECT d.*, u.full_name AS client_name, u.email AS client_email FROM dialogs d "
                "JOIN users u ON u.id = d.client_id WHERE d.id = ?", (dialog_id,), one=True)
    if dlg is None:
        abort(404)
    is_staff = g.user["role"] in ("manager", "admin")
    # Клиент видит только свои диалоги; сотрудники - любые.
    if not is_staff and dlg["client_id"] != g.user["id"]:
        abort(403)
    errors = []
    if request.method == "POST":
        action = request.form.get("action", "send")
        if action == "close" and is_staff:
            execute("UPDATE dialogs SET status = 'closed' WHERE id = ?", (dialog_id,))
            flash("Диалог закрыт.", "ok")
            return redirect(url_for("dialog_view", dialog_id=dialog_id))
        if action == "reopen" and is_staff:
            execute("UPDATE dialogs SET status = 'open' WHERE id = ?", (dialog_id,))
            flash("Диалог снова открыт.", "ok")
            return redirect(url_for("dialog_view", dialog_id=dialog_id))
        body = request.form.get("body", "").strip()
        if dlg["status"] == "closed" and not is_staff:
            errors.append("Диалог закрыт менеджером. Создайте новый диалог.")
        elif len(body) < 1 or len(body) > 3000:
            errors.append("Сообщение: от 1 до 3000 символов.")
        else:
            ts = now_str()
            execute("INSERT INTO messages (dialog_id, sender_id, body, created_at) VALUES (?,?,?,?)",
                    (dialog_id, g.user["id"], body, ts))
            execute("UPDATE dialogs SET updated_at = ? WHERE id = ?", (ts, dialog_id))
            flash("Сообщение отправлено.", "ok")
            return redirect(url_for("dialog_view", dialog_id=dialog_id) + "#end")
    # Помечаем прочитанными сообщения собеседника.
    if is_staff:
        execute("UPDATE messages SET is_read = 1 WHERE dialog_id = ? AND sender_id = ?",
                (dialog_id, dlg["client_id"]))
    else:
        execute("UPDATE messages SET is_read = 1 WHERE dialog_id = ? AND sender_id != ?",
                (dialog_id, dlg["client_id"]))
    msgs = query("SELECT m.*, u.full_name, u.role FROM messages m JOIN users u ON u.id = m.sender_id "
                 "WHERE m.dialog_id = ? ORDER BY m.id", (dialog_id,))
    req = query("SELECT * FROM requests WHERE dialog_id = ?", (dialog_id,), one=True)
    return render_template("dialog.html", dlg=dlg, msgs=msgs, errors=errors, is_staff=is_staff, req=req)


# ---------------------------------------------------------------- кабинет менеджера

@app.route("/manager")
@roles_required("manager", "admin")
def manager_home():
    counts = {
        "dialogs": query("SELECT COUNT(*) c FROM dialogs WHERE status = 'open'", one=True)["c"],
        "new_requests": query("SELECT COUNT(*) c FROM requests WHERE status = 'new'", one=True)["c"],
        "feedback": query("SELECT COUNT(*) c FROM feedback WHERE is_handled = 0", one=True)["c"],
        "clients": query("SELECT COUNT(*) c FROM users WHERE role = 'client'", one=True)["c"],
    }
    return render_template("manager_home.html", counts=counts)


@app.route("/manager/dialogs")
@roles_required("manager", "admin")
def manager_dialogs():
    show = request.args.get("show", "open")
    where = "WHERE d.status = 'open'" if show != "all" else ""
    rows = query(
        "SELECT d.*, u.full_name AS client_name, "
        "(SELECT COUNT(*) FROM messages m WHERE m.dialog_id = d.id AND m.sender_id = d.client_id AND m.is_read = 0) "
        "AS unread, (SELECT body FROM messages m WHERE m.dialog_id = d.id ORDER BY m.id DESC LIMIT 1) AS last_body "
        "FROM dialogs d JOIN users u ON u.id = d.client_id %s ORDER BY unread DESC, d.updated_at DESC" % where)
    return render_template("manager_dialogs.html", rows=rows, show=show)


@app.route("/manager/requests", methods=["GET", "POST"])
@roles_required("manager", "admin")
def manager_requests():
    if request.method == "POST":
        rid = request.form.get("id", "")
        status = request.form.get("status", "")
        if rid.isdigit() and status in STATUS_REQUEST:
            execute("UPDATE requests SET status = ? WHERE id = ?", (status, int(rid)))
            flash("Статус заявки обновлён.", "ok")
        else:
            flash("Не удалось изменить статус заявки.", "error")
        return redirect(url_for("manager_requests"))
    rows = query("SELECT r.*, u.full_name AS client_name FROM requests r JOIN users u ON u.id = r.client_id "
                 "ORDER BY CASE r.status WHEN 'new' THEN 0 WHEN 'work' THEN 1 ELSE 2 END, r.id DESC")
    return render_template("manager_requests.html", rows=rows)


@app.route("/manager/clients", methods=["GET", "POST"])
@roles_required("manager", "admin")
def manager_clients():
    form = {"full_name": "", "login": "", "email": "", "phone": ""}
    errors = []
    created = None
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        password = request.form.get("password", "").strip() or generate_password()
        errors = validate_new_user(form, password)
        if not errors:
            execute(
                "INSERT INTO users (login, email, full_name, phone, password_hash, role, must_change, created_by, "
                "created_at) VALUES (?,?,?,?,?, 'client', 1, ?, ?)",
                (form["login"], form["email"].lower(), form["full_name"], form["phone"],
                 hash_password(password), g.user["id"], now_str()))
            created = {"login": form["login"], "password": password, "full_name": form["full_name"]}
            form = {"full_name": "", "login": "", "email": "", "phone": ""}
    clients = query("SELECT u.*, c.full_name AS creator FROM users u LEFT JOIN users c ON c.id = u.created_by "
                    "WHERE u.role = 'client' ORDER BY u.id DESC")
    return render_template("manager_clients.html", form=form, errors=errors, created=created, clients=clients)


@app.route("/manager/publish", methods=["GET", "POST"])
@roles_required("manager", "admin")
def manager_publish():
    kind = request.values.get("kind", "article")
    if kind not in ("article", "news"):
        kind = "article"
    form = {"section_id": "", "title": "", "summary": "", "body": ""}
    errors = []
    sections = query("SELECT id, title FROM sections ORDER BY position")
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        if len(form["title"]) < 5 or len(form["title"]) > 140:
            errors.append("Заголовок: от 5 до 140 символов.")
        if len(form["summary"]) < 10 or len(form["summary"]) > 300:
            errors.append("Краткое описание: от 10 до 300 символов.")
        if len(form["body"]) < 100 or len(form["body"]) > 12000:
            errors.append("Текст: от 100 до 12000 символов.")
        section_row = None
        if kind == "article":
            if form["section_id"].isdigit():
                section_row = query("SELECT * FROM sections WHERE id = ?", (int(form["section_id"]),), one=True)
            if section_row is None:
                errors.append("Выберите раздел для статьи.")
        if not errors:
            ts = now_str()
            if kind == "article":
                slug = unique_slug("articles", translit(form["title"]))
                execute("INSERT INTO articles (section_id, slug, title, summary, body, author_id, published_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (section_row["id"], slug, form["title"], form["summary"], form["body"], g.user["id"], ts))
                flash("Статья опубликована в разделе «%s»." % section_row["title"], "ok")
                return redirect(url_for("article", slug=section_row["slug"], article_slug=slug))
            slug = unique_slug("news", translit(form["title"]))
            execute("INSERT INTO news (slug, title, summary, body, author_id, published_at) VALUES (?,?,?,?,?,?)",
                    (slug, form["title"], form["summary"], form["body"], g.user["id"], ts))
            flash("Новость опубликована в ленте.", "ok")
            return redirect(url_for("news_item", slug=slug))
    sec_options = [("", "Выберите раздел")] + [(s["id"], s["title"]) for s in sections]
    return render_template("manager_publish.html", kind=kind, form=form, errors=errors, sec_options=sec_options)


@app.route("/manager/content", methods=["GET", "POST"])
@roles_required("manager", "admin")
def manager_content():
    if request.method == "POST":
        table = {"article": "articles", "news": "news"}.get(request.form.get("kind", ""))
        cid = request.form.get("id", "")
        if table and cid.isdigit():
            execute("UPDATE %s SET is_published = 1 - is_published WHERE id = ?" % table, (int(cid),))
            flash("Видимость материала изменена.", "ok")
        return redirect(url_for("manager_content"))
    articles = query("SELECT a.*, s.title AS section_title, s.slug AS section_slug FROM articles a "
                     "JOIN sections s ON s.id = a.section_id ORDER BY a.published_at DESC, a.id DESC")
    news = query("SELECT * FROM news ORDER BY published_at DESC, id DESC")
    return render_template("manager_content.html", articles=articles, news=news)


@app.route("/manager/feedback", methods=["GET", "POST"])
@roles_required("manager", "admin")
def manager_feedback():
    if request.method == "POST":
        fid = request.form.get("id", "")
        if fid.isdigit():
            execute("UPDATE feedback SET is_handled = 1 - is_handled WHERE id = ?", (int(fid),))
        return redirect(url_for("manager_feedback"))
    rows = query("SELECT * FROM feedback ORDER BY is_handled, id DESC")
    return render_template("manager_feedback.html", rows=rows)


# ---------------------------------------------------------------- кабинет администратора

@app.route("/admin")
@roles_required("admin")
def admin_home():
    counts = {
        "users": query("SELECT COUNT(*) c FROM users", one=True)["c"],
        "banners": query("SELECT COUNT(*) c FROM banners WHERE is_active = 1", one=True)["c"],
        "articles": query("SELECT COUNT(*) c FROM articles", one=True)["c"],
        "news": query("SELECT COUNT(*) c FROM news", one=True)["c"],
    }
    by_role = query("SELECT role, COUNT(*) c FROM users GROUP BY role")
    return render_template("admin_home.html", counts=counts, by_role={r["role"]: r["c"] for r in by_role})


@app.route("/admin/users", methods=["GET", "POST"])
@roles_required("admin")
def admin_users():
    form = {"full_name": "", "login": "", "email": "", "phone": "", "role": "manager"}
    errors = []
    created = None
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            form = {k: request.form.get(k, "").strip() for k in form}
            password = request.form.get("password", "").strip() or generate_password()
            errors = validate_new_user(form, password)
            if form["role"] not in ROLE_TITLES:
                errors.append("Выберите роль из списка.")
            if not errors:
                execute(
                    "INSERT INTO users (login, email, full_name, phone, password_hash, role, must_change, "
                    "created_by, created_at) VALUES (?,?,?,?,?,?,1,?,?)",
                    (form["login"], form["email"].lower(), form["full_name"], form["phone"],
                     hash_password(password), form["role"], g.user["id"], now_str()))
                created = {"login": form["login"], "password": password, "full_name": form["full_name"],
                           "role": ROLE_TITLES[form["role"]]}
                form = {"full_name": "", "login": "", "email": "", "phone": "", "role": "manager"}
        else:
            uid = request.form.get("id", "")
            target = query("SELECT * FROM users WHERE id = ?", (int(uid),), one=True) if uid.isdigit() else None
            if target is None:
                flash("Пользователь не найден.", "error")
            elif action == "role":
                new_role = request.form.get("role", "")
                admins = query("SELECT COUNT(*) c FROM users WHERE role = 'admin' AND is_active = 1", one=True)["c"]
                if new_role not in ROLE_TITLES:
                    flash("Неизвестная роль.", "error")
                elif target["role"] == "admin" and new_role != "admin" and admins <= 1:
                    flash("Нельзя снять роль с единственного администратора.", "error")
                else:
                    execute("UPDATE users SET role = ? WHERE id = ?", (new_role, target["id"]))
                    flash("Роль пользователя «%s» изменена: %s." % (target["login"], ROLE_TITLES[new_role]), "ok")
            elif action == "active":
                if target["id"] == g.user["id"]:
                    flash("Нельзя отключить собственную учётную запись.", "error")
                else:
                    execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (target["id"],))
                    flash("Состояние учётной записи «%s» изменено." % target["login"], "ok")
            if not created:
                return redirect(url_for("admin_users"))
    users = query("SELECT u.*, c.full_name AS creator FROM users u LEFT JOIN users c ON c.id = u.created_by "
                  "ORDER BY u.id")
    return render_template("admin_users.html", users=users, form=form, errors=errors, created=created)


@app.route("/admin/banners", methods=["GET", "POST"])
@roles_required("admin")
def admin_banners():
    errors = []
    if request.method == "POST":
        action = request.form.get("action", "")
        data = {k: request.form.get(k, "").strip() for k in ("title", "text", "link_url", "link_text", "art_key")}
        data["position"] = request.form.get("position", "0").strip()
        data["is_active"] = 1 if request.form.get("is_active") else 0
        if not (3 <= len(data["title"]) <= 80):
            errors.append("Заголовок баннера: от 3 до 80 символов.")
        if not (5 <= len(data["text"]) <= 200):
            errors.append("Текст баннера: от 5 до 200 символов.")
        if not (data["link_url"].startswith("/") and not data["link_url"].startswith("//")) and not re.match(
                r"^https?://", data["link_url"]):
            errors.append("Ссылка должна начинаться с «/» (страница сайта) или с http:// либо https://.")
        if not (2 <= len(data["link_text"]) <= 40):
            errors.append("Подпись кнопки: от 2 до 40 символов.")
        if data["art_key"] not in ART_KEYS:
            errors.append("Выберите рисунок из списка.")
        if not re.match(r"^-?\d{1,3}$", data["position"]):
            errors.append("Порядок показа: целое число.")
        if action == "delete":
            bid = request.form.get("id", "")
            if bid.isdigit():
                execute("DELETE FROM banners WHERE id = ?", (int(bid),))
                flash("Баннер удалён.", "ok")
            return redirect(url_for("admin_banners"))
        if not errors:
            args = (data["title"], data["text"], data["link_url"], data["link_text"], data["art_key"],
                    int(data["position"]), data["is_active"])
            if action == "create":
                execute("INSERT INTO banners (title, text, link_url, link_text, art_key, position, is_active) "
                        "VALUES (?,?,?,?,?,?,?)", args)
                flash("Баннер добавлен.", "ok")
            elif action == "update" and request.form.get("id", "").isdigit():
                execute("UPDATE banners SET title=?, text=?, link_url=?, link_text=?, art_key=?, position=?, "
                        "is_active=? WHERE id = ?", args + (int(request.form["id"]),))
                flash("Баннер сохранён.", "ok")
            return redirect(url_for("admin_banners"))
    banners = query("SELECT * FROM banners ORDER BY position, id")
    return render_template("admin_banners.html", banners=banners, errors=errors, art_keys=ART_KEYS)


# ---------------------------------------------------------------- обработчики ошибок

ERROR_TEXT = {
    400: ("Запрос не удалось обработать", "Форма устарела или была отправлена не полностью. Вернитесь назад, обновите страницу и отправьте форму ещё раз."),
    403: ("Доступ запрещён", "У вашей учётной записи нет прав для просмотра этой страницы. Если вы считаете, что это ошибка, обратитесь к администратору."),
    405: ("Метод не поддерживается", "Для этого адреса такое действие не предусмотрено."),
    413: ("Слишком большой запрос", "Отправленные данные превышают допустимый размер."),
    500: ("Внутренняя ошибка сайта", "Что-то пошло не так на нашей стороне. Мы уже знаем о проблеме — попробуйте повторить действие чуть позже."),
}


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


def make_error_handler(code):
    def handler(_e):
        title, text = ERROR_TEXT[code]
        return render_template("error.html", code=code, title=title, text=text), code
    return handler


for _code in ERROR_TEXT:
    app.register_error_handler(_code, make_error_handler(_code))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
