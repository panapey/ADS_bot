import json
import sqlite3

import aiogram
from aiogram import Bot, Dispatcher, types, filters
from aiogram import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

# Считываем данные из файла JSON
with open('DOS.json') as f:
    data = json.load(f)

# Получаем список организаций
organizations = [item['Org'] for item in data]

# Создаем соединение с SQLite и курсор
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Создаем таблицу users, если она не существует
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
    id INT,
    username VARCHAR(255),
    role VARCHAR(255),
    city VARCHAR(255),
    organization VARCHAR(255),
    full_name VARCHAR(255)
);
''')

# Создаем таблицу requests, если она не существует
cursor.execute('''
    CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INT,
    subject VARCHAR(255),
    text TEXT,
    status VARCHAR(255),
    message_id INT
);
''')

ADMIN_ID = AdminId
CHAT_ID = ChatId
token = 'TOKEN'
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())

# Создаем клавиатуру
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Создать заявку", "Проверить статус", "Просмотреть профиль"]
keyboard.add(*buttons)

# Создаем клавиатуру администратора
admin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Просмотреть все заявки", "Просмотреть выполненные", "Просмотреть в процессе", "Изменить статус заявки",
           "Регистрация админов"]
admin_keyboard.add(*buttons)

# Функция для генерации списка категорий
# Создаем инлайн-клавиатуру
inline_kb_full = InlineKeyboardMarkup(row_width=2)
# Добавляем кнопки с организациями
for org in organizations:
    # Обрезаем данные до 64 байт
    org_data = org.encode('utf-8')[:64].decode('utf-8', 'ignore')
    inline_kb_full.add(InlineKeyboardButton(org, callback_data=f'org:{org_data}'))


class Form(StatesGroup):
    full_name = State()  # Введите ФИО
    city = State()  # Введите город
    organization = State()  # Выберите организацию


class EditForm(StatesGroup):
    full_name = State()  # Введите ФИО
    city = State()  # Введите город
    organization = State()  # Выберите организацию
    confirm = State()  # Подтвердите изменения


class EditRequestForm(StatesGroup):
    subject = State()  # Введите тему
    text = State()  # Введите текст
    confirm = State()  # Подтвердите изменения


class AdminForm(StatesGroup):
    request_id = State()  # состояние, когда администратор вводит id заявки
    new_status = State()


class IsAdminFilter(aiogram.dispatcher.filters.BoundFilter):
    key = 'is_admin'

    def __init__(self, is_admin):
        self.is_admin = is_admin

    async def check(self, message: types.Message):
        return message.from_user.id == ADMIN_ID


# Регистрируем фильтр
dp.filters_factory.bind(IsAdminFilter)


@dp.message_handler(commands='start')
async def start(message: types.Message):
    user_id = message.from_user.id

    # Проверяем, зарегистрирован ли уже этот пользователь
    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    # Если пользователь уже зарегистрирован, отправляем сообщение
    if user:
        await message.answer("Вы уже зарегистрированы!", reply_markup=keyboard)
    else:
        await message.answer("Пожалуйста, введите ваше полное имя.")

        # Переходим в следующее состояние
        await Form.full_name.set()


@dp.message_handler(state=Form.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['full_name'] = message.text
    await message.answer("Пожалуйста, введите ваш город.")

    # Переходим в следующее состояние
    await Form.city.set()


@dp.message_handler(state=Form.city)
async def process_city(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['city'] = message.text
    await message.answer("Пожалуйста, выберите организацию из списка.", reply_markup=inline_kb_full)

    # Переходим в следующее состояние
    await Form.organization.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=Form.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f'Вы выбрали организацию {org}')

    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id)

    # Регистрируем пользователя как обычного пользователя
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username
    async with state.proxy() as data:
        city = data['city']
        org = data['organization']
        full_name = data['full_name']
        cursor.execute(
            'INSERT INTO users (id, username, role, city, organization, full_name) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, username, 'user', city, org, full_name))
        conn.commit()

    await bot.send_message(callback_query.from_user.id, "Вы успешно зарегистрированы!", reply_markup=keyboard)

    # Завершаем процесс регистрации и выходим из FSM
    await state.finish()


# Создаем словарь для хранения временных данных
user_data = {}


@dp.message_handler(lambda message: message.text == 'Создать заявку')
async def request(message: types.Message):
    # Запрашиваем у пользователя тему и текст обращения
    await message.answer("Пожалуйста, введите тему и текст обращения, разделенные запятыми.")


@dp.message_handler(filters.Regexp(r'^[^,]+,[^,]+$'))
async def create_request(message: types.Message):
    user_id = message.from_user.id
    subject, text = map(str.strip, message.text.split(','))

    # Создаем новую заявку со статусом "Зарегистрирована"
    cursor.execute('INSERT INTO requests (user_id, subject, text, status) VALUES (?, ?, ?, ?)',
                   (user_id, subject, text, 'Зарегистрирована'))
    conn.commit()

    # Получаем информацию о пользователе
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    cursor.execute('SELECT * FROM requests WHERE subject = ?', (subject,))
    requests = cursor.fetchone()
    # Отправляем заявку в чат группы
    chat_id = CHAT_ID
    sent_message = await bot.send_message(chat_id,
                                          f"Новая заявка от {user[5]}:\nНомер заявки: {requests[0]} \nПодразделение: {user[4]}\n"
                                          f"Тема: {subject}\nТекст: {text}")

    # Сохраняем идентификатор сообщения в базе данных
    cursor.execute('UPDATE requests SET message_id = ? WHERE id = ?',
                   (sent_message.message_id, requests[0]))
    conn.commit()

    await message.answer("Ваша заявка успешно создана и зарегистрирована", reply_markup=keyboard)


@dp.message_handler(lambda message: message.text == 'Проверить статус')
async def check_status(message: types.Message):
    user_id = message.from_user.id

    # Получаем все заявки пользователя
    cursor.execute('SELECT * FROM requests WHERE user_id = ?', (user_id,))
    requests = cursor.fetchall()

    # Если у пользователя нет заявок, отправляем сообщение
    if not requests:
        await message.answer("У вас нет заявок.")
    else:
        # В противном случае, отправляем информацию о всех заявках
        for request in requests:
            print(request)  # Выводим данные заявки

            # Получаем информацию о пользователе
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            await bot.send_message(
                user_id,
                f"Заявка {request[0]}:\nПодразделение: {user[4]}\nФИО: {user[5]}\nТема: {request[2]}\n"
                f"Текст: {request[3]}\nСтатус: {request[4]}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Редактировать заявку", callback_data=f"edit_request:{request[0]}")]
                    ]
                ))


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('edit_request:'))
async def start_editing_request(callback_query: types.CallbackQuery):
    request_id = callback_query.data.split(':')[1]
    await bot.answer_callback_query(callback_query.id)
    state = dp.current_state(user=callback_query.from_user.id)
    await state.update_data(request_id=request_id)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите новую тему заявки.")

    # Переходим в следующее состояние
    await EditRequestForm.subject.set()


@dp.message_handler(state=EditRequestForm.subject)
async def process_subject(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['subject'] = message.text
    await message.answer("Пожалуйста, введите новый текст заявки.")

    # Переходим в следующее состояние
    await EditRequestForm.text.set()


@dp.message_handler(state=EditRequestForm.text)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text
    await message.answer("Вы хотите сохранить эти изменения?",
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=[
                                 [InlineKeyboardButton(text="Да", callback_data="yes"),
                                  InlineKeyboardButton(text="Нет", callback_data="no")]
                             ]
                         ))

    # Переходим в следующее состояние
    await EditRequestForm.confirm.set()


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=EditRequestForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        # Обновляем данные заявки
        async with state.proxy() as data:
            request_id = data['request_id']
            subject = data['subject']
            text = data['text']
            cursor.execute('UPDATE requests SET subject = ?, text = ? WHERE id = ?',
                           (subject, text, request_id))
            conn.commit()

        # Получаем идентификатор сообщения из базы данных
        cursor.execute('SELECT message_id FROM requests WHERE id = ?', (request_id,))
        message_id = cursor.fetchone()[0]

        user_id = callback_query.from_user.id
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

        # Редактируем сообщение в чате
        await bot.edit_message_text(chat_id=CHAT_ID, message_id=message_id,
                                    text=f"Обновленная заявка от {user[5]}:\nНомер заявки: {request_id} \nПодразделение: {user[4]}\n"
                                         f"Тема: {subject}\nТекст: {text}")

        await bot.send_message(callback_query.from_user.id, "Ваша заявка успешно обновлена!", reply_markup=keyboard)
    else:
        await bot.send_message(callback_query.from_user.id, "Ваша заявка не была изменена.", reply_markup=keyboard)

    # Удаляем сообщение с inline кнопками
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    # Завершаем процесс редактирования и выходим из FSM
    await state.finish()


@dp.message_handler(lambda message: message.text == 'Просмотреть профиль')
async def view_profile(message: types.Message):
    user_id = message.from_user.id

    # Получаем данные пользователя
    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        await bot.send_message(user_id, f"Ваши данные:\n\nФИО: {user[5]}\nГород: {user[3]}\nОрганизация: {user[4]}",
                               reply_markup=InlineKeyboardMarkup(
                                   inline_keyboard=[
                                       [InlineKeyboardButton(text="Редактировать профиль", callback_data="edit")]
                                   ]
                               ))
    else:
        await bot.send_message(user_id, "Вы не зарегистрированы!")


@dp.callback_query_handler(lambda c: c.data == 'edit')
async def start_editing(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите ваше полное имя.")

    # Переходим в следующее состояние
    await EditForm.full_name.set()


@dp.message_handler(state=EditForm.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['full_name'] = message.text
    await message.answer("Пожалуйста, введите ваш город.")

    # Переходим в следующее состояние
    await EditForm.city.set()


@dp.message_handler(state=EditForm.city)
async def process_city(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['city'] = message.text
    await message.answer("Пожалуйста, выберите организацию из списка.", reply_markup=inline_kb_full)

    # Переходим в следующее состояние
    await EditForm.organization.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=EditForm.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f'Вы выбрали организацию {org}')

    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id)

    # Переходим в следующее состояние
    await EditForm.confirm.set()
    await bot.send_message(callback_query.from_user.id, "Вы хотите сохранить эти изменения?",
                           reply_markup=InlineKeyboardMarkup(
                               inline_keyboard=[
                                   [InlineKeyboardButton(text="Да", callback_data="yes"),
                                    InlineKeyboardButton(text="Нет", callback_data="no")]
                               ]
                           ))


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=EditForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        # Обновляем данные пользователя
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        async with state.proxy() as data:
            city = data['city']
            org = data['organization']
            full_name = data['full_name']
            cursor.execute(
                'UPDATE users SET username = ?, role = ?, city = ?, organization = ?, full_name = ? WHERE id = ?',
                (username, 'user', city, org, full_name, user_id))
            conn.commit()

        await bot.send_message(callback_query.from_user.id, "Ваши данные успешно обновлены!", reply_markup=keyboard)
    else:
        await bot.send_message(callback_query.from_user.id, "Ваши данные не были изменены.", reply_markup=keyboard)

    # Удаляем сообщение с inline кнопками
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    # Завершаем процесс редактирования и выходим из FSM
    await state.finish()


@dp.message_handler(is_admin=True, commands='admin')
async def admin_start(message: types.Message):
    await message.answer("Добро пожаловать, администратор!", reply_markup=admin_keyboard)


@dp.message_handler(lambda message: message.text == 'Просмотреть все заявки', is_admin=True)
async def view_all_requests(message: types.Message):
    # Получаем все заявки
    cursor.execute('SELECT * FROM requests')
    requests = cursor.fetchall()

    # Выводим информацию о каждой заявке
    for request in requests:
        await bot.send_message(message.from_user.id,
                               f"Заявка {request[0]}:\nТема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")


@dp.message_handler(lambda message: message.text == 'Просмотреть выполненные', is_admin=True)
async def view_completed_requests(message: types.Message):
    # Получаем все выполненные заявки
    cursor.execute('SELECT * FROM requests WHERE status = ?', ('Выполнена',))
    requests = cursor.fetchall()

    # Выводим информацию о каждой заявке
    for request in requests:
        await bot.send_message(message.from_user.id,
                               f"Заявка {request[0]}:\nТема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")


@dp.message_handler(lambda message: message.text == 'Просмотреть в процессе', is_admin=True)
async def view_in_progress_requests(message: types.Message):
    # Получаем все заявки, которые в процессе
    cursor.execute('SELECT * FROM requests WHERE status = ?', ('В процессе',))
    requests = cursor.fetchall()

    # Выводим информацию о каждой заявке
    for request in requests:
        await bot.send_message(message.from_user.id,
                               f"Заявка {request[0]}:\nТема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")


class RequestStatus(StatesGroup):
    waiting_for_status = State()


@dp.message_handler(lambda message: message.text == 'Изменить статус заявки', is_admin=True)
async def change_request_status(message: types.Message):
    # Получаем все невыполненные заявки
    cursor.execute('SELECT * FROM requests WHERE status != ?', ('Выполнена',))
    requests = cursor.fetchall()

    # Выводим информацию о каждой заявке
    for request in requests:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Принята в работу", callback_data=f"accept_{request[0]}"))
        keyboard.add(InlineKeyboardButton("Выполнена", callback_data=f"done_{request[0]}"))
        await bot.send_message(message.from_user.id,
                               f"Заявка {request[0]}:\nТема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}",
                               reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('accept_'), state='*')
async def process_callback_accept(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлекаем id заявки из callback_data
    request_id = callback_query.data.split('_')[1]

    # Обновляем статус заявки в базе данных
    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Принята в работу', request_id))
    conn.commit()

    # Получаем информацию о заявке
    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()

    # Получаем информацию о пользователе
    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))  # request[1] содержит id пользователя
    user = cursor.fetchone()

    # Отправляем уведомление пользователю
    await bot.send_message(user[0], f"Статус вашей заявки {request_id} обновлен до 'Принята в работу'")

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Принята в работу'")


@dp.callback_query_handler(lambda c: c.data.startswith('done_'), state='*')
async def process_callback_done(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлекаем id заявки из callback_data
    request_id = callback_query.data.split('_')[1]

    # Обновляем статус заявки в базе данных
    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Выполнена', request_id))
    conn.commit()

    # Получаем информацию о заявке
    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()

    # Получаем информацию о пользователе
    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))  # request[1] содержит id пользователя
    user = cursor.fetchone()

    # Отправляем уведомление пользователю
    await bot.send_message(user[0], f"Статус вашей заявки {request_id} обновлен до 'Выполнена'")

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Выполнена'")


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@dp.message_handler(lambda message: message.text == 'Регистрация админов', is_admin=True)
async def register_admins(message: types.Message):
    # Получаем всех пользователей
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()

    # Выводим информацию о каждом пользователе
    for user in users:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Сделать администратором", callback_data=f"admin_{user[0]}"))
        await bot.send_message(message.from_user.id,
                               f"Пользователь {user[0]}:\nИмя: {user[1]}\nРоль: {user[2]}",
                               reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('admin_'), state='*')
async def process_callback_admin(callback_query: types.CallbackQuery, state: FSMContext):
    # Извлекаем id пользователя из callback_data
    user_id = callback_query.data.split('_')[1]

    # Обновляем роль пользователя в базе данных
    cursor.execute('UPDATE users SET role = ? WHERE id = ?', ('admin', user_id))
    conn.commit()

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Пользователь с id {user_id} теперь является администратором.")


if __name__ == '__main__':
    executor.start_polling(dp)
