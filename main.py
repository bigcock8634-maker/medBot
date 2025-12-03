import asyncio
import logging
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройки
API_TOKEN = '8582802036:AAFvcqzw01ScMAKuTvAlZSh-5wGtLgPg9lQ'
ADMIN_ID = 8365782992  # ID администратора

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_scam_experience = State()
    waiting_for_hours = State()

# Файл для хранения данных
DATA_FILE = 'bot_data.json'

def load_data():
    """Загрузка данных из файла"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'user_data': {}, 'approved_users': []}
    return {'user_data': {}, 'approved_users': []}

def save_data():
    """Сохранение данных в файл"""
    data_to_save = {
        'user_data': user_data,
        'approved_users': list(approved_users)
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

# Загрузка данных при старте
data = load_data()
user_data = data.get('user_data', {})
approved_users = set(data.get('approved_users', []))

# Конвертируем ключи user_data в int (при загрузке из JSON они становятся строками)
user_data = {int(k): v for k, v in user_data.items()}

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Проверяем, одобрен ли уже пользователь
    if message.from_user.id in approved_users:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Прочитал", callback_data="read_manual")]
        ])
        
        await message.answer(
            "ПЕРЕД НАЧАЛОМ РАБОТЫ ПРОЧИТАЙТЕ МАНУАЛ ПО РАБОТЕ\n\n"
            "https://t.me/+D97mwF58sLY5ZWFh",
            reply_markup=keyboard
        )
        return
    
    # Проверяем, заполнял ли уже анкету
    user_id = message.from_user.id
    if str(user_id) in user_data or user_id in user_data:
        await message.answer("Ваша анкета уже отправлена на рассмотрение. Ожидайте ответа.")
        return
    
    # Новый пользователь
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить анкету", callback_data="fill_form")]
    ])
    
    await message.answer(
        "Перед началом работы заполните анкету.",
        reply_markup=keyboard
    )

# Начало заполнения анкеты
@dp.callback_query(F.data == "fill_form")
async def start_form(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id in approved_users:
        await callback.answer("Вы уже одобрены!", show_alert=True)
        return
    
    if str(user_id) in user_data or user_id in user_data:
        await callback.answer("Вы уже отправили анкету!", show_alert=True)
        return
        
    await callback.message.edit_text(
        "1) Есть ли опыт в ворке тематики скама, если есть то расскажите о нем и о ваших профитах"
    )
    await state.set_state(Form.waiting_for_scam_experience)
    await callback.answer()

# Получение ответа на первый вопрос
@dp.message(Form.waiting_for_scam_experience)
async def process_scam_experience(message: types.Message, state: FSMContext):
    await state.update_data(scam_experience=message.text)
    await message.answer("2) Сколько готовы уделять часов для работы в день?")
    await state.set_state(Form.waiting_for_hours)

# Получение ответа на второй вопрос
@dp.message(Form.waiting_for_hours)
async def process_hours(message: types.Message, state: FSMContext):
    data = await state.update_data(hours=message.text)
    await state.clear()
    
    # Сохраняем данные пользователя
    user_data[message.from_user.id] = {
        'username': message.from_user.username,
        'first_name': message.from_user.first_name,
        'last_name': message.from_user.last_name,
        'answers': data,
        'status': 'pending'  # статус заявки
    }
    
    # Сохраняем в файл
    save_data()
    
    # Отправляем админу
    await send_to_admin(message.from_user)
    
    await message.answer("✅ Ваша анкета отправлена на рассмотрение. Ожидайте ответа.")

# Отправка заявки админу
async def send_to_admin(user: types.User):
    user_info = user_data[user.id]
    
    text = (
        f"📝 Новая заявка!\n\n"
        f"👤 Пользователь: @{user.username or 'нет username'}\n"
        f"Имя: {user.first_name or ''} {user.last_name or ''}\n"
        f"ID: {user.id}\n\n"
        f"1️⃣ Опыт в скаме:\n{user_info['answers']['scam_experience']}\n\n"
        f"2️⃣ Часов в день:\n{user_info['answers']['hours']}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_{user.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user.id}")
        ]
    ])
    
    await bot.send_message(ADMIN_ID, text, reply_markup=keyboard)

# Обработка действий админа
@dp.callback_query(F.data.startswith("accept_") | F.data.startswith("reject_"))
async def process_admin_decision(callback: types.CallbackQuery):
    action, user_id_str = callback.data.split("_")
    user_id = int(user_id_str)
    
    # Проверяем наличие пользователя
    user_found = False
    for uid in [user_id, str(user_id)]:
        if uid in user_data:
            user_found = True
            user_id_key = uid
            break
    
    if not user_found:
        await callback.answer("Пользователь не найден!", show_alert=True)
        return
    
    if action == "accept":
        # Добавляем в одобренных
        approved_users.add(user_id)
        user_data[user_id]['status'] = 'approved'
        
        # Сохраняем данные
        save_data()
        
        # Отправляем пользователю
        try:
            await bot.send_message(
                user_id,
                "✅ Ваша заявка одобрена! Нажмите /start чтобы продолжить."
            )
        except:
            pass
        
        # Редактируем сообщение админу
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Заявка одобрена {user_id}!"
        )
        
        # Удаляем кнопки
        await callback.message.edit_reply_markup(reply_markup=None)
        
    else:
        # Удаляем данные пользователя
        if user_id in user_data:
            user_data.pop(user_id, None)
        if str(user_id) in user_data:
            user_data.pop(str(user_id), None)
        
        # Удаляем из одобренных если там был
        if user_id in approved_users:
            approved_users.remove(user_id)
        
        # Сохраняем данные
        save_data()
        
        try:
            await bot.send_message(
                user_id,
                "❌ Ваша заявка отклонена."
            )
        except:
            pass
        
        # Редактируем сообщение админу
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ Заявка отклонена {user_id}!"
        )
        
        # Удаляем кнопки
        await callback.message.edit_reply_markup(reply_markup=None)
    
    await callback.answer()

# Подтверждение прочтения мануала
@dp.callback_query(F.data == "read_manual")
async def manual_read(callback: types.CallbackQuery):
    text = (
        "🔗 Ссылка на вступление: https://t.me/+84ibjuCC96NjZjc0\n\n"
        "💡 Помните: главное не опускать руки, на этом люди делают спокойно 50$ в день\n\n"
        "📞 По всем вопросам: @zit_z"
    )
    
    await callback.message.edit_text(text)
    await callback.answer()

# Команда для админа - просмотр всех заявок
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав доступа к этой команде.")
        return
    
    # Перезагружаем данные на случай изменений
    data = load_data()
    global user_data, approved_users
    user_data = {int(k): v for k, v in data.get('user_data', {}).items()}
    approved_users = set(data.get('approved_users', []))
    
    pending_count = len([uid for uid, data in user_data.items() if data.get('status') == 'pending'])
    approved_count = len([uid for uid, data in user_data.items() if data.get('status') == 'approved'])
    
    text = (
        f"📊 Панель администратора\n\n"
        f"👥 Всего пользователей: {len(user_data)}\n"
        f"⏳ Ожидают рассмотрения: {pending_count}\n"
        f"✅ Одобрено: {approved_count}\n\n"
        f"Используйте /stats для подробной статистики\n"
        f"Используйте /clean для очистки старых данных"
    )
    
    await message.answer(text)

# Команда для админа - статистика
@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав доступа к этой команде.")
        return
    
    if not user_data:
        await message.answer("Нет данных о пользователях.")
        return
    
    text = "📈 Статистика пользователей:\n\n"
    
    for user_id, data in user_data.items():
        status_emoji = "✅" if data.get('status') == 'approved' else "⏳"
        status_text = "одобрен" if data.get('status') == 'approved' else "ожидает"
        text += (
            f"{status_emoji} @{data.get('username', 'нет username')} "
            f"(ID: {user_id}) - {status_text}\n"
        )
    
    # Разбиваем на части если сообщение слишком длинное
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)

# Команда для очистки данных
@dp.message(Command("clean"))
async def clean_data(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав доступа к этой команде.")
        return
    
    # Сохраняем резервную копию
    backup_data = {'user_data': user_data.copy(), 'approved_users': list(approved_users)}
    with open('bot_data_backup.json', 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    # Очищаем только отклоненные заявки
    users_to_remove = []
    for user_id, data in user_data.items():
        if data.get('status') == 'pending':
            users_to_remove.append(user_id)
    
    for user_id in users_to_remove:
        user_data.pop(user_id, None)
    
    save_data()
    
    await message.answer(f"✅ Очищено {len(users_to_remove)} старых заявок. Резервная копия сохранена.")

# Запуск бота
async def main():
    print("=" * 50)
    print("Бот запущен!")
    print(f"Токен: {API_TOKEN[:10]}...")
    print(f"ID администратора: {ADMIN_ID}")
    print(f"Всего пользователей в базе: {len(user_data)}")
    print(f"Одобренных пользователей: {len(approved_users)}")
    print("=" * 50)
    print("Для остановки бота нажмите Ctrl+C")
    
    try:
        await dp.start_polling(bot)
    finally:
        # Сохраняем данные при завершении
        save_data()
        print("\nДанные сохранены в файл.")

if __name__ == "__main__":
    asyncio.run(main())
