import asyncio
import os
import sqlite3
import ccxt
import pandas as pd
import plotly.graph_objects as go
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

# --- НАСТРОЙКИ ---
API_TOKEN = '8726753006:AAGI8F1B63zi0UyqtMHN3nYg4UwJh6owFaY'
SYMBOL = 'ETH/USDT'
TIMEFRAME = '15m'
CHECK_INTERVAL = 300  # 5 минут между проверками сигналов

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
exchange = ccxt.bybit()


# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()


def add_subscriber(user_id):
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()


def get_subscribers():
    conn = sqlite3.connect('subscribers.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


# --- ВИЗУАЛИЗАЦИЯ ---
async def create_chart(df, pattern_name):
    """Генерирует график свечей с отметкой паттерна"""
    plot_df = df.tail(40).copy()

    fig = go.Figure(data=[go.Candlestick(
        x=plot_df.index,
        open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        name='Candlesticks'
    )])

    # Координаты для стрелки (последняя свеча)
    last_idx = plot_df.index[-1]
    last_high = plot_df['high'].max()

    fig.add_annotation(
        x=last_idx, y=plot_df['high'].iloc[-1], text=pattern_name,
        showarrow=True, arrowhead=2, arrowcolor="yellow",
        ax=0, ay=-50, bgcolor="black", font=dict(color="white", size=14)
    )

    fig.update_layout(
        template='plotly_dark',
        xaxis_rangeslider_visible=False,
        title=f"Bybit: {SYMBOL} ({TIMEFRAME})",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )

    file_path = "signal_chart.png"
    fig.write_image(file_path)
    return file_path


# --- МАТЕМАТИКА АНАЛИЗА (БЕЗ TA-LIB) ---
def analyze_market():
    """Ручной анализ свечных паттернов"""
    try:
        bars = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
        df['timestamp'] = pd.to_datetime(df['ts'], unit='ms')
        df.set_index('timestamp', inplace=True)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        res = {"found": False, "name": "", "side": "", "df": df}

        # 1. Бычье поглощение
        if curr['close'] > curr['open'] and prev['close'] < prev['open']:
            if curr['close'] >= prev['open'] and curr['open'] <= prev['close']:
                res.update({"found": True, "name": "Бычье Поглощение", "side": "LONG 📈"})

        # 2. Медвежье поглощение
        elif curr['close'] < curr['open'] and prev['close'] > prev['open']:
            if curr['close'] <= prev['open'] and curr['open'] >= prev['close']:
                res.update({"found": True, "name": "Медвежье Поглощение", "side": "SHORT 📉"})

        # 3. Молот (Hammer)
        else:
            body = abs(curr['close'] - curr['open'])
            lower_shadow = min(curr['open'], curr['close']) - curr['low']
            upper_shadow = curr['high'] - max(curr['open'], curr['close'])
            if body > 0 and lower_shadow > (body * 2) and upper_shadow < (body * 0.5):
                res.update({"found": True, "name": "Молот (Разворот)", "side": "LONG 📈"})

        return res
    except Exception as e:
        print(f"Ошибка в analyze_market: {e}")
        return {"found": False}


# --- ЦИКЛ МОНИТОРИНГА ---
async def monitoring_loop():
    print(f"Мониторинг {SYMBOL} на Bybit запущен...")
    while True:
        analysis = analyze_market()

        if analysis["found"]:
            print(f"Найден паттерн: {analysis['name']}")
            chart_file = await create_chart(analysis["df"], analysis["name"])

            text = (
                f"🚨 **СИГНАЛ: {analysis['name']}**\n\n"
                f"📊 Направление: {analysis['side']}\n"
                f"💰 Цена ETH: {analysis['df']['close'].iloc[-1]} USDT\n"
                f"⏱ Таймфрейм: {TIMEFRAME}\n\n"
                f"💡 *Рекомендация:* Проверьте объем и уровни поддержки/сопротивления перед входом."
            )

            for user_id in get_subscribers():
                try:
                    photo = FSInputFile(chart_file)
                    await bot.send_photo(user_id, photo=photo, caption=text, parse_mode="Markdown")
                except Exception as e:
                    print(f"Ошибка рассылки юзеру {user_id}: {e}")

            if os.path.exists(chart_file):
                os.remove(chart_file)

            # Пауза, чтобы не присылать одну и ту же закрытую свечу несколько раз
            await asyncio.sleep(CHECK_INTERVAL)
        else:
            # Если сигнала нет, проверяем через минуту
            await asyncio.sleep(60)


# --- ОБРАБОТКА КОМАНД ---
@dp.message(Command("start"))
async def start(message: types.Message):
    add_subscriber(message.from_user.id)
    await message.answer(
        f"Бот-аналитик запущен! 🚀\n\nЯ слежу за парой {SYMBOL} на Bybit. "
        "Как только увижу разворотный свечной паттерн — сразу пришлю тебе скриншот графика."
    )


# --- ЗАПУСК ---
async def main():
    init_db()
    # Запускаем фоновый мониторинг
    asyncio.create_task(monitoring_loop())
    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")