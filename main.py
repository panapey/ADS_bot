import aiogram
import pyodbc
from aiogram import Bot, Dispatcher, types, filters
from aiogram import executor
from aiogram.types import ReplyKeyboardMarkup

conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};"
                      "SERVER=SERVER;"
                      "DATABASE=users;"
                      "Trusted_Connection=yes;")
cursor = conn.cursor()

ADMIN_ID = ADMIN_ID
token = 'TOKEN'
bot = Bot(token=token)
dp = Dispatcher(bot)

# Создаем клавиатуру
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
buttons = ["Создать заявку", "Проверить статус"]
keyboard.add(*buttons)


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверяем, зарегистрирован ли уже этот пользователь
    cursor.execute('SELECT * FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()

    # Если пользователь уже зарегистрирован, отправляем сообщение
    if user:
        await message.answer("Вы уже зарегистрированы!", reply_markup=keyboard)
    else:
        # Если пользователь не зарегистрирован, запрашиваем дополнительную информацию
        await message.answer("Пожалуйста, введите ваш город, организацию и ФИО, разделенные запятыми.")


@dp.message_handler(lambda message: ',' in message.text and len(message.text.split(',')) == 3)
async def register_user(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    city, organization, full_name = map(str.strip, message.text.split(','))

    # Регистрируем пользователя как обычного пользователя
    cursor.execute('INSERT INTO users (id, username, role, city, organization, full_name) VALUES (?, ?, ?, ?, ?, ?)',
                   (user_id, username, 'user', city, organization, full_name))
    conn.commit()

    await message.answer("Вы успешно зарегистрированы!", reply_markup=keyboard)


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
    await bot.send_message(chat_id,
                           f"Новая заявка от {user[5]}:\nНомер заявки: {requests[0]} \nПодразделение: {user[4]}\nТема: {subject}\nТекст: {text}")

    await message.answer("Ваша заявка успешно создана и отправлена в чат вашей организации!", reply_markup=keyboard)


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

            await message.answer(
                f"Заявка {request[0]}:\nПодразделение: {user[4]}\nФИО: {user[5]}\nТема: {request[2]}\nТекст: {request[3]}\nСтатус: {request[4]}")


class IsAdminFilter(aiogram.dispatcher.filters.BoundFilter):
    key = 'is_admin'

    def __init__(self, is_admin):
        self.is_admin = is_admin

    async def check(self, message: types.Message):
        return message.from_user.id == ADMIN_ID


# Регистрируем фильтр
dp.filters_factory.bind(IsAdminFilter)


@dp.message_handler(is_admin=True)
async def process_reply(message: types.Message):
    # Проверяем, является ли сообщение ответом на другое сообщение
    if message.reply_to_message is not None:
        # Проверяем, является ли сообщение ответом на сообщение бота
        if message.reply_to_message.from_user.id == bot.id:
            # Извлекаем id заявки из сообщения бота
            bot_message_text = message.reply_to_message.text
            request_id = bot_message_text.split()[
                8]  # Предполагается, что id заявки находится на третьем месте в сообщении

            # Извлекаем новый статус из ответа администратора
            new_status = message.text

            # Обновляем статус заявки в базе данных
            cursor.execute('UPDATE requests SET status = ? WHERE id = ?', (new_status, request_id))
            conn.commit()

            # Получаем информацию о заявке
            cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
            request = cursor.fetchone()

            # Получаем информацию о пользователе
            cursor.execute('SELECT * FROM users WHERE id = ?', (request[1],))  # request[1] содержит id пользователя
            user = cursor.fetchone()

            # Отправляем обновленный статус заявки пользователю
            await bot.send_message(user[0], f"Статус вашей заявки {request_id} обновлен до {new_status}")

            await message.answer(f"Статус заявки {request_id} обновлен до {new_status}")


if __name__ == '__main__':
    executor.start_polling(dp)
