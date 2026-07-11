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
from datetime import datetime, timedelta, timezone

import database as db
from data_layer import exchange, api_call
from telegram_ingest import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION,
    _extract_signal, normalize_symbol,
)

COMMISSION_PCT = 0.1          # 0.1% за сторону (вход + выход = 0.2% с сделки)
ENTRY_TIMEOUT_HOURS = 6       # если цена не дошла до Entry за это время — сигнал не в винрейте
MAX_TRADE_HOURS = 72          # максимум ждём выход по TP1/Stop


class SignalBacktester:
    """
    Симулирует, как отработали бы сигналы канала, если бы каждый пост
    торговался фиксированным объёмом по цене Entry/Stop/TP1, как они указаны
    в самом посте (без нашей trailing-логики TP2/TP3).
    """

    def __init__(self, commission_pct=COMMISSION_PCT,
                 entry_timeout_hours=ENTRY_TIMEOUT_HOURS,
                 max_trade_hours=MAX_TRADE_HOURS):
        self.commission_pct = commission_pct
        self.entry_timeout_hours = entry_timeout_hours
        self.max_trade_hours = max_trade_hours

    # ── 1. Data Ingest ───────────────────────────────────────
    async def ingest_channel_history(self, channel: str, days: int = 30) -> int:
        """Проходит историю канала за `days` дней, извлекает сигналы через
        существующий OpenAI-промпт и сохраняет в historical_signals.
        Идемпотентно: повторный запуск не создаёт дублей
        (UNIQUE(channel, message_id) в БД, save_historical_signal — INSERT OR IGNORE)."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if not (TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION):
            raise RuntimeError("TELEGRAM_API_ID/HASH/SESSION не заданы — ingest невозможен")

        since = datetime.now(timezone.utc) - timedelta(days=days)
        saved = 0

        client = TelegramClient(StringSession(TELEGRAM_SESSION), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        async with client:
            async for msg in client.iter_messages(channel, offset_date=since, reverse=True):
                if not msg.raw_text:
                    continue
                try:
                    parsed = await _extract_signal(msg.raw_text)
                except Exception as e:
                    print(f"[channel_backtest] {channel}#{msg.id}: ошибка извлечения — {e}")
                    continue
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

                row_id = db.save_historical_signal(
                    channel=channel, message_id=msg.id, symbol=symbol, side=side,
                    entry=entry, stop=stop, tp1=tp1,
                    posted_at=msg.date.isoformat(),
                )
                if row_id:
                    saved += 1

        print(f"[channel_backtest] {channel}: сохранено {saved} новых сигналов за {days} дн.")
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

    def simulate_trade(self, signal: dict) -> dict:
        """
        a) искали касание Entry в течение entry_timeout_hours после поста —
           если не коснулась, сигнал не в винрейте (outcome='not_filled').
        b) с момента заполнения Entry идём по свечам до max_trade_hours:
           что случилось раньше — TP1 или Stop.
        Не бросает исключений наружу — отсутствие данных по монете или сбой
        биржи превращается в outcome='no_data', чтобы один плохой сигнал не
        валил весь прогон отчёта.
        """
        symbol, side = signal['symbol'], signal['side']
        entry, stop, tp1 = signal['entry'], signal['stop'], signal['tp1']
        try:
            posted_at = datetime.fromisoformat(signal['posted_at'])
            since_ms = int(posted_at.timestamp() * 1000)
            candles = self._fetch_ohlcv_range(symbol, since_ms, self.max_trade_hours)
        except Exception as e:
            return dict(outcome='no_data', entry_filled=False, entry_filled_at=None,
                        exit_price=None, pnl_pct=None, reason=str(e))

        if not candles:
            return dict(outcome='no_data', entry_filled=False, entry_filled_at=None,
                        exit_price=None, pnl_pct=None, reason='биржа не отдала свечи по символу')

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
            return dict(outcome='not_filled', entry_filled=False, entry_filled_at=None,
                        exit_price=None, pnl_pct=None,
                        reason=f'цена не дошла до Entry за {self.entry_timeout_hours}ч')

        filled_ts = candles[filled_idx][0]
        filled_at = datetime.fromtimestamp(filled_ts / 1000, tz=timezone.utc).isoformat()

        # b) с момента заполнения идём вперёд: что раньше — TP1 или Stop.
        # Обе цели внутри одной свечи неразличимы по OHLC — консервативно
        # считаем стоп первым, чтобы не завышать винрейт.
        for ts, o, h, l, close, vol in candles[filled_idx:]:
            hit_sl = (l <= stop) if side == 'LONG' else (h >= stop)
            hit_tp = (h >= tp1)  if side == 'LONG' else (l <= tp1)
            if hit_sl:
                exit_price, outcome = stop, 'loss'
            elif hit_tp:
                exit_price, outcome = tp1, 'win'
            else:
                continue

            gross_pnl_pct = ((exit_price - entry) / entry * 100) if side == 'LONG' \
                else ((entry - exit_price) / entry * 100)
            net_pnl_pct = gross_pnl_pct - self.commission_pct * 2  # комиссия на вход и на выход
            return dict(outcome=outcome, entry_filled=True, entry_filled_at=filled_at,
                        exit_price=exit_price, pnl_pct=round(net_pnl_pct, 3), reason=None)

        return dict(outcome='timeout', entry_filled=True, entry_filled_at=filled_at,
                    exit_price=None, pnl_pct=None,
                    reason=f'ни TP1 ни Stop не достигнуты за {self.max_trade_hours}ч')

    def run_backtest(self, channel: str) -> list:
        """Прогоняет все ещё не сверенные сигналы канала через simulate_trade
        и сохраняет результат обратно в historical_signals."""
        signals = db.load_historical_signals(channel, unchecked_only=True)
        results = []
        for sig in signals:
            res = self.simulate_trade(sig)
            db.save_backtest_result(
                sig['id'], res['entry_filled'], res['entry_filled_at'],
                res['outcome'], res['exit_price'], res['pnl_pct'],
            )
            print(f"[channel_backtest] {sig['symbol']} {sig['side']} @ {sig['posted_at']} -> {res['outcome']}")
            results.append({**sig, **res})
        return results

    # ── 3. Analytics ──────────────────────────────────────────
    @staticmethod
    def build_report(channel: str) -> dict:
        """Отчёт по уже сверенным сигналам (читает БД, не пересчитывает
        бэктест — можно перегенерировать отчёт без повторных запросов к бирже)."""
        all_signals = db.load_historical_signals(channel)
        checked = [s for s in all_signals if s['checked_at']]
        closed = [s for s in checked if s['outcome'] in ('win', 'loss')]
        wins = [s for s in closed if s['outcome'] == 'win']
        losses = [s for s in closed if s['outcome'] == 'loss']

        avg_win_pct = sum(s['pnl_pct'] for s in wins) / len(wins) if wins else 0
        avg_loss_pct = abs(sum(s['pnl_pct'] for s in losses) / len(losses)) if losses else 0

        return {
            "channel": channel,
            "total_signals": len(all_signals),
            "checked": len(checked),
            "not_filled": sum(1 for s in checked if s['outcome'] == 'not_filled'),
            "no_data": sum(1 for s in checked if s['outcome'] == 'no_data'),
            "timeout": sum(1 for s in checked if s['outcome'] == 'timeout'),
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "winrate_pct": round(len(wins) / len(closed) * 100, 1) if closed else None,
            "avg_risk_reward": round(avg_win_pct / avg_loss_pct, 2) if avg_loss_pct else None,
            "total_pnl_pct_fixed_size": round(sum(s['pnl_pct'] for s in closed if s['pnl_pct'] is not None), 2),
        }

    @staticmethod
    def build_equity_curve(channel: str) -> list:
        """Кумулятивный PnL% по закрытым сделкам в хронологическом порядке —
        для графика доходности на фронтенде (Recharts)."""
        signals = db.load_historical_signals(channel)
        closed = sorted(
            (s for s in signals if s['outcome'] in ('win', 'loss') and s['pnl_pct'] is not None),
            key=lambda s: s['posted_at'],
        )
        curve, cum = [], 0.0
        for s in closed:
            cum += s['pnl_pct']
            curve.append({"date": s['posted_at'][:10], "cum_pnl_pct": round(cum, 2)})
        return curve


def print_report(report: dict):
    print(f"\n=== Отчёт по каналу {report['channel']} ===")
    print(f"Всего сигналов найдено:      {report['total_signals']}")
    print(f"Сверено с рынком:            {report['checked']}")
    print(f"  из них не дошли до Entry:  {report['not_filled']}")
    print(f"  нет данных по монете:      {report['no_data']}")
    print(f"  таймаут (не дошли TP/SL):  {report['timeout']}")
    print(f"Закрытых сделок:             {report['closed_trades']}")
    print(f"  прибыльных:                {report['wins']}")
    print(f"  убыточных:                 {report['losses']}")
    print(f"Winrate:                     {report['winrate_pct']}%")
    print(f"Средний Risk/Reward:         {report['avg_risk_reward']}")
    print(f"Итоговый PnL (фикс. объём):  {report['total_pnl_pct_fixed_size']}%\n")


async def main():
    parser = argparse.ArgumentParser(description="Бэктест исторической эффективности Telegram-канала")
    parser.add_argument("channel", help="username канала без @, например binancekillers")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    db.init_db()
    bt = SignalBacktester()
    await bt.ingest_channel_history(args.channel, days=args.days)
    bt.run_backtest(args.channel)
    print_report(bt.build_report(args.channel))


if __name__ == "__main__":
    asyncio.run(main())
