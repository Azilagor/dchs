# Справочник МЧС на FastAPI + Jinja2

MVP информационно-справочной системы: документы, инструкции, приказы, видео, ссылки, теги, категории, поиск и простая админ-панель.

## Что уже есть

- публичная главная страница и каталог материалов
- поиск по названию, описанию, тексту, тегам, категориям, файлам и ссылкам
- живой поиск с подсказками
- индексация содержимого PDF/DOCX/TXT для поиска
- роли `admin`, `moderator`, `editor`, `staff`
- загрузка файлов
- админка для материалов, категорий, отделов и пользователей
- пагинация в списках материалов

## Быстрый запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

Открыть:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/admin
```

Дефолтный админ:

```text
Email: admin@mchs.local
Password: admin12345
```

## Поиск по PDF/DOCX

После загрузки новых файлов их текст индексируется автоматически.

Чтобы переиндексировать уже существующие материалы и вложения:

```bash
python scripts/reindex_search.py
```

Для извлечения текста используются зависимости:

- `pypdf`
- `python-docx`

Формат `.doc` не индексируется полноценно без внешних конвертеров.

## PostgreSQL для production

Для production рекомендуется PostgreSQL.

Пример `DATABASE_URL`:

```text
postgresql+psycopg2://mchs_user:strong-password@localhost:5432/mchs_directory
```

Пример запуска с PostgreSQL:

```bash
set DATABASE_URL=postgresql+psycopg2://mchs_user:strong-password@localhost:5432/mchs_directory
python scripts/init_db.py
python scripts/reindex_search.py
uvicorn app.main:app --reload
```

Или через `.env` / настройки окружения.

## Полезные переменные окружения

- `DATABASE_URL` — SQLite или PostgreSQL
- `SECRET_KEY` — секрет для session middleware
- `ADMIN_EMAIL` — email дефолтного администратора
- `ADMIN_PASSWORD` — пароль дефолтного администратора
- `TINYMCE_API_KEY` — ключ TinyMCE, если позже снова включите редактор
- `MAX_UPLOAD_SIZE_MB` — лимит размера одного файла
- `PAGE_SIZE` — размер страницы публичного каталога
- `ADMIN_PAGE_SIZE` — размер страницы в админке
- `ALLOWED_UPLOAD_EXTENSIONS` — разрешенные расширения загрузок

## Production notes

- лучше вынести БД на PostgreSQL
- добавить Alembic для миграций
- включить HTTPS и `https_only=True`
- добавить резервное копирование БД и uploads
- при большом объеме файлов вынести хранение в S3/MinIO
