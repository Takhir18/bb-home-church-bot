import os, asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
ACCESS_CODE = os.getenv("ACCESS_CODE", "bb-home-2026-invite")

dp = Dispatcher()


def get_start_payload(message: Message) -> str:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


@dp.message(CommandStart())
async def start(message: Message):
    payload = get_start_payload(message)

    if payload != ACCESS_CODE:
        await message.answer(
            "Доступ к приложению возможен только по приглашению.\n\n"
            "Откройте специальную ссылку или отсканируйте QR-код, выданный церковью."
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔥 Найти домашнюю церковь",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]])

    await message.answer(
        "Добро пожаловать в «Божью Благодать»!\n\n"
        "Домашняя церковь — это место общения, духовного роста, ученичества и служения.\n\n"
        "Нажмите кнопку ниже, чтобы найти подходящую домашнюю церковь.",
        reply_markup=kb
    )


async def main():
    if not TOKEN or not WEBAPP_URL:
        raise RuntimeError("Заполните BOT_TOKEN и WEBAPP_URL в .env")
    bot = Bot(TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
