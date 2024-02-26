import json
import sqlite3

import aiogram
from aiogram import Bot, Dispatcher, types, filters
from aiogram import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

with open('DOS.json') as f:
    data = json.load(f)

organizations = [item['Org'] for item in data]

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

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

user_data = {}

ADMIN_ID = ADMINID
CHAT_ID = CHATID
token = 'TOKEN'
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())

keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Создать заявку", "Проверить статус", "Просмотреть профиль"]
keyboard.add(*buttons)

admin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Просмотреть все заявки", "Просмотреть выполненные", "Просмотреть в процессе", "Изменить статус заявки"]
admin_keyboard.add(*buttons)

superadmin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Регистрация админов"]
superadmin_keyboard.add(*buttons)

inline_kb_full = InlineKeyboardMarkup(row_width=2)

for org in organizations:
    org_data = org.encode('utf-8')[:64].decode('utf-8', 'ignore')
    inline_kb_full.add(InlineKeyboardButton(org, callback_data=f'org:{org_data}'))


class Form(StatesGroup):
    full_name = State()
    city = State()
    organization = State()


class EditForm(StatesGroup):
    full_name = State()
    city = State()
    organization = State()
    confirm = State()


class EditRequestForm(StatesGroup):
    subject = State()
    text = State()
    confirm = State()


class AdminForm(StatesGroup):
    request_id = State()
    new_status = State()


class RequestStatus(StatesGroup):
    waiting_for_status = State()


class RequestForm(StatesGroup):
    subject = State()
    text = State()


class IsSuperAdminFilter(aiogram.dispatcher.filters.BoundFilter):
    key = 'is_superadmin'

    def __init__(self, is_superadmin):
        self.is_superadmin = is_superadmin

    async def check(self, message: types.Message):
        return message.from_user.id == ADMIN_ID


dp.filters_factory.bind(IsSuperAdminFilter)


class IsAdminFilter(aiogram.dispatcher.filters.BoundFilter):
    key = 'is_admin'

    def __init__(self, is_admin):
        self.is_admin = is_admin

    async def check(self, message: types.Message):
        user_id = message.from_user.id
        cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
        role = cursor.fetchone()[0]
        return role == 'admin'


dp.filters_factory.bind(IsAdminFilter)


@dp.message_handler(commands='start')
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        role = user[2]
        if role == 'admin':
            await message.answer("Добро пожаловать, администратор!", reply_markup=admin_keyboard)
        elif role == 'superadmin':
            await message.answer("Добро пожаловать, суперадминистратор!", reply_markup=superadmin_keyboard)
        else:
            await message.answer("Вы уже зарегистрированы!", reply_markup=keyboard)
    else:
        if user_id == ADMIN_ID:
            cursor.execute(
                'INSERT INTO users (id, username, role, city, organization, full_name) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, username, 'superadmin', 'none', 'none', 'none'))
            conn.commit()
            await message.answer("Вы успешно зарегистрированы как суперадминистратор!",
                                 reply_markup=superadmin_keyboard)
        else:
            await message.answer("Пожалуйста, введите ваше полное имя.")
            await Form.full_name.set()


@dp.message_handler(state=Form.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['full_name'] = message.text
    await message.answer("Пожалуйста, введите ваш город.")

    await Form.city.set()


@dp.message_handler(state=Form.city)
async def process_city(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['city'] = message.text
    await message.answer("Пожалуйста, выберите организацию из списка.", reply_markup=inline_kb_full)

    await Form.organization.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=Form.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f'Вы выбрали организацию {org}')

    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id)

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

    await state.finish()


@dp.message_handler(lambda message: message.text == 'Создать заявку')
async def request(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        await message.answer("Пожалуйста, введите тему обращения.")
        await RequestForm.subject.set()
    else:
        await message.answer("Вы не зарегистрированы!", reply_markup=keyboard)


@dp.message_handler(state=RequestForm.subject)
async def process_subject(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['subject'] = message.text
    await message.answer("Пожалуйста, введите текст обращения.")
    await RequestForm.text.set()


@dp.message_handler(state=RequestForm.text)
async def create_request(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with state.proxy() as data:
        subject = data['subject']
        text = message.text

    cursor.execute('INSERT INTO requests (user_id, subject, text, status) VALUES (?, ?, ?, ?)',
                   (user_id, subject, text, 'Зарегистрирована'))
    conn.commit()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    cursor.execute('SELECT * FROM requests WHERE subject = ?', (subject,))
    requests = cursor.fetchone()

    chat_id = CHAT_ID
    sent_message = await bot.send_message(chat_id,
                                          f"Новая заявка от {user[5]}:\nНомер заявки: {requests[0]} \n"
                                          f"Подразделение: {user[4]}\n"
                                          f"Тема: {subject}\nТекст: {text}")

    cursor.execute('UPDATE requests SET message_id = ? WHERE id = ?',
                   (sent_message.message_id, requests[0]))
    conn.commit()
    await message.answer(f"Ваша заявка №{requests[0]} \' {subject}\' успешно создана и зарегистрирована",
                         reply_markup=keyboard)
    await state.finish()


@dp.message_handler(filters.Regexp(r'^[^,]+,[^,]+$'))
async def create_request(message: types.Message):
    user_id = message.from_user.id
    subject, text = map(str.strip, message.text.split(','))

    cursor.execute('INSERT INTO requests (user_id, subject, text, status) VALUES (?, ?, ?, ?)',
                   (user_id, subject, text, 'Зарегистрирована'))
    conn.commit()

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    cursor.execute('SELECT * FROM requests WHERE subject = ?', (subject,))
    requests = cursor.fetchone()

    chat_id = CHAT_ID
    sent_message = await bot.send_message(chat_id,
                                          f"Новая заявка от {user[5]}:\nНомер заявки: {requests[0]} \n"
                                          f"Подразделение: {user[4]}\nТема: {subject}\nТекст: {text}")

    cursor.execute('UPDATE requests SET message_id = ? WHERE id = ?',
                   (sent_message.message_id, requests[0]))
    conn.commit()

    await message.answer("Ваша заявка успешно создана и зарегистрирована", reply_markup=keyboard)


@dp.message_handler(lambda message: message.text == 'Проверить статус')
async def check_status(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM requests WHERE user_id = ?', (user_id,))
    requests = cursor.fetchall()

    if not requests:
        await message.answer("У вас нет заявок.")
    else:

        for request in requests:
            print(request)

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

    await EditRequestForm.subject.set()


@dp.message_handler(state=EditRequestForm.subject)
async def process_subject(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['subject'] = message.text
    await message.answer("Пожалуйста, введите новый текст заявки.")

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

    await EditRequestForm.confirm.set()


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=EditRequestForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':

        async with state.proxy() as data:
            request_id = data['request_id']
            subject = data['subject']
            text = data['text']
            cursor.execute('UPDATE requests SET subject = ?, text = ? WHERE id = ?',
                           (subject, text, request_id))
            conn.commit()

        cursor.execute('SELECT message_id FROM requests WHERE id = ?', (request_id,))
        message_id = cursor.fetchone()[0]

        user_id = callback_query.from_user.id
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

        await bot.edit_message_text(chat_id=CHAT_ID, message_id=message_id,
                                    text=f"Обновленная заявка от {user[5]}:\nНомер заявки: {request_id} \n"
                                         f"Подразделение: {user[4]}\nТема: {subject}\nТекст: {text}")

        await bot.send_message(callback_query.from_user.id, "Ваша заявка успешно обновлена!", reply_markup=keyboard)
    else:
        await bot.send_message(callback_query.from_user.id, "Ваша заявка не была изменена.", reply_markup=keyboard)

    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    await state.finish()


@dp.message_handler(lambda message: message.text == 'Просмотреть профиль')
async def view_profile(message: types.Message):
    user_id = message.from_user.id

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

    await EditForm.full_name.set()


@dp.message_handler(state=EditForm.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['full_name'] = message.text
    await message.answer("Пожалуйста, введите ваш город.")

    await EditForm.city.set()


@dp.message_handler(state=EditForm.city)
async def process_city(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['city'] = message.text
    await message.answer("Пожалуйста, выберите организацию из списка.", reply_markup=inline_kb_full)

    await EditForm.organization.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=EditForm.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f'Вы выбрали организацию {org}')

    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id)

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

    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    await state.finish()


@dp.message_handler(is_admin=True, commands='admin')
async def admin_start(message: types.Message):
    await message.answer("Добро пожаловать, администратор!", reply_markup=admin_keyboard)


@dp.message_handler(is_superadmin=True, commands='super_admin')
async def admin_start(message: types.Message):
    await message.answer("Добро пожаловать, главный администратор!", reply_markup=superadmin_keyboard)


@dp.message_handler(lambda message: message.text == 'Просмотреть все заявки', is_admin=True)
async def view_all_requests(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests')
        requests = cursor.fetchall()

        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
            user = cursor.fetchone()
            await bot.send_message(message.from_user.id,
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.message_handler(lambda message: message.text == 'Просмотреть выполненные', is_admin=True)
async def view_completed_requests(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests WHERE status = ?', ('Выполнена',))
        requests = cursor.fetchall()

        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
            user = cursor.fetchone()
            await bot.send_message(message.from_user.id,
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.message_handler(lambda message: message.text == 'Просмотреть в процессе', is_admin=True)
async def view_in_progress_requests(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests WHERE status = ?', ('Принята в работу',))
        requests = cursor.fetchall()

        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
            user = cursor.fetchone()
            await bot.send_message(message.from_user.id,
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.message_handler(lambda message: message.text == 'Изменить статус заявки', is_admin=True)
async def change_request_status(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests WHERE status != ?', ('Выполнена',))
        requests = cursor.fetchall()

        for request in requests:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Принята в работу", callback_data=f"accept_{request[0]}"))
            keyboard.add(InlineKeyboardButton("Выполнена", callback_data=f"done_{request[0]}"))
            await bot.send_message(message.from_user.id,
                                   f"Заявка {request[0]}:\nТема: {request[2]}\nТекст: {request[3]}\n"
                                   f"Статус: {request[4]}",
                                   reply_markup=keyboard)
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.callback_query_handler(lambda c: c.data.startswith('accept_'), state='*')
async def process_callback_accept(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]

    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Принята в работу', request_id))
    conn.commit()

    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()

    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
    user = cursor.fetchone()

    await bot.send_message(user[0], f"Статус вашей заявки {request_id} обновлен до 'Принята в работу'")

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Принята в работу'")


@dp.callback_query_handler(lambda c: c.data.startswith('done_'), state='*')
async def process_callback_done(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]

    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Выполнена', request_id))
    conn.commit()

    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()

    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
    user = cursor.fetchone()

    await bot.send_message(user[0], f"Статус вашей заявки {request_id} обновлен до 'Выполнена'")

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Выполнена'")


@dp.message_handler(lambda message: message.text == 'Регистрация админов', is_superadmin=True)
async def register_admins(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        admins = ['admin', 'superadmin']
        for admin in admins:
            cursor.execute('SELECT * FROM users WHERE role !=?', (admin,))
            users = cursor.fetchall()

        for user in users:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Сделать администратором", callback_data=f"admin_{user[0]}"))
            await bot.send_message(message.from_user.id,
                                   f"Пользователь {user[0]}:\nИмя: {user[1]}\nРоль: {user[2]}",
                                   reply_markup=keyboard)
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.callback_query_handler(lambda c: c.data.startswith('admin_'), state='*')
async def process_callback_admin(callback_query: types.CallbackQuery):
    user_id = callback_query.data.split('_')[1]

    cursor.execute('UPDATE users SET role = ? WHERE id = ?', ('admin', user_id))
    conn.commit()

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Пользователь с id {user_id} теперь является администратором.")


if __name__ == '__main__':
    executor.start_polling(dp)
