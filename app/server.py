import os, json, sqlite3, asyncio, base64
from pathlib import Path
from contextlib import suppress
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE.parent / ".env")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

app = FastAPI(title="Божья Благодать — Домашние церкви")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

groups = json.loads((BASE / "groups.json").read_text(encoding="utf-8"))
DB = BASE.parent / "applications.db"

bot: Bot | None = None
dp: Dispatcher | None = None
polling_task: asyncio.Task | None = None


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS applications(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      group_id TEXT NOT NULL,
      name TEXT NOT NULL,
      telegram TEXT,
      comment TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    con.commit()
    con.close()


init_db()


class Application(BaseModel):
    group_id: str
    name: str
    telegram: str = ""
    comment: str = ""


async def start_handler(message: Message):
    if not WEBAPP_URL:
        await message.answer("Mini App пока не настроен. Попробуйте чуть позже.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔥 Найти домашнюю церковь",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    ]])

    await message.answer(
        "Добро пожаловать в «Божью Благодать»!\n\n"
        "Домашняя церковь — это место общения, духовного роста, ученичества и служения.\n\n"
        "Нажмите кнопку ниже, чтобы найти подходящую домашнюю церковь.",
        reply_markup=kb,
    )


@app.on_event("startup")
async def startup_bot():
    global bot, dp, polling_task

    if not TOKEN:
        print("BOT_TOKEN не задан — Telegram polling не запущен")
        return

    bot = Bot(TOKEN)
    dp = Dispatcher()
    dp.message.register(start_handler, CommandStart())
    polling_task = asyncio.create_task(dp.start_polling(bot))
    print("Telegram bot polling started")


@app.on_event("shutdown")
async def shutdown_bot():
    global polling_task, bot

    if polling_task:
        polling_task.cancel()
        with suppress(asyncio.CancelledError):
            await polling_task

    if bot:
        await bot.session.close()


@app.get("/")
def index():
    html = (BASE / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace(
        '<img id="aboutHeroImg" alt="Что такое домашняя церковь">',
        '<img id="aboutHeroImg" src="/about-hero.jpg?v=2" alt="Что такое домашняя церковь">'
    )
    old_loader = "fetch('/static/assets/about_hero_exact.b64?v=1',{cache:'no-store'}).then(r=>r.text()).then(s=>{const el=document.getElementById('aboutHeroImg');if(el)el.src='data:image/jpeg;base64,'+s.trim()});"
    html = html.replace(old_loader, "")
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/about-hero.jpg")
def about_hero():
    b64_path = BASE / "static" / "assets" / "about_hero_exact.b64"
    try:
        encoded = "".join(b64_path.read_text(encoding="utf-8").split())
        image = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(500, f"About hero image error: {exc}")
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/groups")
def api_groups():
    public = []
    for g in groups:
        x = dict(g)
        x["public_address"] = g["district"] + " район"
        public.append(x)
    return public


@app.get("/api/groups/{group_id}")
def api_group(group_id: str):
    for g in groups:
        if g["id"] == group_id:
            return g
    raise HTTPException(404, "Group not found")


@app.post("/api/applications")
async def api_application(data: Application):
    if not data.name.strip():
        raise HTTPException(400, "Введите имя")

    group = next((g for g in groups if g["id"] == data.group_id), None)
    if not group:
        raise HTTPException(404, "Group not found")

    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO applications(group_id,name,telegram,comment) VALUES(?,?,?,?)",
        (data.group_id, data.name.strip(), data.telegram.strip(), data.comment.strip()),
    )
    con.commit()
    con.close()

    admin = os.getenv("ADMIN_CHAT_ID", "").strip()
    if bot and admin:
        try:
            text = (
                f"🔥 Новая заявка в домашнюю церковь\n\n"
                f"Группа: {group['name']}\nЛидеры: {group['leaders']}\n"
                f"Имя: {data.name}\nTelegram: {data.telegram or '—'}\n"
                f"Комментарий: {data.comment or '—'}"
            )
            await bot.send_message(admin, text)
        except Exception as exc:
            print(f"Не удалось отправить заявку администратору: {exc}")

    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "bot": bool(bot and polling_task and not polling_task.done())}
