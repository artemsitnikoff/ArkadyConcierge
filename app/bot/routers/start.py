from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()

MENU_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="ℹ️ Как работать", callback_data="help")]]
)

WELCOME = (
    "👋 Я — консьерж.\n\n"
    "Пришли мне задачу <b>текстом</b> или <b>голосовым</b> сообщением — "
    "я разберу её на составляющие и верну структурированный JSON, "
    "готовый для создания задач в разных системах."
)

HELP_TEXT = (
    "<b>Как работать:</b>\n"
    "1. Напиши задачу текстом или запиши голосовое прямо в чате.\n"
    "2. Я расшифрую голос (Gemini 2.5 Pro через OpenRouter).\n"
    "3. Отправлю текст в Claude (opus) с промптом разбивки.\n"
    "4. В ответ — JSON-файл с разложенными задачами.\n\n"
    "Команды: /start, /help"
)


@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    await message.answer(WELCOME, reply_markup=MENU_KB)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=MENU_KB)


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(HELP_TEXT, reply_markup=MENU_KB)
    await callback.answer()
