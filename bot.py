import asyncio
import sqlite3
import ccxt
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

# --- НАСТРОЙКИ (ЗАМЕНИТЕ ТОКЕН!) ---
API_TOKEN = 'ВАШ_НОВЫЙ_ТОКЕН_ОТ_BOTFATHER'
SYMBOL = 'ETH/USDT'
TIMEFRAME = '15m'
CHECK_INTERVAL = 300  # 5 минут

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
exchange = ccxt.bybit()

# --- БАЗА ДАННЫХ ---
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
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]

# --- ЛОГИКА АНАЛИЗА ---
def detect_patterns(df):
    """
    Простая логика поиска паттерна 'Молот' (Hammer).
    Вы можете заменить её на свою.
    """
    last_row = df.iloc[-1]
    body = abs(last_row['close'] - last_row['open'])
    lower_shadow = min(last_row['open'], last_row['close']) - last_row['low']
    upper_shadow = last_row['high'] - max(last_row['open'], last_row['close'])
    
    # Упрощенное условие Молота: длинная нижняя тень, маленькое тело
    if lower_shadow > body * 2 and upper_shadow < body:
        return "Молот (Разворот вверх)"
    return None

async def monitoring_loop():
    print(f"Мониторинг {SYMBOL} запущен...")
    while True:
        try:
            # Получаем данные с биржи
            ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=50)
            df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            
            pattern = detect_patterns(df)
            
            if pattern:
                last_price = df['close'].iloc[-1]
                time_now = datetime.now().strftime("%H:%M:%S")
                subscribers = get_subscribers()
                
                text = (
                    f"🚨 **НОВЫЙ СИГНАЛ** 🚨\n\n"
                    f"💎 **Актив:** {SYMBOL}\n"
                    f"📊 **Паттерн:** {pattern}\n"
                    f"💰 **Цена:** {last_price:.2f} USDT\n"
                    f"⏰ **Время:** {time_now} (МСК)\n"
                    f"⏳ **Таймфрейм:** {TIMEFRAME}\n\n"
                    f"👉 *Проверьте график перед входом!*"
                )
                
                for user_id in subscribers:
                    try:
                        await bot.send_message(user_id, text, parse_mode="Markdown")
                    except Exception as e:
                        print(f"Не удалось отправить сообщение {user_id}: {e}")
            
        except Exception as e:
            print(f"Ошибка в цикле мониторинга: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    add_subscriber(message.from_user.id)
    await message.answer(f"Привет! Я буду присылать сигналы по {SYMBOL} ({TIMEFRAME}) прямо сюда.")

# --- ЗАПУСК ---
async def main():
    init_db()
    # Запускаем мониторинг как фоновую задачу
    asyncio.create_task(monitoring_loop())
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")
