# Справочник МЧС на FastAPI + Jinja2

Готовый MVP сайта-справочника: документы, инструкции, видео, приказы, ссылки, статьи, поиск, категории, теги, роли и простая админ-панель.

## Функции

- Публичная главная страница.
- Каталог материалов.
- Поиск по названию, описанию, тексту и номеру документа.
- Фильтры по категории, типу материала и тегу.
- Страница материала с файлами, ссылками и видео.
- Авторизация через cookie-session.
- Роли: `admin`, `moderator`, `editor`, `staff`.
- Админка для материалов, категорий, отделов и пользователей.
- Загрузка файлов.
- Публичные и внутренние материалы.
- Статусы: черновик, на проверке, опубликовано, архив.
- Простая версионность при редактировании материала.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

Открыть:

```text
http://127.0.0.1:8000
```

Админка:

```text
http://127.0.0.1:8000/admin
```

Данные по умолчанию:

```text
Email: admin@mchs.local
Password: admin12345
```

Пароль можно поменять через переменные окружения перед `init_db.py`:

```bash
export ADMIN_EMAIL="admin@example.com"
export ADMIN_PASSWORD="strong-password"
python scripts/init_db.py
```

## PostgreSQL

Для PostgreSQL укажи `DATABASE_URL`:

```bash
export DATABASE_URL="postgresql+psycopg2://user:password@localhost:5432/mchs_directory"
```

И добавь драйвер:

```bash
pip install psycopg2-binary
```

После этого:

```bash
python scripts/init_db.py
uvicorn app.main:app --reload
```

## Структура

```text
app/
  main.py
  config.py
  database.py
  models.py
  security.py
  utils.py
  routers/
    public.py
    auth.py
    admin.py
templates/
  base.html
  home.html
  materials/
  categories/
  admin/
static/
  css/styles.css
scripts/
  init_db.py
uploads/
```

## Что улучшить для production

- Подключить Alembic для миграций.
- Сделать полноценный PostgreSQL full-text search.
- Добавить извлечение текста из PDF/DOCX для поиска внутри файлов.
- Добавить аудит действий пользователей.
- Добавить удаление/замену отдельных файлов в админке.
- Подключить S3/MinIO для хранения файлов.
- Настроить Nginx + Gunicorn/Uvicorn workers + SSL.
- Включить `https_only=True` в `SessionMiddleware` после настройки HTTPS.
