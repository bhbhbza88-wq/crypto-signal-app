"""
Channel Backtester — офлайн-анализ исторической эффективности Telegram-каналов
с крипто-сигналами. Отдельный процесс, никак не завязан на live-бота
(telegram_ingest.py) и не встроен в main.py/lifespan — запускается вручную и
не создаёт постоянной нагрузки на прод:

    cd backend
    python channel_backtest.py binancekillers --days 30

Использует ту же Telegram-сессию (TELEGRAM_API_ID/HASH/SESSION) и тот же
OpenAI-экстрактор (telegram_ingest._extract_signal — один промпт, не дублируем
логику парсинга), но пишет только в свою таблицу historical_signals — не
трогает open_trades/history, поэтому бэктест не может задеть live-сделки.

Важно: TP2/TP3, которые telegram_ingest.py достраивает от TP1 для реальной
торговли (наша trailing-механика), здесь не участвуют — бэктест меряет
эффективность именно того, что канал реально написал (Entry/Stop/TP1), а не
нашу собственную надстройку.
"""

import argparse
import asyncio
import re
from datetime import datetime, timedelta, timezone

import database as db
from data_layer import exchange, api_call
from telegram_ingest import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION,
    _extract_signal, normalize_symbol,
)

COMMISSION_PCT = 0.1          # 0.1% за сторону (вход + выход = 0.2% с сделки)
ENTRY_TIMEOUT_HOURS = 6       # если цена не дошла до Entry за это время — сигнал не в винрейте
MAX_HOLD_HOURS = 168          # 7 дней — если за это время ни TP1 ни Stop не достигнуты,
                               # позиция принудительно закрывается по цене (не "зависает" вечно)
RISK_PER_TRADE_USD = 100.0    # $ риска на сигнал — размер позиции считается от этого, не от фикс. объёма
EXTRACT_CONCURRENCY = 5       # сколько сообщений одновременно гоняем через OpenAI при ingest
DEDUP_WINDOW_HOURS = 48       # апдейты по той же позиции (то же symbol/side/уровни от канала
                               # в этом окне) не считаются новым сигналом — защита от переучёта
                               # даже если промпт ошибочно пометил апдейт как is_signal=true
DEDUP_TOLERANCE = 0.003       # 0.3% — уровни считаются "теми же", если отличаются меньше этого

# ── Локальный пре-фильтр перед OpenAI ─────────────────────────
# Цель — не тратить деньги на явно нерелевантные сообщения (мемы, обсуждение,
# реклама без цифр). Намеренно permissive: пропускаем в OpenAI всё, что хотя
# бы отдалённо похоже на сигнал — задача фильтра урезать расходы на очевидный
# мусор, а не заменить собой сам экстрактор. Ложный "похоже на сигнал" стоит
# нам одного лишнего запроса; ложный "не сигнал" стоит нам потерянной сделки
# в статистике — асимметрия в пользу пропустить лишнее, а не отсеять нужное.
_SIGNAL_KEYWORDS_RE = re.compile(
    r'\b(LONG|SHORT|BUY|SELL|ВХОД|ENTRY|ЛОНГ|ШОРТ|TP\d?|SL|STOP|СТОП|TARGET|ЦЕЛЬ|TAKE.?PROFIT|STOP.?LOSS)\b',
    re.IGNORECASE,
)
_TICKER_RE = re.compile(r'\$?\b[A-Z]{2,10}\s?/?\s?USDT\b|#[A-Z]{2,10}\b')
_PRICE_RE = re.compile(r'\d{1,3}[.,]\d{1,8}|\d{3,}')  # десятичная цена или "круглое" число вроде 60000


def looks_like_signal(text: str) -> bool:
    """Быстрая локальная проверка (без сети) — стоит ли вообще тратить вызов
    OpenAI на это сообщение. False = точно не сигнал (нет ни ключевых слов
    трейдинга, ни тикера, ни похожей на цену цифры) — пропускаем без API-вызова."""
    if not text or not text.strip():
        return False
    return bool(_SIGNAL_KEYWORDS_RE.search(text) or _TICKER_RE.search(text) or _PRICE_RE.search(text))


class SignalBacktester:
    """
    Симулирует, как отработали бы сигналы канала, если бы каждый пост
    торговался с фиксированным риском на сделку (risk_per_trade_usd) — размер
    позиции считается от дистанции Entry->Stop, а не от фиксированного объёма.
    Позиции, которые не дошли ни до TP1, ни до Stop за max_hold_hours,
    принудительно закрываются по факту (цена закрытия свечи), а не "теряются"
    из статистики. Уровни (Entry/Stop/TP1) — ровно те, что указаны в самом
    посте канала, без нашей trailing-логики TP2/TP3.
    """

    def __init__(self, commission_pct=COMMISSION_PCT,
                 entry_timeout_hours=ENTRY_TIMEOUT_HOURS,
                 max_hold_hours=MAX_HOLD_HOURS,
                 risk_per_trade_usd=RISK_PER_TRADE_USD):
        self.commission_pct = commission_pct
        self.entry_timeout_hours = entry_timeout_hours
        self.max_hold_hours = max_hold_hours
        self.risk_per_trade_usd = risk_per_trade_usd

    # ── 1. Data Ingest ───────────────────────────────────────
    async def ingest_channel_history(self, channel: str, days: int = 30,
                                      concurrency: int = EXTRACT_CONCURRENCY) -> int:
        """Проходит историю канала за `days` дней, извлекает сигналы через
        существующий OpenAI-промпт и сохраняет в historical_signals.
        Идемпотентно: повторный запуск не создаёт дублей
        (UNIQUE(channel, message_id) в БД, save_historical_signal — INSERT OR IGNORE).

        Извлечение (OpenAI на каждое сообщение) — самая долгая часть ingest,
        гоняем до `concurrency` сообщений параллельно через семафор. Дедуп и
        запись в БД делаем отдельным последовательным проходом ПОСЛЕ того как
        все ответы собраны — так порядок обработки остаётся хронологическим
        (важно для дедупа: он сравнивает сигнал с ближайшим предыдущим по
        времени, а не по порядку завершения параллельных запросов)."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if not (TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION):
            raise RuntimeError("TELEGRAM_API_ID/HASH/SESSION не заданы — ingest невозможен")

        since = datetime.now(timezone.utc) - timedelta(days=days)
        sem = asyncio.Semaphore(max(1, concurrency))

        async def _extract_with_limit(msg):
            async with sem:
                try:
                    return msg, await _extract_signal(msg.raw_text)
                except Exception as e:
                    print(f"[channel_backtest] {channel}#{msg.id}: ошибка извлечения — {e}")
                    return msg, None

        client = TelegramClient(StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        async with client:
            all_messages = [m async for m in client.iter_messages(channel, offset_date=since, reverse=True) if m.raw_text]
            # Локальный пре-фильтр — режем очевидный мусор (мемы, обсуждение без
            # чисел) ДО того, как он вообще попадёт в очередь на OpenAI. Экономит
            # деньги на явно нерелевантных сообщениях без похода в сеть.
            candidate_messages = [m for m in all_messages if looks_like_signal(m.raw_text)]
            skipped_prefilter = len(all_messages) - len(candidate_messages)
            # asyncio.gather сохраняет порядок списка задач в результате — хронология не теряется,
            # хотя сами задачи выполняются параллельно (до `concurrency` штук одновременно).
            results = await asyncio.gather(*[_extract_with_limit(m) for m in candidate_messages])

        saved = 0
        skipped_dupes = 0
        recent_by_key = {}   # (symbol, side) -> (entry, stop, tp1, posted_at) последнего сохранённого

        def _is_duplicate(symbol, side, entry, stop, tp1, posted_at) -> bool:
            prev = recent_by_key.get((symbol, side))
            if not prev:
                return False
            p_entry, p_stop, p_tp1, p_posted_at = prev
            if posted_at - p_posted_at > timedelta(hours=DEDUP_WINDOW_HOURS):
                return False
            def _close(a, b):
                return abs(a - b) <= abs(b) * DEDUP_TOLERANCE
            return _close(entry, p_entry) and _close(stop, p_stop) and _close(tp1, p_tp1)

        for msg, parsed in results:
            if not parsed:
                continue

            side = str(parsed.get("side", "")).upper().strip()
            if side not in ("LONG", "SHORT"):
                continue
            try:
                symbol = normalize_symbol(str(parsed["symbol"]))
                entry, stop, tp1 = float(parsed["entry"]), float(parsed["stop"]), float(parsed["tp1"])
            except (KeyError, TypeError, ValueError):
                continue

            # tp2/tp3 — только если канал сам явно назвал уровень (промпт учит
            # возвращать null иначе); никогда не достраиваем сами.
            tp2 = parsed.get("tp2")
            tp3 = parsed.get("tp3")
            try: tp2 = float(tp2) if tp2 is not None else None
            except (TypeError, ValueError): tp2 = None
            try: tp3 = float(tp3) if tp3 is not None else None
            except (TypeError, ValueError): tp3 = None

            # Messages были собраны в порядке reverse=True (от старых к новым),
            # поэтому это сравнение ловит апдейты/реминдеры о позиции, которая
            # была открыта раньше в том же окне — даже если промпт ошибочно
            # счёл повтор новым сигналом.
            if _is_duplicate(symbol, side, entry, stop, tp1, msg.date):
                skipped_dupes += 1
                continue
            recent_by_key[(symbol, side)] = (entry, stop, tp1, msg.date)

            row_id = db.save_historical_signal(
                channel=channel, message_id=msg.id, symbol=symbol, side=side,
                entry=entry, stop=stop, tp1=tp1, tp2=tp2, tp3=tp3,
                posted_at=msg.date.isoformat(),
            )
            if row_id:
                saved += 1

        print(f"[channel_backtest] {channel}: сохранено {saved} новых сигналов за {days} дн. "
              f"(отфильтровано локально без OpenAI: {skipped_prefilter}, дубль/апдейт: {skipped_dupes})")
        return saved

    # ── 2. Backtest Engine ───────────────────────────────────
    def _fetch_ohlcv_range(self, symbol: str, since_ms: int, hours: int) -> list:
        """1m-свечи от since_ms на `hours` часов вперёд (постранично, ccxt
        отдаёт максимум ~1000 свечей за запрос) — нужна минутная точность,
        чтобы честно проверять касание Entry/TP/SL, а не смазывать часовыми барами."""
        until_ms = since_ms + hours * 3600 * 1000
        all_candles, cursor = [], since_ms
        while cursor < until_ms:
            raw = api_call(exchange.fetch_ohlcv, symbol, '1m', since=cursor, limit=1000)
            if not raw:
                break
            all_candles.extend(raw)
            last_ts = raw[-1][0]
            if last_ts <= cursor:   # защита от зацикливания, если биржа вернула тот же since
                break
            cursor = last_ts + 60_000
            if len(raw) < 1000:
                break
        return [c for c in all_candles if c[0] <= until_ms]

    def _risk_based_pnl(self, side: str, entry: float, stop: float, exit_price: float) -> dict | None:
        """Размер позиции считается от фиксированного риска на сделку, а не от
        фиксированного объёма: risk_per_trade_usd делится на дистанцию до стопа
        в цене актива — это и есть количество монет в позиции. PnL в $ и в
        процентах ОТ РИСКА (не от цены входа: +100% здесь значит "заработали
        ровно столько же, сколько было готовы потерять", т.е. R-множитель).
        Возвращает None при некорректных уровнях (entry == stop — риск не определён)."""
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return None
        position_size = self.risk_per_trade_usd / stop_distance   # количество монет
        notional_entry = position_size * entry
        notional_exit = position_size * exit_price
        commission_usd = (notional_entry + notional_exit) * (self.commission_pct / 100)
        gross_pnl_usd = (exit_price - entry) * position_size if side == 'LONG' \
            else (entry - exit_price) * position_size
        net_pnl_usd = gross_pnl_usd - commission_usd
        pnl_pct_of_risk = (net_pnl_usd / self.risk_per_trade_usd) * 100
        return dict(
            position_size=round(position_size, 6),
            pnl_usd=round(net_pnl_usd, 2),
            pnl_pct=round(pnl_pct_of_risk, 2),   # оставляем имя pnl_pct для совместимости со старыми читателями поля
        )

    def simulate_trade(self, signal: dict) -> dict:
        """
        a) искали касание Entry в течение entry_timeout_hours после поста —
           если не коснулась, сигнал не в винрейте (outcome='not_filled').
        b) с момента заполнения Entry идём по свечам до max_hold_hours: что
           случилось раньше — TP1, Stop, или истёк таймаут удержания.
           Таймаут — не "сигнал без результата", а принудительное закрытие
           по цене закрытия той свечи, на которой истекло время (реальная
           сделка так же не может висеть открытой вечно).
        c) PnL считается от фиксированного риска на сделку (risk_per_trade_usd),
           не от фиксированного объёма — см. _risk_based_pnl.
        Не бросает исключений наружу — отсутствие данных по монете или сбой
        биржи превращается в outcome='no_data', чтобы один плохой сигнал не
        валил весь прогон отчёта.
        """
        symbol, side = signal['symbol'], signal['side']
        entry, stop, tp1 = signal['entry'], signal['stop'], signal['tp1']
        tp2, tp3 = signal.get('tp2'), signal.get('tp3')
        empty = dict(entry_filled=False, entry_filled_at=None, exit_price=None,
                     pnl_pct=None, pnl_usd=None, position_size=None, tp2_hit=None, tp3_hit=None)
        try:
            posted_at = datetime.fromisoformat(signal['posted_at'])
            since_ms = int(posted_at.timestamp() * 1000)
            # Диапазон должен покрыть и ожидание входа, и весь возможный холд —
            # иначе таймаут удержания не с чем будет сравнивать по факту.
            total_hours = self.entry_timeout_hours + self.max_hold_hours
            candles = self._fetch_ohlcv_range(symbol, since_ms, total_hours)
        except Exception as e:
            return dict(outcome='no_data', reason=str(e), **empty)

        if not candles:
            return dict(outcome='no_data', reason='биржа не отдала свечи по символу', **empty)

        # a) ждём касания Entry в пределах entry_timeout_hours
        entry_timeout_ms = since_ms + self.entry_timeout_hours * 3600 * 1000
        filled_idx = None
        for i, (ts, o, h, l, close, vol) in enumerate(candles):
            if ts > entry_timeout_ms:
                break
            if l <= entry <= h:
                filled_idx = i
                break

        if filled_idx is None:
            return dict(outcome='not_filled',
                        reason=f'цена не дошла до Entry за {self.entry_timeout_hours}ч', **empty)

        filled_ts = candles[filled_idx][0]
        filled_at = datetime.fromtimestamp(filled_ts / 1000, tz=timezone.utc).isoformat()
        hold_deadline_ms = filled_ts + self.max_hold_hours * 3600 * 1000

        # b) с момента заполнения идём вперёд: TP1, Stop или принудительный
        # таймаут — что раньше. Обе цели внутри одной свечи неразличимы по
        # OHLC — консервативно считаем стоп первым, чтобы не завышать винрейт.
        for i, (ts, o, h, l, close, vol) in enumerate(candles[filled_idx:], start=filled_idx):
            hit_sl = (l <= stop) if side == 'LONG' else (h >= stop)
            hit_tp = (h >= tp1)  if side == 'LONG' else (l <= tp1)
            timed_out = ts >= hold_deadline_ms

            if hit_sl:
                exit_price, outcome = stop, 'loss'
            elif hit_tp:
                exit_price, outcome = tp1, 'win'
            elif timed_out:
                # Ни TP1, ни Stop не достигнуты за max_hold_hours — закрываем
                # по факту, по цене закрытия текущей свечи, а не выкидываем
                # сделку из статистики как "неопределённую".
                exit_price, outcome = close, 'timeout_closed'
            else:
                continue

            pnl = self._risk_based_pnl(side, entry, stop, exit_price)
            if pnl is None:
                return dict(outcome='no_data', reason='entry == stop, риск не определён', **empty)

            # Информационно: дошла ли цена дальше TP1 до TP2/TP3, которые канал
            # сам назвал (не наша trailing-надстройка) — не влияет на pnl,
            # который считается строго по фактической точке выхода.
            tp2_hit = tp3_hit = None
            if outcome == 'win':
                if tp2 is not None:
                    tp2_hit = any((c[2] >= tp2) if side == 'LONG' else (c[3] <= tp2) for c in candles[i:])
                if tp3 is not None:
                    tp3_hit = any((c[2] >= tp3) if side == 'LONG' else (c[3] <= tp3) for c in candles[i:])

            return dict(outcome=outcome, entry_filled=True, entry_filled_at=filled_at,
                        exit_price=exit_price, pnl_pct=pnl['pnl_pct'], pnl_usd=pnl['pnl_usd'],
                        position_size=pnl['position_size'], reason=None,
                        tp2_hit=tp2_hit, tp3_hit=tp3_hit)

        # Данные закончились раньше, чем наступил TP1/Stop/таймаут — обычно
        # значит, что сигнал слишком свежий и биржа ещё не отдала будущие
        # свечи. Это не "результат", а "мы пока не знаем" — не считаем закрытой
        # сделкой, чтобы не приписать ей случайный exit_price.
        return dict(outcome='still_open', entry_filled=True, entry_filled_at=filled_at,
                    reason='данных недостаточно, чтобы определить исход (сигнал слишком свежий?)',
                    exit_price=None, pnl_pct=None, pnl_usd=None, position_size=None,
                    tp2_hit=None, tp3_hit=None)

    def run_backtest(self, channel: str, recheck_all: bool = True) -> list:
        """Прогоняет сигналы канала через simulate_trade и сохраняет результат
        обратно в historical_signals.

        recheck_all=True (по умолчанию) — пересчитывает ВСЕ сигналы, а не
        только ещё не сверенные. Это дёшево (только ccxt-запросы свечей, без
        повторного похода в Telegram/OpenAI) и обязательно при повторном
        анализе с другими параметрами (max_hold_hours/risk_per_trade_usd) —
        иначе старые сигналы остались бы посчитаны по старым параметрам, а
        новые по новым, и отчёт превратился бы в мешанину несопоставимых
        цифр. unchecked_only имеет смысл только для точечного дозапуска CLI."""
        signals = db.load_historical_signals(channel, unchecked_only=not recheck_all)
        results = []
        for sig in signals:
            res = self.simulate_trade(sig)
            db.save_backtest_result(
                sig['id'], res['entry_filled'], res['entry_filled_at'],
                res['outcome'], res['exit_price'], res['pnl_pct'],
                tp2_hit=res.get('tp2_hit'), tp3_hit=res.get('tp3_hit'),
                pnl_usd=res.get('pnl_usd'), position_size=res.get('position_size'),
            )
            print(f"[channel_backtest] {sig['symbol']} {sig['side']} @ {sig['posted_at']} -> {res['outcome']}")
            results.append({**sig, **res})
        return results

    # ── 3. Analytics ──────────────────────────────────────────
    @staticmethod
    def build_report(channel: str) -> dict:
        """Отчёт по уже сверенным сигналам (читает БД, не пересчитывает
        бэктест — можно перегенерировать отчёт без повторных запросов к бирже).

        winrate/avg R:R считаются строго по "чистым" исходам (win/loss —
        реально задет TP1 или Stop), timeout_closed туда не подмешивается,
        чтобы не выдавать вынужденное закрытие по рынку за попадание в цель.
        Но total_pnl_usd/total_pnl_pct суммируют ВСЕ реально закрытые сделки,
        включая timeout_closed — деньги там реальные, их нельзя просто выкинуть
        из итога."""
        all_signals = db.load_historical_signals(channel)
        checked = [s for s in all_signals if s['checked_at']]
        wins = [s for s in checked if s['outcome'] == 'win']
        losses = [s for s in checked if s['outcome'] == 'loss']
        timeout_closed = [s for s in checked if s['outcome'] == 'timeout_closed']
        closed_all = wins + losses + timeout_closed   # всё, что реально принесло PnL

        avg_win_pct = sum(s['pnl_pct'] for s in wins) / len(wins) if wins else 0
        avg_loss_pct = abs(sum(s['pnl_pct'] for s in losses) / len(losses)) if losses else 0

        # TP2/TP3 — только среди сигналов, где канал сам их назвал (tp2/tp3 не NULL)
        wins_with_tp2 = [s for s in wins if s.get('tp2') is not None]
        wins_with_tp3 = [s for s in wins if s.get('tp3') is not None]
        tp2_hit_rate = round(sum(1 for s in wins_with_tp2 if s['tp2_hit']) / len(wins_with_tp2) * 100, 1) \
            if wins_with_tp2 else None
        tp3_hit_rate = round(sum(1 for s in wins_with_tp3 if s['tp3_hit']) / len(wins_with_tp3) * 100, 1) \
            if wins_with_tp3 else None

        return {
            "channel": channel,
            "total_signals": len(all_signals),
            "checked": len(checked),
            "not_filled": sum(1 for s in checked if s['outcome'] == 'not_filled'),
            "no_data": sum(1 for s in checked if s['outcome'] == 'no_data'),
            "still_open": sum(1 for s in checked if s['outcome'] == 'still_open'),
            "closed_trades": len(closed_all),
            "wins": len(wins),
            "losses": len(losses),
            "closed_by_timeout": len(timeout_closed),   # принудительно закрыты по max_hold_hours, не по TP/SL
            "winrate_pct": round(len(wins) / (len(wins) + len(losses)) * 100, 1) if (wins or losses) else None,
            "avg_risk_reward": round(avg_win_pct / avg_loss_pct, 2) if avg_loss_pct else None,
            "total_pnl_pct_of_risk": round(sum(s['pnl_pct'] for s in closed_all if s['pnl_pct'] is not None), 2),
            "total_pnl_usd": round(sum(s['pnl_usd'] for s in closed_all if s['pnl_usd'] is not None), 2),
            "tp2_hit_rate": tp2_hit_rate,           # % выигрышей, дошедших до TP2 (из тех, где канал его назвал)
            "tp2_sample": len(wins_with_tp2),        # сколько выигрышей вообще имели заявленный TP2
            "tp3_hit_rate": tp3_hit_rate,
            "tp3_sample": len(wins_with_tp3),
        }

    @staticmethod
    def build_equity_curve(channel: str) -> list:
        """Кумулятивный $PnL (риск-based) по закрытым сделкам (включая
        принудительно закрытые по таймауту) в хронологическом порядке —
        для графика доходности на фронтенде (Recharts)."""
        signals = db.load_historical_signals(channel)
        closed = sorted(
            (s for s in signals if s['outcome'] in ('win', 'loss', 'timeout_closed') and s['pnl_usd'] is not None),
            key=lambda s: s['posted_at'],
        )
        curve, cum_usd = [], 0.0
        for s in closed:
            cum_usd += s['pnl_usd']
            curve.append({"date": s['posted_at'][:10], "cum_pnl_usd": round(cum_usd, 2)})
        return curve


def print_report(report: dict):
    print(f"\n=== Отчёт по каналу {report['channel']} ===")
    print(f"Всего сигналов найдено:      {report['total_signals']}")
    print(f"Сверено с рынком:            {report['checked']}")
    print(f"  из них не дошли до Entry:  {report['not_filled']}")
    print(f"  нет данных по монете:      {report['no_data']}")
    print(f"  ещё не определён исход:    {report['still_open']}")
    print(f"Закрытых сделок:             {report['closed_trades']}")
    print(f"  прибыльных (TP1):          {report['wins']}")
    print(f"  убыточных (Stop):          {report['losses']}")
    print(f"  закрыто по таймауту:       {report['closed_by_timeout']}")
    print(f"Winrate (по TP1/Stop):       {report['winrate_pct']}%")
    print(f"Средний Risk/Reward:         {report['avg_risk_reward']}")
    print(f"Итоговый PnL (% от риска):   {report['total_pnl_pct_of_risk']}%")
    print(f"Итоговый PnL ($):            {report['total_pnl_usd']}$\n")


async def main():
    parser = argparse.ArgumentParser(description="Бэктест исторической эффективности Telegram-канала")
    parser.add_argument("channel", help="username канала без @, например binancekillers")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-hold-hours", type=int, default=MAX_HOLD_HOURS)
    parser.add_argument("--risk-usd", type=float, default=RISK_PER_TRADE_USD)
    args = parser.parse_args()

    db.init_db()
    bt = SignalBacktester(max_hold_hours=args.max_hold_hours, risk_per_trade_usd=args.risk_usd)
    await bt.ingest_channel_history(args.channel, days=args.days)
    bt.run_backtest(args.channel)
    print_report(bt.build_report(args.channel))


if __name__ == "__main__":
    asyncio.run(main())
