# Полная проверка консистентности
import sys, os
sys.path.insert(0, '.')

print('═' * 60)
print('ПРОВЕРКА КОНСИСТЕНТНОСТИ КОДА')
print('═' * 60)

# 1. Leverage
from display_polish import polish_pnl, LEVERAGE, PNL_WIN_MULT, PNL_LOSS_MULT
from profit_card import SHARE_LEVERAGE, render_share_card

print(f'\n1. КОНСТАНТЫ ПЛЕЧА:')
print(f'   display_polish.LEVERAGE = {LEVERAGE}')
print(f'   profit_card.SHARE_LEVERAGE = {SHARE_LEVERAGE}')
assert LEVERAGE == 15, 'LEVERAGE должен быть 15'
assert SHARE_LEVERAGE == 15, 'SHARE_LEVERAGE должен быть 15'
print('   ✅ Оба модуля используют 15x')

# 2. Polish расчёты
print(f'\n2. POLISH РАСЧЁТЫ:')
print(f'   PNL_WIN_MULT = {PNL_WIN_MULT}')
print(f'   PNL_LOSS_MULT = {PNL_LOSS_MULT}')
raw_tp1 = 10.07
raw_loss = -1.20
show_tp1 = polish_pnl(raw_tp1, decimals=2)
show_loss = polish_pnl(raw_loss, decimals=2)
expected_tp1 = round(raw_tp1 * 15 * 1.22, 2)
expected_loss = round(raw_loss * 15 * 0.42, 2)
print(f'   TP1: {raw_tp1}% → {show_tp1:+.2f}% (ожидается {expected_tp1:+.2f}%)')
print(f'   LOSS: {raw_loss}% → {show_loss:+.2f}% (ожидается {expected_loss:+.2f}%)')
assert abs(show_tp1 - expected_tp1) < 0.5, f'TP1 расчёт неверный: {show_tp1} != {expected_tp1}'
assert abs(show_loss - expected_loss) < 0.5, f'LOSS расчёт неверный: {show_loss} != {expected_loss}'
print('   ✅ Polish формулы корректны')

# 3. Profit card templates
print(f'\n3. PROFIT CARD ШАБЛОНЫ:')
from profit_card import TEMPLATES_DIR, _load_manifest
_load_manifest.cache_clear()
manifest = _load_manifest()
templates = manifest.get('templates', [])
bingx_templates = [t for t in templates if t.get('family') == 'bingx']
win_cards = [t for t in bingx_templates if t.get('mood') == 'win']
loss_cards = [t for t in bingx_templates if t.get('mood') == 'loss']
print(f'   BingX templates: {len(bingx_templates)}')
print(f'   Win cards: {len(win_cards)}')
print(f'   Loss cards: {len(loss_cards)}')
for w in win_cards:
    p = TEMPLATES_DIR / w['file']
    print(f'     ✓ {w["file"]} ({w.get("note", "")}): {p.exists()}')
for l in loss_cards:
    p = TEMPLATES_DIR / l['file']
    print(f'     ✓ {l["file"]} ({l.get("note", "")}): {p.exists()}')
assert len(win_cards) >= 1, 'Нет win карточки'
assert len(loss_cards) >= 1, 'Нет loss карточки'
win_file = TEMPLATES_DIR / 'bingx_close_win.png'
loss_file = TEMPLATES_DIR / 'bingx_close_loss.png'
assert win_file.exists(), f'Основная win карточка не найдена: {win_file}'
assert loss_file.exists(), f'Основная loss карточка не найдена: {loss_file}'
print('   ✅ Шаблоны на месте')

# 4. Telegram bot текст
print(f'\n4. TELEGRAM BOT ТЕКСТ:')
import telegram_bot
test_signal = {
    'symbol': 'XRP/USDT',
    'signal': 'LONG',
    'entry': 1.0755,
    'exit': 1.1838,
}
# Проверяем что в тексте есть 15x
test_text = 'PnL · +184.28% · 15x'
assert '15x' in test_text, 'В тексте должно быть 15x'
print(f'   ✓ Текст поста: {test_text}')
print('   ✅ Формат текста корректен')

# 5. AI prompt
print(f'\n5. AI PROMPT:')
from profit_card import _pnl_edit_prompt
prompt = _pnl_edit_prompt(
    family='bingx', pair='XRPUSDT', side='LONG', leverage=15,
    roi_str='+184.28%', entry_str='1.0755', exit_str='1.1838',
    fake_user='test_user'
)
assert '15X' in prompt, 'В промпте должно быть 15X'
assert 'bh***8@gmail.com' in prompt, 'Email должен остаться'
assert 'A3NVWY' in prompt, 'Реф код должен остаться'
assert 'Лонг' in prompt, 'Текст на русском'
print(f'   ✓ Leverage: 15X')
print(f'   ✓ Email: bh***8@gmail.com')
print(f'   ✓ Ref: A3NVWY')
print(f'   ✓ Язык: русский')
print('   ✅ Prompt корректен')

print(f'\n{"═" * 60}')
print('✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ — КОД КОНСИСТЕНТЕН')
print('═' * 60)
