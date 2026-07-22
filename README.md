# NOWICKI — крипто-сигналы (честная платформа, без обещаний «иксов»)

FastAPI + Python backend, React + Vite frontend, SQLite, Bybit через ccxt, деплой на Railway,
автодеплой при пуше в `main`. GitHub: `bhbhbza88-wq/crypto-signal-app`.

**Прод:**
- Backend: https://crypto-signal-app-production-f37c.up.railway.app
- Frontend: https://nowicki.trade (custom domain → Railway `terrific-expression-production.up.railway.app`)

## Идея проекта

Большинство крипто-сигнальных сервисов врут: рисуют ROI 500%, показывают только
выигрышные сделки, обещают гарантированную прибыль. NOWICKI устроен наоборот —
**реальные данные с Bybit, честные бэктесты, живой дальран, никаких нарисованных цифр**.
Это ключевой принцип проекта: если результат не проверен на живых данных — мы прямо
так и пишем, а не приукрашиваем.

## Архитектура

```
backend/    FastAPI + торговая логика + SQLite + фоновый сканер (раз в 2 мин)
frontend/   React (Vite) — дашборд + публичный лендинг
```

### Backend (`backend/`)

| Файл | Что делает |
|---|---|
| `main.py` | FastAPI-приложение: все `/api/*` роуты, аутентификация, бэктест-движок, эндпоинты проверки на прочность |
| `auth.py` | Своя аутентификация — pbkdf2 (hashlib) для паролей, сессионные токены в БД. Без внешних auth-библиотек. `effective_tier()` — платный тариф всегда побеждает, иначе активный триал даёт premium |
| `database.py` | SQLite: `open_trades`, `history`, `events`, `users`, `sessions`, `xsec_state`, `xsec_log`, `trend_state` |
| `data_layer.py` | OHLCV с Bybit (ccxt), кэш, технические индикаторы (EMA/RSI/ADX/ATR), детектор режима, фоновый снапшот обзора рынка для Скринера (39 пар) |
| `nfi_strategy.py` | Основная стратегия сканера (V8/V9): детекторы входа, скоринг 0-20, расчёт TP1/TP2/TP3/SL, momentum-режим (`STRATEGY_MODE=momentum`) |
| `scanner.py` | Фоновый поток: скан каждые 2 минуты, cooldown, дневной лимит убытка, тики xsec/trend-стратегий, прогрев снапшота Скринера |
| `tracker.py` | Отслеживание открытых позиций: TP1/TP2/TP3, перевод в безубыток, trailing stop (Chandelier Exit) |
| `xsec_strategy.py` | Cross-sectional momentum long-short — market-neutral, ребаланс раз в неделю. **Единственная стратегия с validated edge** на 5-летней истории |
| `trend_strategy.py` | Trend-Following (EMA50/200 long/cash) — хедж от просадок, не источник альфы. Плюс информационный индикатор фазы рынка (не торгует) |
| `robustness.py` | «Проверка на прочность» — walk-forward, стресс по комиссиям, jitter параметров, Monte-Carlo, Deflated Sharpe Ratio. Честный вердикт: устойчив / хрупкий / похож на артефакт |
| `telegram_bot.py` | Уведомления о новых сигналах в Telegram (токен только через env `TELEGRAM_BOT_TOKEN`) |

### Frontend (`frontend/src/`)

| Файл | Что делает |
|---|---|
| `App.jsx` | Дашборд-шелл: сайдбар (Главное/Стратегии/Инструменты/Аккаунт), роутинг вкладок, ErrorBoundary, восстановление сессии |
| `Landing.jsx` | Публичный лендинг — hero, живой скринер-виджет, реальная статистика, тарифы, честность как УТП |
| `AuthModal.jsx` | Вход/регистрация (email+пароль, Google), сброс пароля |
| `AuthPages.jsx` | Страницы подтверждения email и нового пароля |
| `SignalCard.jsx` | Карточка активного сигнала — настоящий свечной график (lightweight-charts, движок TradingView) с price-lines Entry/SL/TP1/TP2/TP3 |
| `MarketView.jsx` | Скринер — тепловая карта 39 пар по режиму и ADX |
| `Backtest.jsx` | Бэктест (одна пара / все пары) + панель «Проверка на прочность» (Premium) |
| `HistoryTable.jsx` | История сделок — free видит только винрейт, полная история (PnL-график, таблица) за Premium |
| `AIChat.jsx` | AI-ассистент «Ник» — крипто-наставник с характером, контекст строится на бэкенде из реальных данных |
| `DryRunDashboard.jsx`, `XSecDashboard.jsx`, `TrendDashboard.jsx`, `StrategiesCompare.jsx` | Дашборды трёх paper-стратегий (все — Premium) |
| `Pricing.jsx` | Тарифы free/premium/vip, недостроенные фичи помечены «СКОРО» |
| `SmartTrade.jsx` | Калькулятор позиции (риск, размер, R:R) |
| `WinrateRing.jsx`, `StatsHero.jsx` | Переиспользуемые виджеты статистики |

## Три независимые paper-стратегии

Торгуют параллельно на бумаге (реальные цены Bybit, виртуальный депозит):

1. **Momentum** (сканер) — высокочастотная, входит на переходе ADX+EMA в тренд, выход по TP/SL/таймауту. **Backtest PF не заслуживает доверия** — менялся на 30-60% от сдвига таймаута на одну свечу. Единственный настоящий арбитр — дальран.
2. **Long-Short (xsec)** — market-neutral, ребаланс раз в неделю, лонг топ-3/шорт боттом-3 из 30 монет по 30-дневному моментуму. **Единственная стратегия с честно подтверждённым edge** (после того как первая проверка Sharpe 1.3 оказалась артефактом дневной ребалансировки — честная версия даёт Sharpe ~0.38-0.43).
3. **Trend-Following** — EMA50/200 long/cash, редкие сделки, позиционируется как хедж от просадок, не альфа.

Плюс информационный индикатор фазы рынка (BTC UPTREND/DOWNTREND/SIDEWAYS) — **не управляет капиталом ни в одной стратегии** (авто-переключение протестировано и отклонено).

## Методология (строго соблюдается)

- Любой бэктест-результат — артефакт, пока не пройдёт walk-forward, sweep параметров, проверку по годам и устойчивость к малым изменениям параметров.
- Во время дальрана **не тюним** параметры/фильтры/монеты — доверяем только живым результатам.
- «Проверка на прочность» (`robustness.py`) — автоматизация этой методологии: walk-forward по 4 окнам, стресс комиссий x1.5/x2, jitter таймаута/трейлинга (9 комбинаций), Monte-Carlo bootstrap (1000 симуляций), Deflated Sharpe Ratio (поправка на подбор параметров, формула Bailey & López de Prado 2014). Честные вердикты: `robust` / `fragile` / `artifact` / `insufficient`.
- Никогда не рисуем цифры — если данных мало, вердикт так и говорит «мало данных», а не натянутый «passed».

## Монетизация

- Тарифы **free / premium / vip**, 3-дневный Premium-триал при регистрации.
- За Premium: **каналы ТВХ + чат в Telegram** (invite после оплаты), полная история на сайте, AI 50/день.
- Публичный канал **результатов** (закрытые сделки) — без оплаты, ссылка с сайта.
- Оплата: USDT TRC20 через бота → пользователь жмёт «Я оплатил» + email → админ `/grant email` → tier + invite-ссылки.
- `/api/billing/upgrade` — stub для админа/тестов; основной путь — Telegram `/grant`.

## Telegram-каналы (чеклист)

**Роли**

| Что | Кто видит | Env |
|-----|-----------|-----|
| Каналы ТВХ (входы) | Premium | `TELEGRAM_PREMIUM_CHANNEL_IDS` (CSV), fallback `TELEGRAM_CHAT_ID` |
| Чат обсуждения | Premium (invite) | `TELEGRAM_PREMIUM_CHAT_ID` |
| Канал результатов (закрытия) | Все | `@papayaqq` — `TELEGRAM_PUBLIC_CHANNEL_ID` (default `@papayaqq`) + `TELEGRAM_PUBLIC_CHANNEL_URL` |
| Админы бота (`/grant`) | — | `TELEGRAM_ADMIN_IDS` (CSV numeric user id) |

**Настройка в Telegram**

1. Публичный канал результатов: **[@papayaqq](https://t.me/papayaqq)** — добавь бота админом (post messages). Default в коде: `@papayaqq`.
2. Сделай каналы ТВХ и чат **private**, бот — админ с правом **invite users** + post.
3. Узнай numeric `chat_id` premium-каналов/чата → `TELEGRAM_PREMIUM_CHANNEL_IDS`, `TELEGRAM_PREMIUM_CHAT_ID`.
4. Свой Telegram user id → `TELEGRAM_ADMIN_IDS`.
5. Сайт ведёт на `https://t.me/papayaqq` (`TG_RESULTS_CHANNEL` в `shared.jsx`).

**Команды бота:** `/premium`, `/paid` (email), `/grant email@…` (только админ).

## AI-ассистент

Персона Nick — desk analyst NOWICKI. Модель по умолчанию `gpt-4o` (`AI_MODEL`).
Контекст: цены, скринер, открытые сетапы с R:R/reasons, статистика, последние закрытия.

## API (основные эндпоинты)

```
POST /api/auth/register, /api/auth/login, /api/auth/logout   — аутентификация
GET  /api/auth/me                                             — текущий пользователь
POST /api/billing/upgrade                                     — смена тарифа (заглушка оплаты)
POST /api/ai/chat                                              — AI-ассистент
GET  /api/signals                                              — активные сигналы сканера
GET  /api/stats                                                — статистика (сегодня/неделя/всё время)
GET  /api/strategies/summary                                  — сводка по 3 стратегиям
GET  /api/history, /api/events                                 — история сделок, лог событий
GET  /api/dryrun/status, /api/dryrun/open, /api/dryrun/breakdown  — дальран momentum
GET  /api/xsec/status, /api/xsec/history, /api/xsec/ranking    — Long-Short стратегия
GET  /api/trend/status, /api/trend/history                     — Trend-Following
GET  /api/market, /api/market/phase                             — цены, скринер, фаза рынка
POST /api/backtest, /api/backtest/multi                         — бэктест (одна пара / все пары)
POST /api/backtest/robustness, GET /api/backtest/robustness/{job_id} — проверка на прочность (Premium)
```

## Auth: Google + email

Вход через **Google** и регистрация email+пароль с письмами (verify / reset).

**Важно:** Railway блокирует исходящий SMTP (`Network is unreachable`). Письма шлём по **HTTPS** через [Resend](https://resend.com) (предпочтительно) или Gmail API.

### Railway / env (backend)

| Переменная | Зачем |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth Client ID (веб) — кнопка «Войти через Google» |
| `RESEND_API_KEY` | API key из resend.com |
| `RESEND_DOMAIN_VERIFIED` | `1` после успешной верификации `send.nowicki.trade` |
| `EMAIL_FROM` | например `NOWICKI <noreply@send.nowicki.trade>` |
| `FRONTEND_URL` | `https://nowicki.trade` — ссылки в письмах |
| `REQUIRE_EMAIL_VERIFY` | `1` (по умолчанию) |
| `GOOGLE_CLIENT_SECRET` + `GOOGLE_REFRESH_TOKEN` | опционально: Gmail API вместо Resend |
| `SMTP_*` | fallback; на Railway обычно не работает |

### Resend (рекомендуется)

1. Domains → Add `send.nowicki.trade`  
2. В DNS Namecheap (домен `nowicki.trade`) добавь записи из Resend (DKIM + MX/SPF на `send.send`)  
3. Verify domain → `RESEND_DOMAIN_VERIFIED=1`, `EMAIL_FROM=NOWICKI <noreply@send.nowicki.trade>`  
4. `RESEND_API_KEY` на Railway  

Без verified-домена Resend шлёт только на email владельца аккаунта Resend.

### Аватар отправителя (фото в инбоксе)

API **не умеет** задать аватар Gmail/Resend программно — его рисует почтовый клиент по адресу From.

**Если письма идут с Gmail** (`GOOGLE_*` / SMTP от `bhbhbza.88@gmail.com` и т.п.):

1. Войди в этот Google-аккаунт → [myaccount.google.com/personal-info](https://myaccount.google.com/personal-info)  
2. «Фото профиля» → загрузи логотип NOWICKI (квадрат, без текста мельче лого)  
3. В Gmail у получателей аватар подтянется с Google-профиля отправителя (не у всех клиентов сразу)

**Если письма идут через Resend** (`noreply@send.nowicki.trade`):

- В Gmail/Outlook аватар часто пустой или буква «N» — Resend **не передаёт** фото профиля  
- Практичные варианты:  
  1. Зарегистрируй email From на [gravatar.com](https://gravatar.com) с тем же адресом и загрузи лого (многие клиенты смотрят Gravatar)  
  2. Позже BIMI ( Domains → BIMI у Resend + SVG-лого + DMARC p=quarantine/reject) — поддерживают не все инбоксы  
- В самих письмах логотип уже встроен картинками: `https://nowicki.trade/email/logo.png` и `…/banner.png`

### Lifecycle-письма

После verify уходит welcome; free-пользователям спустя ~24ч — одно pricing-nudge (сводка публичных результатов канала + CTA на тарифы). Reply-To по умолчанию: `bhbhbza.88@gmail.com` (`EMAIL_REPLY_TO` / `SUPPORT_EMAIL`).

### Google Cloud Console (логин)

1. Credentials → OAuth client → Web application  
2. Authorized JavaScript origins: `https://nowicki.trade`, `http://localhost:5173`  
3. Client ID → `GOOGLE_CLIENT_ID`  

Эндпоинты: `POST /api/auth/google`, `/api/auth/verify-email`, `/api/auth/forgot-password`, `/api/auth/reset-password`, `GET /api/auth/config`.

## Локальный запуск

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

На Windows нужен `PYTHONIOENCODING=utf-8` в окружении — иначе падает на эмодзи в консольных логах
(`cp1250` кодек по умолчанию). Обязательные env-переменные для полного функционала:
`OPENAI_API_KEY` (AI-ассистент), `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_PREMIUM_CHANNEL_IDS` / `TELEGRAM_CHAT_ID`, `TELEGRAM_PUBLIC_CHANNEL_ID`,
`TELEGRAM_ADMIN_IDS` (опционально для уведомлений).

При старте сразу запускается фоновый сканер. Проверить: http://localhost:8000/api/stats.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Открой http://localhost:5173. Для указания другого backend — `frontend/.env` с
`VITE_API_URL=http://адрес-backend` (без слэша на конце).

### Аналитика (Яндекс Метрика)

Для RU/PL аудитории подключена **Яндекс Метрика** (SPA pageviews + цели).

1. Создай счётчик на https://metrika.yandex.ru/ → «Добавить счётчик» → сайт `nowicki.trade`.
2. Скопируй **номер счётчика** (только цифры).
3. Добавь переменную окружения на **frontend** (Railway Variables, build-time):
   `VITE_METRIKA_ID=<номер>`
4. Пересобери/задеплой frontend (Vite вшивает ID при `npm run build`).
5. Локально: `frontend/.env` → `VITE_METRIKA_ID=...` (см. `.env.example`).

Дашборд: https://metrika.yandex.ru/ — посетители, источники, вебвизор.
Цели в коде (создай одноимённые в Метрике → Цели → JavaScript-событие):  
`pricing_click`, `telegram_bot_click`, `login`, `register`.

Пока `VITE_METRIKA_ID` не задан — трекинг тихо отключён (без ошибок).

### Ошибки (Sentry)

Ловим прод-баги на backend (FastAPI) и frontend (React).

1. Создай проект(ы) на https://sentry.io (можно один DSN на оба сервиса или два отдельных).
2. Backend (Railway `crypto-signal-app`):
   - `SENTRY_DSN=...`
   - опционально `SENTRY_ENVIRONMENT=production`, `SENTRY_TRACES_SAMPLE_RATE=0.1`
3. Frontend (Railway `terrific-expression`, build-time):
   - `VITE_SENTRY_DSN=...`
   - опционально `VITE_SENTRY_ENVIRONMENT=production`
4. Пересобери frontend после добавления `VITE_*`.

Пока DSN не задан — Sentry не инициализируется.

### Telegram ingest (больше сигналов, осторожно)

Лимиты отбора сигналов из источников — через env (backend). **Рекомендуемые значения на Railway** (чуть мягче дефолтов):

| Переменная | Рекомендация | Дефолт в коде |
|---|---|---|
| `INGEST_MIN_QUALITY_SCORE` | `54` | `58` |
| `INGEST_MAX_PER_CHANNEL_DAY` | `6` | `4` |
| `INGEST_AGG_MAX_OPEN` | `12` | `8` |
| `INGEST_MAX_ENTRY_SLIP_PCT` | `3.0` (проценты; внутри → `0.03`) | `2.5` |

Также проверь:
- `TELEGRAM_SOURCE_CHANNELS` — список каналов-источников
- AI-ключи (`OPENAI_API_KEY` / OpenRouter и т.п.) — без них extract/vision не работают
- `INGEST_VISION=1` — **только если готов платить за vision-токены** (скриншоты/баннеры); по умолчанию выключено

Админка → вкладка **Ingest** показывает снимок `/api/ingest/health` (day_count, last_signal, open_aggregated, ошибки каналов).

## Стиль работы с проектом (для будущих сессий)

- Отвечать по-русски, прямо, без воды.
- Перед крупными развилками (что гейтить, визуальные решения, поведение фичей) — спрашивать выбор, не решать единолично.
- После фронтенд-правок — обязательно проверять в браузере (билд + визуально), не просто «должно работать».
- Никогда не добавлять фейковые/красивые, но неправдивые цифры — только реальные данные с бэкенда, даже если выглядит скромнее.
- Коммитить с подробным сообщением, объясняющим «почему», пушить в `main` напрямую (так договорились работать). `gh` CLI недоступен — PR только через ручную ссылку `github.com/.../pull/new/<branch>`.
