"""Мини-разметка текста статей и безопасная подсветка поиска.

Тело статьи хранится в БД простым текстом:
  пустая строка  - новый абзац;
  '## Заголовок' - подзаголовок;
  '- пункт'      - элемент маркированного списка;
  '> цитата'     - цитата.
Шаблон Jinja получает список блоков и сам экранирует каждый из них,
поэтому фильтр |safe для пользовательского текста не нужен.
"""
import re

from markupsafe import Markup, escape


def parse_body(text):
    blocks = []
    for chunk in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [ln.rstrip() for ln in chunk.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].startswith("## "):
            blocks.append(("h2", lines[0][3:].strip()))
            lines = lines[1:]
            if not lines:
                continue
        if all(ln.startswith("- ") for ln in lines):
            blocks.append(("ul", [ln[2:].strip() for ln in lines]))
        elif lines[0].startswith("> "):
            blocks.append(("quote", " ".join(ln.lstrip("> ").strip() for ln in lines)))
        else:
            blocks.append(("p", " ".join(lines)))
    return blocks


def word_count(text):
    return len(re.findall(r"[\w-]+", re.sub(r"^(## |- |> )", "", text or "", flags=re.M), flags=re.U))


def highlight(text, query, width=90):
    """Возвращает фрагмент текста вокруг первого совпадения с подсветкой <mark>."""
    text = re.sub(r"^(## |- |> )", "", text or "", flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    query = (query or "").strip()
    if not query:
        return Markup(escape(text[: width * 2]))
    pos = text.lower().find(query.lower())
    if pos < 0:
        return Markup(escape(text[: width * 2] + ("..." if len(text) > width * 2 else "")))
    start = max(0, pos - width)
    end = min(len(text), pos + len(query) + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    fragment = text[start:end]
    local = pos - start
    return Markup(
        escape(prefix + fragment[:local])
        + Markup("<mark>") + escape(fragment[local:local + len(query)]) + Markup("</mark>")
        + escape(fragment[local + len(query):] + suffix)
    )
