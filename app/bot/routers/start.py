from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()

MENU_KB = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text="ℹ️ Что я умею", callback_data="help")]]
)

WELCOME = (
    "👋 Я — <b>нейроконсьерж</b> вашего дома.\n\n"
    "Напишите или надиктуйте голосом, что нужно сделать, — я разберу "
    "сообщение на атомарные задачи и передам в работу службам комплекса.\n\n"
    "Можно одним сообщением сразу несколько поручений: я сам разложу."
)

HELP_TEXT = (
    "<b>Как работает:</b>\n"
    "1. Шлёте текст или голосовое с тем, что нужно сделать.\n"
    "2. Я расшифровываю голос и разбираю смысл.\n"
    "3. Возвращаю структурированный список задач.\n\n"
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
