import asyncio
import logging
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

# Хранение данных пользователей
user_data = {}
approved_users = set()  # Множество одобренных пользователей

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
    if message.from_user.id in user_data:
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
    if callback.from_user.id in approved_users:
        await callback.answer("Вы уже одобрены!", show_alert=True)
        return
    
    if callback.from_user.id in user_data:
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
    action, user_id = callback.data.split("_")
    user_id = int(user_id)
    
    if user_id not in user_data:
        await callback.answer("Пользователь не найден!", show_alert=True)
        return
    
    if action == "accept":
        # Добавляем в одобренных
        approved_users.add(user_id)
        user_data[user_id]['status'] = 'approved'
        
        # Отправляем пользователю
        await bot.send_message(
            user_id,
            "✅ Ваша заявка одобрена! Нажмите /start чтобы продолжить."
        )
        
        # Редактируем сообщение админу
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Заявка одобрена!"
        )
        
        # Удаляем кнопки
        await callback.message.edit_reply_markup(reply_markup=None)
        
    else:
        # Удаляем данные пользователя
        user_data.pop(user_id, None)
        
        await bot.send_message(
            user_id,
            "❌ Ваша заявка отклонена."
        )
        
        # Редактируем сообщение админу
        await callback.message.edit_text(
            callback.message.text + f"\n\n❌ Заявка отклонена!"
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
    
    pending_count = len([uid for uid, data in user_data.items() if data.get('status') == 'pending'])
    approved_count = len([uid for uid, data in user_data.items() if data.get('status') == 'approved'])
    
    text = (
        f"📊 Панель администратора\n\n"
        f"👥 Всего пользователей: {len(user_data)}\n"
        f"⏳ Ожидают рассмотрения: {pending_count}\n"
        f"✅ Одобрено: {approved_count}\n\n"
        f"Используйте /stats для подробной статистики"
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
        text += (
            f"{status_emoji} @{data['username'] or 'нет username'} "
            f"(ID: {user_id}) - {data.get('status', 'unknown')}\n"
        )
    
    await message.answer(text[:4000])  # Ограничение Telegram

# Запуск бота
async def main():
    print("Бот запущен! Проверьте работу в Telegram.")
    print(f"ID администратора: {ADMIN_ID}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
