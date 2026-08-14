# GeeksPro Control

Внутренняя система управления проектами, командами, стажёрами, документами,
рисками и отчётностью GeeksPro. Заменяет управление через Google Sheets:
система сама показывает, какие проекты, задачи, документы, люди и сроки
требуют внимания.

## Технологический стек

- **Backend:** Python 3.11, Django 5.2, PostgreSQL 16
- **Frontend:** Django Templates, HTMX, Alpine.js, собственный CSS
- **Фоновые задачи:** Redis, Celery, Celery Beat
- **Инфраструктура:** Docker, Docker Compose, Gunicorn, Nginx (prod)
- **Архитектура:** Modular Monolith, service layer + selectors

## Структура проекта

```
app/
  core/                # settings (base/dev/prod), urls, celery
  apps/
    accounts/          # пользователи и роли (Head, PM, TL, Intern, Admin)
    common/            # базовые абстрактные модели, seed_demo
    clients/           # клиенты и их контакты
    projects/          # проекты, этапы, история изменений, Kanban
    dashboard/         # KPI-карточки, «Требует внимания», «Сегодня»
  templates/
  static/
docker/                # Dockerfile
scripts/               # entrypoint.sh
```

## Быстрый старт (Docker)

1. Скопируйте `.env` (в репозитории уже есть dev-версия) и при необходимости
   поменяйте порты/пароли:

```env
COMPOSE_PROJECT_NAME=geekspro
WEB_PORT=8090            # порт веб-приложения на хосте
DB_PORT=5436             # порт PostgreSQL на хосте
REDIS_PORT=6391

SECRET_KEY=...           # обязательный
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8090,http://localhost:8090

POSTGRES_DB=geekspro
POSTGRES_USER=geekspro_user
POSTGRES_PASSWORD=...
POSTGRES_HOST=db
POSTGRES_PORT=5432

REDIS_URL=redis://redis:6379/0

# Автосоздание администратора при первом старте
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=admin12345
DJANGO_SUPERUSER_EMAIL=admin@example.com
```

2. Соберите и запустите:

```bash
docker compose up -d --build
```

При старте контейнер `web` сам применяет миграции, собирает статику и
создаёт администратора из env-переменных.

3. Откройте http://127.0.0.1:8090/ и войдите под администратором.

### Демо-данные

```bash
docker compose run --rm web python manage.py seed_demo
```

Создаёт тестовых клиентов и проекты в разных состояниях
(просроченные, в риске, на сдаче, завершённые), чтобы Dashboard был наполнен.
Команда пропускается, если в базе уже есть проекты.

## Полезные команды

```bash
# миграции
docker compose run --rm web python manage.py makemigrations
docker compose run --rm web python manage.py migrate

# создать администратора вручную
docker compose run --rm web python manage.py createsuperuser

# тесты
docker compose run --rm web python manage.py test

# django shell
docker compose run --rm web python manage.py shell
```

## Celery

Worker и beat поднимаются отдельными сервисами compose (`celery`,
`celery-beat`) и используют Redis как брокер. Периодические проверки
(deadline, неактивные проекты, отсутствующие документы, перегруз) будут
регистрироваться в `CELERY_BEAT_SCHEDULE` по мере реализации модулей.

## Backup / Restore

```bash
# бэкап базы
docker compose exec db pg_dump -U geekspro_user geekspro > backup_$(date +%F).sql

# восстановление
cat backup_2026-08-14.sql | docker compose exec -T db psql -U geekspro_user geekspro

# бэкап загруженных файлов
tar -czf media_backup_$(date +%F).tar.gz app/media/
```

## Production

- `docker-compose.prod.yml` + `core.settings.prod` (`DEBUG=False`,
  secure cookies, `SECURE_PROXY_SSL_HEADER` за nginx).
- Gunicorn как app-сервер, nginx терминирует HTTPS и раздаёт static/media.
- `SECRET_KEY`, пароли БД и `ALLOWED_HOSTS` — только через environment.

### Деплой на сервер

```bash
# 1. На сервере (Ubuntu + Docker + nginx):
git clone <repo> /opt/GeeksProControl && cd /opt/GeeksProControl

# 2. Конфигурация
cp .env.prod.example .env
nano .env        # SECRET_KEY, домен, пароли — все CHANGE_ME

# 3. Запуск (миграции и статика применятся автоматически)
docker compose -f docker-compose.prod.yml up -d --build

# 4. nginx + HTTPS
cp docker/nginx.example.conf /etc/nginx/sites-available/geekspro-control
# поправить server_name и пути, затем:
ln -s /etc/nginx/sites-available/geekspro-control /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d control.example.com

# 5. (опционально) демо-данные для теста
docker compose -f docker-compose.prod.yml run --rm web python manage.py seed_demo
```

## Статус разработки

Реализованы этапы 1–7 плана разработки из ТЗ §41 (50 тестов):

- [x] Каркас: Django + PostgreSQL + Docker + Celery, split settings
- [x] Авторизация, кастомный User с ролями (Head/PM/TL/Intern/Admin)
- [x] Клиенты: список, карточка, формы
- [x] Проекты: фильтры, карточка (8 вкладок), Kanban с drag-and-drop,
      автосоздание этапов жизненного цикла, история изменений
- [x] Контроль сроков: автоматический статус, обязательная причина
      при переносе deadline
- [x] Dashboard: KPI-карточки, «Требует внимания», «Сегодня и неделя»
- [x] Задачи: таблица/Kanban/сегодня/неделя/просроченные, комментарии,
      вложения (с валидацией файлов), автоматические чек-листы при создании
      проекта и переходе в Delivery (шаблоны настраиваются в админке)
- [x] Команды: участники проектов (сотрудники и стажёры), загрузка,
      предупреждение о перегрузе >100%, обзор загрузки людей
- [x] Стажёры: карточка, статусы, оценка по 7 критериям (1–5),
      средний рейтинг, занятость, история проектов
- [x] Документы: типы (справочник), статусы, контроль комплекта «4/6»,
      warning при сдаче без обязательных документов
- [x] Delivery workflow: чек-лист условий (техника/документы/клиент),
      кнопка «Завершить проект» с конкретными причинами отказа,
      принудительное завершение с причиной, освобождение команды
- [x] Собрания: типы, авто-повестка из проблемных пунктов,
      решения → кнопка «Создать задачу»
- [x] Уведомления: Notification Center, счётчик в навигации, дедупликация
- [x] Риски: категории, справочник причин задержек
- [x] Audit log: глобальный журнал ключевых действий
- [x] Автоматические проверки (Celery Beat, ежедневно 07:00): deadline,
      неактивные проекты, документы, перегруз, отсутствие PM/TL
- [x] Учебные группы и выпуски по месяцам
- [x] Resource Planning: баланс Доступно/Выпуск/Нужно по направлениям,
      планируемые проекты (planning pipeline) с составом команды
- [x] Отчёты: недельный отчёт со сравнением с прошлой неделей,
      KPI руководителя + snapshots (еженедельно/ежемесячно по Celery)
- [x] seed_demo, 50 тестов, страницы 403/404/500

Дальше по плану (§40 P1–P2): Project Health Score, прогноз даты завершения,
календарь, PDF-экспорт отчётов, импорт Excel/CSV, генерация документов,
глобальный поиск (Ctrl+K), графики аналитики, dark mode.
