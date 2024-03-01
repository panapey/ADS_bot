import json
import sqlite3
from datetime import datetime

import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

with open('DOS.json') as f:
    data = json.load(f)

organizations = [item['Org'] for item in data]

org_addresses = {item['Org']: item['Adress'] for item in data}

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
    photo VARCHAR(255),
    status VARCHAR(255),
    comment TEXT,
    message_id INT,
    registered_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    accepted_time DATETIME,
    appealed_time DATETIME,
    completed_time DATETIME
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
buttons = ["Просмотреть новые заявки", "Просмотреть выполненные", "Просмотреть в процессе", "Обжалованные",
           "Изменить статус заявки"]
admin_keyboard.add(*buttons)

superadmin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Регистрация админов", "Разжалование админов"]
superadmin_keyboard.add(*buttons)

inline_kb_full = InlineKeyboardMarkup(row_width=2)

for org in organizations:
    org_data = org.encode('utf-8')[:64].decode('utf-8', 'ignore')
    inline_kb_full.add(InlineKeyboardButton(org, callback_data=f'org:{org_data}'))


class Form(StatesGroup):
    full_name = State()
    city = State()
    organization = State()


class EditProfileForm(StatesGroup):
    choice = State()
    full_name = State()
    organization = State()
    confirm = State()


class EditRequestForm(StatesGroup):
    choice = State()
    subject = State()
    text = State()
    confirm = State()


class AdminForm(StatesGroup):
    request_id = State()
    new_status = State()
    photo = State()
    confirm = State()


class RequestStatus(StatesGroup):
    waiting_for_status = State()


class RequestForm(StatesGroup):
    subject = State()
    text = State()
    ask_photo = State()
    photo = State()
    confirm = State()


class AppealForm(StatesGroup):
    comment = State()


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
        result = cursor.fetchone()
        if result is not None:
            role = result[0]
            return role == 'admin'
        else:
            return False


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
    await message.answer("Пожалуйста, выберите организацию из списка.", reply_markup=inline_kb_full)

    await Form.organization.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=Form.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
        data['city'] = org_addresses[org]
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
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text
    await message.answer("Вы хотите прикрепить фотографию к заявке?",
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=[
                                 [InlineKeyboardButton(text="Да", callback_data="yes"),
                                  InlineKeyboardButton(text="Нет", callback_data="no")]
                             ]
                         ))
    await RequestForm.ask_photo.set()


@dp.message_handler(state=RequestForm.text)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['text'] = message.text
    await message.answer("Пожалуйста, прикрепите фотографию к заявке.")
    await RequestForm.photo.set()


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=RequestForm.ask_photo)
async def process_ask_photo(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, прикрепите фотографию.")
        await RequestForm.photo.set()
    else:
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id,
                               "Ваша заявка готова к отправке. Вы хотите отправить ее сейчас?",
                               reply_markup=InlineKeyboardMarkup(
                                   inline_keyboard=[
                                       [InlineKeyboardButton(text="Да", callback_data="yes"),
                                        InlineKeyboardButton(text="Нет", callback_data="no")]
                                   ]
                               ))
        await RequestForm.confirm.set()


@dp.message_handler(state=RequestForm.photo, content_types=types.ContentType.PHOTO)
async def process_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['photo'] = message.photo[-1].file_id
    await message.answer("Вы хотите сохранить эти изменения?",
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=[
                                 [InlineKeyboardButton(text="Да", callback_data="yes"),
                                  InlineKeyboardButton(text="Нет", callback_data="no")]
                             ]
                         ))
    await RequestForm.confirm.set()


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=RequestForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        user_id = callback_query.from_user.id
        async with state.proxy() as data:
            subject = data['subject']
            text = data['text']
            photo = data.get('photo')

        cursor.execute('INSERT INTO requests (user_id, subject, text, photo, status) VALUES (?, ?, ?, ?, ?)',
                       (user_id, subject, text, photo,
                        'Зарегистрирована'))
        conn.commit()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        cursor.execute('SELECT * FROM requests WHERE subject = ?', (subject,))
        requests = cursor.fetchone()

        chat_id = CHAT_ID
        if photo is not None:
            sent_message = await bot.send_photo(chat_id, photo,
                                                caption=f"Новая заявка от {user[5]}\nНомер заявки: {requests[0]} \n"
                                                        f"Подразделение: {user[4]}\nАдрес: {user[3]}\n"
                                                        f"Тема: {subject}\nТекст: {text}\n"
                                                        f"Статус: {requests[5]} 📝\n"
                                                        f"Дата и время заявки: {requests[8]}")
            cursor.execute('UPDATE requests SET message_id = ? WHERE id = ?',
                           (sent_message.message_id, requests[0]))
            conn.commit()
        else:
            sent_message = await bot.send_message(chat_id,
                                                  f"Новая заявка от {user[5]}:\nНомер заявки: {requests[0]} \n"
                                                  f"Подразделение: {user[4]}\nАдрес: {user[3]}\n"
                                                  f"Тема: {subject}\nТекст: {text}\n"
                                                  f"Статус: {requests[5]} 📝\nДата и время заявки: {requests[8]}")
            cursor.execute('UPDATE requests SET message_id = ? WHERE id = ?',
                           (sent_message.message_id, requests[0]))
            conn.commit()
        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id,
                               f"Ваша заявка №{requests[0]} \' {subject}\' успешно создана и зарегистрирована",
                               reply_markup=keyboard)
    else:
        await bot.send_message(callback_query.from_user.id, "Ваша заявка не была отправлена.", reply_markup=keyboard)

    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    await state.finish()


@dp.message_handler(lambda message: message.text == 'Проверить статус')
async def check_status(message: types.Message):
    user_id = message.from_user.id

    await bot.send_message(
        user_id,
        "Выберите категорию заявки:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Зарегистрированные", callback_data="check_status:registered")],
                [InlineKeyboardButton(text="Принятые в работу и обжалованные",
                                      callback_data="check_status:in_progress")],
                [InlineKeyboardButton(text="Выполненные", callback_data="check_status:completed")]
            ]
        )
    )


@dp.callback_query_handler(lambda c: c.data.startswith('check_status:'), state='*')
async def process_check_status(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    status = callback_query.data.split(':')[1]

    if status == 'registered':
        cursor.execute('SELECT * FROM requests WHERE user_id = ? and status = ?', (user_id, "Зарегистрирована"))
    elif status == 'in_progress':
        cursor.execute('SELECT * FROM requests WHERE user_id = ? and status in (?, ?)',
                       (user_id, "Принята в работу", "Обжалована"))
    elif status == 'completed':
        cursor.execute('SELECT * FROM requests WHERE user_id = ? and status = ?', (user_id, "Выполнена"))

    requests = cursor.fetchall()

    if not requests:
        await bot.send_message(user_id, "У вас нет заявок в этой категории.")
    else:
        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()

            if status == 'registered':
                await bot.send_message(
                    user_id,
                    f"Заявка {request[0]}:\nПодразделение: {user[4]}\nАдрес: {user[3]}\nФИО: {user[5]}\n"
                    f"Тема: {request[2]}\n"
                    f"Текст: {request[3]}\nСтатус: {request[5]}",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="Редактировать заявку",
                                                  callback_data=f"edit_request:{request[0]}")]
                        ]
                    )
                )
            else:
                await bot.send_message(
                    user_id,
                    f"Заявка {request[0]}:\nПодразделение: {user[4]}\nАдрес: {user[3]}\nФИО: {user[5]}\n"
                    f"Тема: {request[2]}\n"
                    f"Текст: {request[3]}\nСтатус: {request[5]}"
                )
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
    await bot.answer_callback_query(callback_query.id)


@dp.callback_query_handler(lambda c: c.data.startswith('edit_request:'))
async def start_editing_request(callback_query: types.CallbackQuery):
    request_id = callback_query.data.split(':')[1]
    await bot.answer_callback_query(callback_query.id)
    state = dp.current_state(user=callback_query.from_user.id)
    await state.update_data(request_id=request_id)
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Редактировать тему", callback_data="edit_subject"))
    keyboard.add(InlineKeyboardButton("Редактировать текст", callback_data="edit_text"))
    await bot.send_message(callback_query.from_user.id, "Что вы хотите редактировать?", reply_markup=keyboard)
    await EditRequestForm.choice.set()


@dp.callback_query_handler(lambda c: c.data in ['edit_subject', 'edit_text'], state=EditRequestForm.choice)
async def process_edit_choice(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'edit_subject':
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите новую тему заявки.")
        await EditRequestForm.subject.set()
    else:
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите новый текст заявки.")
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


@dp.message_handler(state=EditRequestForm.subject)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['subject'] = message.text
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
            print(data)
            request_id = data['request_id']
            subject = data.get('subject')
            text = data.get('text')

            if subject is not None:
                cursor.execute('UPDATE requests SET subject = ? WHERE id = ?', (subject, request_id))

            if text is not None:
                cursor.execute('UPDATE requests SET text = ? WHERE id = ?', (text, request_id))

            conn.commit()

        cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
        request = cursor.fetchone()

        user_id = callback_query.from_user.id
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

        await bot.edit_message_text(chat_id=CHAT_ID, message_id=request[7],
                                    text=f"Обновленная заявка от {user[5]}:\nНомер заявки: {request_id} \n"
                                         f"Подразделение: {user[4]}\nТема: {request[2]}\nТекст: {request[3]}"
                                         f"\nСтатус: {request[5]}")

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
        await bot.send_message(user_id, f"Ваши данные:\n\nФИО: {user[5]}\nАдрес: {user[3]}\nОрганизация: {user[4]}",
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
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Редактировать ФИО", callback_data="edit_full_name"))
    keyboard.add(InlineKeyboardButton("Редактировать организацию", callback_data="edit_organization"))
    await bot.send_message(callback_query.from_user.id, "Что вы хотите редактировать?", reply_markup=keyboard)
    await EditProfileForm.choice.set()


@dp.callback_query_handler(lambda c: c.data in ['edit_full_name', 'edit_organization'], state=EditProfileForm.choice)
async def process_edit_choice(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'edit_full_name':
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, введите ваше полное имя.")
        await EditProfileForm.full_name.set()
    else:
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, выберите организацию из списка.",
                               reply_markup=inline_kb_full)
        await EditProfileForm.organization.set()


@dp.message_handler(state=EditProfileForm.full_name)
async def process_text(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['full_name'] = message.text
    await message.answer("Вы хотите сохранить эти изменения?",
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=[
                                 [InlineKeyboardButton(text="Да", callback_data="yes"),
                                  InlineKeyboardButton(text="Нет", callback_data="no")]
                             ]
                         ))

    await EditProfileForm.confirm.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('org:'), state=EditProfileForm.organization)
async def process_callback_org(callback_query: types.CallbackQuery, state: FSMContext):
    org = callback_query.data.split(':')[1]
    async with state.proxy() as data:
        data['organization'] = org
        data['city'] = org_addresses[org]
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f'Вы выбрали организацию {org}')

    await bot.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id)

    await EditProfileForm.confirm.set()
    await bot.send_message(callback_query.from_user.id, "Вы хотите сохранить эти изменения?",
                           reply_markup=InlineKeyboardMarkup(
                               inline_keyboard=[
                                   [InlineKeyboardButton(text="Да", callback_data="yes"),
                                    InlineKeyboardButton(text="Нет", callback_data="no")]
                               ]
                           ))


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=EditProfileForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username
        async with state.proxy() as data:
            full_name = data.get('full_name')
            city = data.get('city')
            org = data.get('organization')

            if full_name is not None:
                cursor.execute(
                    'UPDATE users SET full_name = ? WHERE id = ?',
                    (full_name, user_id))
                conn.commit()

            if city is not None and org is not None:
                cursor.execute(
                    'UPDATE users SET city = ?, organization = ? WHERE id = ?',
                    (city, org, user_id))
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


@dp.message_handler(lambda message: message.text == 'Просмотреть новые заявки', is_admin=True)
async def view_all_requests(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests WHERE status = ?', ('Зарегистрирована',))
        requests = cursor.fetchall()
        print(requests)
        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
            user = cursor.fetchone()
            photo = request[4]
            if photo is not None:
                await bot.send_photo(message.from_user.id, photo,
                                     caption=f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}"
                                             f"\nАдрес: {user[3]}\n"
                                             f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[5]}"
                                             f"\nДата и время заявки: {request[8]}")
            else:
                await bot.send_message(message.from_user.id,
                                       f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}"
                                       f"\nАдрес: {user[3]}\n"
                                       f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[5]}"
                                       f"\nДата и время заявки: {request[8]}")
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
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}"
                                   f"\nАдрес: {user[3]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[5]}"
                                   f"\nДата и время заявки: {request[11]}")
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
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}"
                                   f"\nАдрес: {user[3]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[5]}"
                                   f"\nДата и время заявки: {request[9]}")
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.message_handler(lambda message: message.text == 'Обжалованные', is_admin=True)
async def view_in_progress_requests(message: types.Message):
    user_id = message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('SELECT * FROM requests WHERE status = ?', ('Обжалована',))
        requests = cursor.fetchall()
        print(requests)
        for request in requests:
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
            user = cursor.fetchone()
            await bot.send_message(message.from_user.id,
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nОрганизация: {user[4]}"
                                   f"\nАдрес: {user[3]}\n"
                                   f"Тема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[5]}"
                                   f"\nДата и время заявки: {request[10]}"
                                   f"\nКомментарий: {request[6]}")
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
                                   f"Заявка {request[0]}:\nСоздатель: {user[5]}\nТема: {request[2]}"
                                   f"\nТекст: {request[3]}\nАдрес: {user[3]}\n"
                                   f"Статус: {request[5]}",
                                   reply_markup=keyboard)
    else:
        await message.answer("Вы не являетесь администратором!")


@dp.callback_query_handler(lambda c: c.data.startswith('accept_'), state='*')
async def process_callback_accept(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]
    admin_id = callback_query.from_user.id

    cursor.execute('UPDATE requests SET status = ?, accepted_time = ? WHERE id = ?',
                   ('Принята в работу', datetime.now(), request_id))
    conn.commit()

    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()
    cursor.execute('SELECT * FROM users WHERE id = ?', (admin_id,))
    admin = cursor.fetchone()
    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
    user = cursor.fetchone()

    if admin[2] == 'admin':
        await bot.send_message(request[1],
                               f"Ваша заявка {request_id} была принята к исполнению администратором {admin[5]}."
                               f"\nВремя принятия заявки: {request[9]}")
        await bot.edit_message_text(chat_id=CHAT_ID, message_id=request[7],
                                    text=f"Администратор {admin[5]} обновил статус заявки\nот {user[5]}"
                                         f"\nНомер заявки: {request_id}\n"
                                         f"Подразделение: {user[4]}\nТема: {request[2]}\nТекст: {request[3]}"
                                         f"\nСтатус: {request[5]} 🛠️\nВремя принятия: {request[9]}")

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Принята в работу'")


@dp.callback_query_handler(lambda c: c.data.startswith('appeal_'), state='*')
async def process_callback_appeal(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]
    async with state.proxy() as data:
        data['request_id'] = request_id
        data['callback_query'] = callback_query
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           f"Вы обжаловали выполнение заявки {request_id}. Пожалуйста, напишите комментарий.")
    await AppealForm.comment.set()


@dp.message_handler(state=AppealForm.comment)
async def process_comment(message: types.Message, state: FSMContext):
    comment = message.text
    async with state.proxy() as data:
        request_id = data['request_id']
        callback_query = data['callback_query']
    cursor.execute('UPDATE requests SET status = ?, comment = ?, appealed_time = ? WHERE id = ?',
                   ('Обжалована', comment, datetime.now(), request_id))
    conn.commit()
    await message.answer("Ваш комментарий был добавлен к обжалованию заявки. Статус заявки обновлен до 'Обжалована'.")
    await bot.send_message(callback_query.from_user.id, f"Комментарий к обжалованию заявки {request_id}: {comment}")
    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()

    cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
    user = cursor.fetchone()
    await bot.edit_message_text(chat_id=CHAT_ID, message_id=request[7],
                                text=f"Пользователь {user[5]}\nобжаловал выполнение заявки"
                                     f"\nНомер заявки: {request_id}\n"
                                     f"Подразделение: {user[4]}\nТема: {request[2]}\n"
                                     f"Текст: {request[3]}\nКомментарий: {comment}\n"
                                     f"Статус: {request[5]} ⚠️\nВремя обжалования: {request[10]}")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith('done_'), state='*')
async def process_callback_done(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]
    await state.update_data(request_id=request_id)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, прикрепите фотографию к заявке.")
    await AdminForm.photo.set()


@dp.message_handler(state=AdminForm.photo, content_types=types.ContentType.PHOTO)
async def process_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['photo'] = message.photo[-1].file_id
    await message.answer("Вы хотите сохранить эти изменения?",
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=[
                                 [InlineKeyboardButton(text="Да", callback_data="yes"),
                                  InlineKeyboardButton(text="Нет", callback_data="no")]
                             ]
                         ))
    await AdminForm.confirm.set()


@dp.callback_query_handler(lambda c: c.data in ['yes', 'no'], state=AdminForm.confirm)
async def process_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'yes':
        async with state.proxy() as data:
            request_id = data['request_id']
            photo = data['photo']

        cursor.execute('UPDATE requests SET status = ?, photo = ?, completed_time = ? WHERE id = ?',
                       ('Выполнена', photo, datetime.now(), request_id))
        conn.commit()

        cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
        request = cursor.fetchone()

        cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))
        user = cursor.fetchone()
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Принять выполнение", callback_data=f"acceptdone_{request_id}"))
        keyboard.add(InlineKeyboardButton("Обжаловать", callback_data=f"appeal_{request_id}"))

        await bot.send_photo(user[0], photo,
                             caption=f"Статус вашей заявки {request_id} обновлен до 'Выполнена'. Вы согласны с этим?",
                             reply_markup=keyboard)

        await bot.answer_callback_query(callback_query.id)
        await bot.send_message(callback_query.from_user.id, f"Статус заявки {request_id} обновлен до 'Выполнена'")
    else:
        await bot.send_message(callback_query.from_user.id, "Ваша заявка не была отправлена.")

    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)

    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith('acceptdone_'), state='*')
async def process_callback_accept_done(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]
    cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
    request = cursor.fetchone()
    print(request)
    if request is not None:
        user_id = request[1]
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user is not None:
            cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Выполнена', request_id))
            conn.commit()
            await bot.answer_callback_query(callback_query.id)
            await bot.send_message(callback_query.from_user.id, f"Вы приняли выполнение заявки {request_id}.")
            await bot.edit_message_text(chat_id=CHAT_ID, message_id=request[7],
                                        text=f"Пользователь {user[5]}\nпринял выполнение заявки"
                                             f"\nНомер заявки: {request_id}\n"
                                             f"Подразделение: {user[4]}\nТема: {request[2]}\nТекст: {request[3]}"
                                             f"\nСтатус: {request[5]} ✅\nВремя выполнения: {request[11]}")
        else:
            await bot.send_message(callback_query.from_user.id, "Пользователь не найден.")
    else:
        await bot.send_message(callback_query.from_user.id, "Заявка не найдена.")


@dp.callback_query_handler(lambda c: c.data.startswith('appeal_'), state='*')
async def process_callback_appeal(callback_query: types.CallbackQuery, state: FSMContext):
    request_id = callback_query.data.split('_')[1]

    cursor.execute('UPDATE requests SET status = ? WHERE id = ?', ('Обжалована', request_id))
    conn.commit()

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           f"Вы обжаловали выполнение заявки {request_id}. Статус заявки обновлен до 'Обжалована'.")


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


@dp.message_handler(lambda message: message.text == 'Разжалование админов', is_superadmin=True)
async def demote_admins(message: types.Message):
    cursor.execute('SELECT * FROM users WHERE role = ?', ('admin',))
    admins = cursor.fetchall()

    for admin in admins:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Разжаловать до пользователя", callback_data=f"demote_{admin[0]}"))
        await bot.send_message(message.from_user.id,
                               f"Администратор {admin[0]}:\nИмя: {admin[1]}",
                               reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('demote_'), state='*')
async def process_callback_demote(callback_query: types.CallbackQuery):
    admin_id = callback_query.data.split('_')[1]

    cursor.execute('UPDATE users SET role = ? WHERE id = ?', ('user', admin_id))
    conn.commit()

    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id,
                           f"Администратор с id {admin_id} теперь является обычным пользователем.")


if __name__ == '__main__':
    executor.start_polling(dp)
