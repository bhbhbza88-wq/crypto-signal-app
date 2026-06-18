# Crypto Signal App

Веб-версия твоего Telegram-бота: та же торговая логика (детекторы, score 0-20, MTF-фильтры,
trailing stop), но вместо постов в Telegram — собственный интерфейс с активным сигналом,
историей сделок, статистикой и графиком.

## Структура

```
backend/    FastAPI + торговая логика + SQLite + фоновый сканер (раз в 5 мин)
frontend/   React-интерфейс (Vite)
```

## Запуск (всё локально, два терминала)

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

При первом запуске сразу начнётся сканирование рынка (как в боте) — в консоли будут логи
`🔍 Ищем сигнал...`. Открытые сделки и история пишутся в файл `backend/trading_app.db`
(SQLite, создаётся автоматически).

Проверить, что backend работает: открой http://localhost:8000/api/stats — должен вернуться JSON.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Открой http://localhost:3000 — увидишь интерфейс. Он опрашивает backend каждые 15 секунд.

## Настройки (переменные окружения для backend)

Те же, что были в боте — задаются перед запуском или в `.env`:

```bash
export DEPOSIT=1000
export RISK_PCT=1.5
export SCORE_MIN=15
```

## Что перенесено как есть

- Все детекторы (`pullback`, `structure`, `trend_strength`, `volume_climax`, `ema_cross_fresh`)
- Скоринг 0-20, фильтры MTF (4h/1h/30m), BTC-фильтр
- Расчёт уровней TP1/TP2/TP3/SL, trailing stop, фиксация 50% на TP1
- `check_trades()` — теперь пишет события в БД вместо Telegram

## Дизайн интерфейса

Светлая, спокойная тема в духе Apple/Notion. Навигация по трём вкладкам:

- **Обзор** — статистика с переключателем периода (сегодня / неделя / всё время),
  кольцевой индикатор винрейта, активный сигнал с графиком, причиной входа текстом
  и рекомендованным размером позиции
- **Рынок** — режим BTC (определяет, какие сигналы сканер пропускает) и heatmap всех
  32 отслеживаемых монет по текущему режиму (аптренд/даунтренд/флэт)
- **История** — таблица закрытых сделок (карточки на мобильном)

## Что изменилось

- Telegram-код удалён полностью (`requests` к Telegram API, `send_message`, токены)
- `matplotlib`/`mplfinance` графики заменены на интерактивный график на фронтенде (recharts) —
  данные свечей отдаются как JSON через `/api/signals`
- JSON-файлы (`open_trades.json`, `trades_history.json`) заменены на SQLite

## Публикация через Cloudflare Tunnel (доступ для всех, без сервера)

Это временное решение: сайт доступен всем в интернете, но работает только пока твой
компьютер включён и backend/frontend запущены. Бесплатно, без регистрации карты.

### 1. Установи cloudflared

Скачай с https://github.com/cloudflare/cloudflared/releases — для Windows нужен файл
`cloudflared-windows-amd64.exe`. Переименуй в `cloudflared.exe` и положи, например, в
`C:\cloudflared\`.

### 2. Запусти backend и frontend как обычно (два терминала)

```powershell
cd backend
uvicorn main:app --reload --port 8000
```
```powershell
cd frontend
npm run dev
```

### 3. Открой туннель для фронтенда (третий терминал)

```powershell
cd C:\cloudflared
.\cloudflared.exe tunnel --url http://localhost:3000
```

В выводе появится строка вида `https://random-words-1234.trycloudflare.com` — это
публичная ссылка на сайт, можно отправлять кому угодно.

### 4. Открой туннель для backend (четвёртый терминал)

```powershell
cd C:\cloudflared
.\cloudflared.exe tunnel --url http://localhost:8000
```

Появится вторая ссылка, например `https://other-words-5678.trycloudflare.com` — это
адрес backend.

### 5. Скажи фронтенду, где искать backend

Создай файл `frontend/.env` с содержимым (подставь свою ссылку из шага 4, без слэша на конце):

```
VITE_API_URL=https://other-words-5678.trycloudflare.com
```

Перезапусти `npm run dev` (Ctrl+C и заново), чтобы переменная подхватилась.

**Важно:** при каждом перезапуске `cloudflared` (бесплатный Quick Tunnel) ссылки меняются.
Если перезапускал туннели — обнови `.env` с новой ссылкой backend и перезапусти фронтенд.

### Когда будешь готов к постоянному адресу

Понадобится: VPS (Railway, Render, DigitalOcean) для размещения кода 24/7 и домен
(Namecheap, Reg.ru, ~$10/год). Архитектура проекта (FastAPI + SQLite + React) переносится
на сервер почти без изменений.
