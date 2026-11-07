from logic import TOKEN
import telebot
from telebot import types
import psutil
import time
import threading
import platform
import requests
import io
import os
import pyautogui
import subprocess
import sys
from datetime import datetime
from ID import ADMIN_ID
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPORT_INTERVAL = 300
MAX_HISTORY = 20

bot = telebot.TeleBot(TOKEN)
START_TIME = time.time()
SUBSCRIBERS = set()

# История для графиков
CPU_HISTORY = []
RAM_HISTORY = []
TIME_HISTORY = []

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def is_admin(message):
    """Проверяет, что команду дал владелец ПК."""
    return message.from_user.id == ADMIN_ID

def make_bar(percent, length=10):
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percent:.1f}%"

def get_uptime():
    sec = int(time.time() - START_TIME)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}ч {m}м {s}с"

def check_internet():
    try:
        start = time.perf_counter()
        requests.head("https://www.google.com", timeout=3)
        ping = (time.perf_counter() - start) * 1000
        return f"✅ <b>Онлайн</b> (Пинг: {ping:.0f} мс)"
    except (requests.ConnectionError, requests.Timeout):
        return "❌ <b>Нет соединения</b>"

def get_top_processes():
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            if proc.info['cpu_percent'] is not None and proc.info['memory_percent'] is not None:
                procs.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    top_cpu = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:3]
    top_ram = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:3]

    cpu_text = "🔥 <b>Топ по CPU:</b>\n"
    for p in top_cpu:
        cpu_text += f"• {p['name'][:15]}: {p['cpu_percent']}%\n"
    ram_text = "🧠 <b>Топ по RAM:</b>\n"
    for p in top_ram:
        ram_text += f"• {p['name'][:15]}: {p['memory_percent']:.1f}%\n"
    return f"{cpu_text}\n{ram_text}"

def update_history(cpu, ram):
    now = datetime.now().strftime('%H:%M')
    TIME_HISTORY.append(now)
    CPU_HISTORY.append(cpu)
    RAM_HISTORY.append(ram)
    if len(TIME_HISTORY) > MAX_HISTORY:
        TIME_HISTORY.pop(0)
        CPU_HISTORY.pop(0)
        RAM_HISTORY.pop(0)

def generate_chart():
    if not CPU_HISTORY: return None
    plt.figure(figsize=(8, 4))
    plt.plot(TIME_HISTORY, CPU_HISTORY, marker='o', color='#ff5722', label='CPU (%)', linewidth=2)
    plt.plot(TIME_HISTORY, RAM_HISTORY, marker='s', color='#2196f3', label='RAM (%)', linewidth=2)
    plt.title('System Load History', color='white')
    plt.ylabel('Percent (%)', color='white')
    plt.ylim(0, 100)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.gca().set_facecolor('#17212b')
    plt.gcf().patch.set_facecolor('#17212b')
    plt.tick_params(colors='white')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#17212b')
    buf.seek(0)
    plt.close()
    return buf

# --- УПРАВЛЕНИЕ ПК ---
def execute_cmd(command):
    """Выполняет команду в консоли и возвращает результат."""
    try:
        encoding = 'cp866' if platform.system() == 'Windows' else 'utf-8'
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding=encoding, timeout=15)
        
        output = result.stdout.strip() if result.stdout else result.stderr.strip()
        if not output:
            output = "Команда выполнена (пустой вывод)."
        return output
    except subprocess.TimeoutExpired:
        return "❌ Ошибка: Команда выполнялась слишком долго (таймаут 15 сек)."
    except Exception as e:
        return f"❌ Ошибка выполнения: {e}"

# --- СБОР ДАННЫХ И ОТЧЕТ ---
def build_report():
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    update_history(cpu, ram.percent)
    net_status = check_internet()
    top_procs = get_top_processes()
    
    text = (
        f"<b>🖥 СИСТЕМА:</b> <code>{platform.node()}</code>\n"
        f"<b>⏱ Аптайм:</b> <code>{get_uptime()}</code>\n"
        f"<b>🌐 Сеть:</b> {net_status}\n\n"
        f"🧠 <b>CPU</b> {make_bar(cpu)}\n"
        f"💾 <b>RAM</b> {make_bar(ram.percent)}\n"
        f"<i>использовано: {ram.used / (1024**3):.1f} / {ram.total / (1024**3):.1f} GB</i>\n\n"
        f"💿 <b>Диск</b> {make_bar(disk.percent)}\n\n"
        f"📊 <b>Активные процессы:</b>\n"
        f"{top_procs}"
    )
    return text

def get_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_status = types.InlineKeyboardButton("🔄 Обновить", callback_data="status")
    btn_chart = types.InlineKeyboardButton("📊 Графики", callback_data="chart")
    btn_ping = types.InlineKeyboardButton("🌐 Пинг", callback_data="ping")
    btn_stop = types.InlineKeyboardButton("🔕 Отписаться", callback_data="stop")
    markup.add(btn_status, btn_chart)
    markup.add(btn_ping, btn_stop)
    return markup

# --- ФОНОВАЯ РАССЫЛКА ---
def auto_report_loop():
    while True:
        time.sleep(REPORT_INTERVAL)
        if SUBSCRIBERS:
            report = build_report()
            for chat_id in list(SUBSCRIBERS):
                try:
                    bot.send_message(chat_id, report, parse_mode="HTML", reply_markup=get_main_keyboard())
                except Exception:
                    SUBSCRIBERS.discard(chat_id)

# --- КОМАНДЫ ---
@bot.message_handler(commands=["start"])
def cmd_start(message):
    SUBSCRIBERS.add(message.chat.id)
    welcome_text = (
        f"👋 <b>Привет!</b>\n\n"
        "Я — твой удаленный администратор ПК.\n\n"
        "🛠 <b>Команды управления:</b>\n"
        "<code>/cmd &lt;команда&gt;</code> — выполнить в консоли (например, <code>/cmd dir</code> или <code>/cmd ipconfig</code>)\n"
        "📸 <code>/screen</code> — сделать скриншот экрана\n"
        "🔒 <code>/lock</code> — заблокировать ПК\n"
        "🔄 <code>/reboot</code> — перезагрузить\n"
        "🛑 <code>/shutdown</code> — выключить\n\n"
        "Для управления ПК напиши эти команды сюда."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@bot.message_handler(commands=["status"])
def cmd_status(message):
    bot.send_message(message.chat.id, build_report(), parse_mode="HTML", reply_markup=get_main_keyboard())

@bot.message_handler(commands=["cmd"])
def cmd_exec(message):
    if not is_admin(message):
        bot.reply_to(message, "⛔️ У тебя нет прав для управления этим ПК.")
        return
    command = message.text.replace("/cmd", "").strip()
    if not command:
        bot.reply_to(message, "Использование: <code>/cmd ipconfig</code>", parse_mode="HTML")
        return
    bot.reply_to(message, f"⚙️ Выполняю: <code>{command}</code>...", parse_mode="HTML")
    result = execute_cmd(command)
    # Обрезаем слишком длинный вывод (Telegram не принимает сообщения > 4096 символов)
    if len(result) > 4000:
        result = result[:4000] + "\n\n... (вывод обрезан)"
    bot.send_message(message.chat.id, f"<b>Результат:</b>\n<pre>{result}</pre>", parse_mode="HTML")

@bot.message_handler(commands=["screen"])
def cmd_screen(message):
    if not is_admin(message): return
    try:
        screen = pyautogui.screenshot()
        img_byte_arr = io.BytesIO()
        screen.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        bot.send_photo(message.chat.id, img_byte_arr, caption="📸 Скриншот рабочего стола")
    except Exception as e:
        bot.reply_to(message, f"❌ Не удалось сделать скриншот: {e}")

@bot.message_handler(commands=["lock"])
def cmd_lock(message):
    if not is_admin(message): return
    bot.reply_to(message, "🔒 Блокирую ПК...")
    if platform.system() == 'Windows':
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    elif platform.system() == 'Linux':
        os.system("xdg-screensaver lock")
    elif platform.system() == 'Darwin': # macOS
        os.system("pmset displaysleepnow")

@bot.message_handler(commands=["reboot"])
def cmd_reboot(message):
    if not is_admin(message): return
    bot.reply_to(message, "🔄 Перезагружаю ПК...")
    if platform.system() == 'Windows':
        os.system("shutdown /r /t 5")
    else:
        os.system("sudo reboot")

@bot.message_handler(commands=["shutdown"])
def cmd_shutdown(message):
    if not is_admin(message): return
    bot.reply_to(message, "🛑 Выключаю ПК...")
    if platform.system() == 'Windows':
        os.system("shutdown /s /t 5")
    else:
        os.system("sudo shutdown -h now")

# --- ОБРАБОТЧИК КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "status":
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=build_report(), parse_mode="HTML", reply_markup=get_main_keyboard()
            )
        except Exception:
            bot.answer_callback_query(call.id, text="✅ Данные актуальны")
    elif call.data == "ping":
        status = check_internet().replace("<b>", "").replace("</b>", "")
        bot.answer_callback_query(call.id, text=f"Результат: {status}", show_alert=True)
    elif call.data == "chart":
        bot.answer_callback_query(call.id, text="Строю график...")
        chart_buf = generate_chart()
        if chart_buf:
            bot.send_photo(call.message.chat.id, chart_buf, caption=f"📈 История за последние {len(CPU_HISTORY)} проверок")
    elif call.data == "stop":
        SUBSCRIBERS.discard(call.message.chat.id)
        bot.answer_callback_query(call.id, text="Отключено")
        bot.edit_message_text("Автоотчёты отключены.", call.message.chat.id, call.message.message_id, reply_markup=None)

# --- ЗАПУСК ---
if __name__ == "__main__":
    threading.Thread(target=auto_report_loop, daemon=True).start()
    print("Бот запущен и готов к управлению...")
    bot.infinity_polling()