# Crypto Alpha AI Advisor - Docker Deployment

Полноценная система анализа крипторынка с AI и Telegram ботом.

## 🚀 Быстрый старт

### 1. Клонирование и настройка
```bash
git clone <repository>
cd crypto-alpha-ai

# Копируем и настраиваем переменные окружения
cp .env.example .env
nano .env  # Добавьте свои API ключи
```

### 2. Запуск системы
```bash
# Полный запуск всех сервисов
docker-compose up -d

# Или с логами для отладки
docker-compose up
```

### 3. Проверка работы
```bash
# Посмотреть статус контейнеров
docker-compose ps

# Посмотреть логи
docker-compose logs -f worker
docker-compose logs -f beat

# Автоматическая проверка развертывания
docker-compose run --rm deployment_check
```

## 🏗️ Архитектура

### Сервисы:
- **postgres** - TimescaleDB база данных
- **redis** - Брокер сообщений для Celery
- **worker** - Celery worker для фоновых задач
- **beat** - Celery beat для периодических задач
- **db_init** - Инициализация базы данных
- **web** - Основное приложение (CLI)

### Переменные окружения (.env):
```env
# База данных
DB_HOST=postgres
DB_USER=crypto
DB_PASS=crypto_pass

# API ключи
DEEPSEEK_API_KEY=sk-your-key
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Опционально
CRYPTOPANIC_API_KEY=your-news-key
```

## 📊 Использование

### Ручное управление:
```bash
# Войти в контейнер
docker-compose exec web bash

# Команды CLI
python run.py init-db          # Инициализация БД
python run.py collect --limit 10  # Сбор данных
python run.py analyze          # AI анализ
python run.py send             # Отправка сигналов
python run.py full-cycle       # Полный цикл
```

### Автоматический режим:
- **Сбор данных**: каждые 30 минут
- **Полный анализ**: каждый час
- **Отправка сигналов**: автоматически после анализа

## 🔧 Управление

### Остановка:
```bash
docker-compose down
```

### Перезапуск сервисов:
```bash
docker-compose restart worker beat
```

### Очистка данных:
```bash
docker-compose down -v  # Удалить volumes
```

### Мониторинг:
```bash
# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f worker

# Статистика Redis
docker-compose exec redis redis-cli info
```

## 🐛 Отладка

### Проблемы с базой данных:
```bash
# Проверить подключение
docker-compose exec postgres pg_isready -U crypto

# Войти в базу
docker-compose exec postgres psql -U crypto -d crypto_alpha
```

### Проблемы с Celery:
```bash
# Проверить Redis
docker-compose exec redis redis-cli ping

# Проверить очереди
docker-compose exec redis redis-cli KEYS "*"
```

### Проблемы с API:
```bash
# Проверить логи worker
docker-compose logs worker | grep -i error

# Тестовый запуск задач
docker-compose exec worker celery -A scheduler.tasks call scheduler.tasks.collect_data_task
```

## 📈 Масштабирование

### Увеличение производительности:
```yaml
# В docker-compose.yml
services:
  worker:
    command: celery -A scheduler.tasks worker --loglevel=info --concurrency=4
    deploy:
      replicas: 2
```

### Настройка периодичности:
```python
# В scheduler/tasks.py
sender.add_periodic_task(900.0, collect_data_task.s(), name='collect-data')  # 15 мин
sender.add_periodic_task(1800.0, full_cycle_task.s(), name='full-cycle')   # 30 мин
```

## 🔒 Безопасность

- Все секреты в `.env` файле
- Контейнеры запускаются от непривилегированного пользователя
- База данных доступна только внутри Docker сети
- API ключи не логируются

## 📝 Логи

Логи сохраняются в:
- `/var/log/postgresql/` - логи базы данных
- Контейнеры Celery логируют в stdout/stderr
- Приложение логирует через Python logging

## 🚨 Мониторинг

### Проверка здоровья:
```bash
# Статус всех сервисов
docker-compose ps

# Использование ресурсов
docker stats

# Проверка API
curl -f http://localhost:8000/health || echo "Service unhealthy"
```

### Метрики:
- Количество обработанных сигналов
- Время выполнения задач
- Ошибки API
- Статус Telegram бота