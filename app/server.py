import os, json, sqlite3, asyncio, base64, hashlib, hmac, time
from pathlib import Path
from contextlib import suppress
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
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
INVITE_CODE = os.getenv("INVITE_CODE", "bb-home-2026-invite").strip()

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
    con.execute("""CREATE TABLE IF NOT EXISTS authorized_users(
      user_id INTEGER PRIMARY KEY,
      authorized_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    con.commit()
    con.close()


init_db()


class Application(BaseModel):
    group_id: str
    name: str
    telegram: str = ""
    comment: str = ""


def authorize_user(user_id: int):
    con = sqlite3.connect(DB)
    con.execute("INSERT OR IGNORE INTO authorized_users(user_id) VALUES(?)", (user_id,))
    con.commit()
    con.close()


def is_authorized(user_id: int) -> bool:
    con = sqlite3.connect(DB)
    row = con.execute("SELECT 1 FROM authorized_users WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return bool(row)


def validate_telegram_init_data(init_data: str) -> dict:
    if not TOKEN or not init_data:
        raise HTTPException(401, "Откройте приложение через Telegram")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            raise ValueError("bad hash")
        auth_date = int(pairs.get("auth_date", "0"))
        if auth_date <= 0 or time.time() - auth_date > 86400:
            raise ValueError("expired")
        user = json.loads(pairs.get("user", "{}"))
        if not user.get("id"):
            raise ValueError("no user")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Недействительный доступ Telegram")


def require_user(request: Request) -> dict:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = validate_telegram_init_data(init_data)
    if not is_authorized(int(user["id"])):
        raise HTTPException(403, "Доступ только по приглашению")
    return user


async def start_handler(message: Message):
    if not WEBAPP_URL:
        await message.answer("Mini App пока не настроен. Попробуйте чуть позже.")
        return
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    if payload != INVITE_CODE:
        await message.answer("Доступ к приложению возможен только по пригласительной ссылке или QR-коду.")
        return
    if not message.from_user:
        await message.answer("Не удалось подтвердить пользователя Telegram.")
        return
    authorize_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥 Найти домашнюю церковь", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer(
        "Добро пожаловать в «Божью Благодать»!\n\nДоступ подтверждён. Нажмите кнопку ниже, чтобы открыть домашние церкви.",
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
        '<img id="aboutHeroImg" src="/static/assets/about_hero_HQ.jpg?v=5" alt="Что такое домашняя церковь">'
    )
    old_loader = "fetch('/static/assets/about_hero_exact.b64?v=1',{cache:'no-store'}).then(r=>r.text()).then(s=>{const el=document.getElementById('aboutHeroImg');if(el)el.src='data:image/jpeg;base64,'+s.trim()});"
    html = html.replace(old_loader, "")

    icon_style = """<style id=\"aboutIconStyle\">#about .value .i{width:54px;height:54px;border-radius:50%;background:linear-gradient(145deg,#1b120d,#120d0a);border:1px solid #6f3215;display:grid;place-items:center;flex:none;color:var(--orange);box-shadow:inset 0 0 0 1px rgba(255,90,10,.05),0 6px 18px rgba(255,90,10,.08)}#about .value .i svg{width:28px;height:28px;display:block;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}</style>"""
    html = html.replace("</head>", icon_style + "</head>")

    icons = {
        "🍽": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v7M4.5 3v5.5A2.5 2.5 0 0 0 7 11v10M9.5 3v5.5A2.5 2.5 0 0 1 7 11"/><path d="M15 3v8c0 1.7 1.3 3 3 3V3M18 14v7"/></svg>',
        "🙏": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 21c-1.5-3-2.5-5.2-2.5-7.2V8.5c0-1 .8-1.8 1.8-1.8.9 0 1.7.7 1.8 1.6V4.8c0-1 .8-1.8 1.8-1.8s1.8.8 1.8 1.8v3.4c.2-.8.9-1.4 1.8-1.4 1 0 1.8.8 1.8 1.8v4.8c0 3-1.2 5.4-3.2 7.6"/><path d="M7 13.5 4.8 11c-.6-.7-.5-1.8.2-2.4.7-.6 1.8-.5 2.4.2L10 12"/></svg>',
        "📖": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 5.5c3-1 5.5-.5 8 1.5v12c-2.5-2-5-2.5-8-1.5zM20.5 5.5c-3-1-5.5-.5-8 1.5v12c2.5-2 5-2.5 8-1.5z"/></svg>',
        "❤️": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.8a5.4 5.4 0 0 0-7.7 0L12 6l-1.1-1.2a5.4 5.4 0 1 0-7.7 7.6L12 21l8.8-8.6a5.4 5.4 0 0 0 0-7.6z"/></svg>',
        "🌍": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3.5 12h17M12 3c2.2 2.4 3.3 5.4 3.3 9S14.2 18.6 12 21c-2.2-2.4-3.3-5.4-3.3-9S9.8 5.4 12 3z"/></svg>'
    }
    for emoji, svg in icons.items():
        html = html.replace(f'<div class="i">{emoji}</div>', f'<div class="i">{svg}</div>')

    old_start = "const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand();}let groups=[],current=null,filter='all',stack=['home'];"
    new_start = "const tg=window.Telegram?.WebApp;const initData=tg?.initData||'';if(tg){tg.ready();tg.expand();}const authHeaders={'X-Telegram-Init-Data':initData};let groups=[],current=null,filter='all',stack=['home'];if(!initData){document.querySelector('.app').innerHTML='<div style=\"padding:60px 24px;text-align:center\"><h2>Доступ только через Telegram</h2><p style=\"color:#aaa;line-height:1.5\">Откройте приложение по пригласительной ссылке или QR-коду.</p></div>';throw new Error('Telegram access required');}"
    html = html.replace(old_start, new_start)
    html = html.replace("fetch('/api/groups',{cache:'no-store'})", "fetch('/api/groups',{cache:'no-store',headers:authHeaders})")
    html = html.replace("fetch('/api/groups/'+id,{cache:'no-store'})", "fetch('/api/groups/'+id,{cache:'no-store',headers:authHeaders})")
    html = html.replace("headers:{'Content-Type':'application/json'}", "headers:{'Content-Type':'application/json','X-Telegram-Init-Data':initData}")
    html = html.replace(
        "<div class=\"notice\">В целях приватности на общей странице показывается район. Точный адрес используется только для маршрута и организационной связи.</div>",
        "<div class=\"notice\" id=\"addressNotice\"></div>"
    )
    old_badges = "document.getElementById('dBadges').innerHTML=`<span class=\"badge\">📍 ${current.district}</span><span class=\"badge\">🕒 ${current.time}</span><span class=\"badge\">👥 ${current.members} участников</span><span class=\"badge\">Возраст ${current.age}</span><span class=\"badge\">🐾 ${current.pets}</span>`;"
    new_badges = "document.getElementById('dBadges').innerHTML=`<span class=\"badge\">📍 ${current.address}</span><span class=\"badge\">🕒 ${current.time}</span><span class=\"badge\">👥 ${current.members} участников</span><span class=\"badge\">Возраст ${current.age}</span><span class=\"badge\">🐾 ${current.pets}</span>`;document.getElementById('addressNotice').textContent='Точный адрес: '+current.address;"
    html = html.replace(old_badges, new_badges)
    return HTMLResponse(html, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/about-hero.jpg")
def about_hero():
    b64_path = BASE / "static" / "assets" / "about_hero_exact.b64"
    try:
        encoded = "".join(b64_path.read_text(encoding="utf-8").split())
        image = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise HTTPException(500, f"About hero image error: {exc}")
    return Response(content=image, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/groups")
def api_groups(request: Request):
    require_user(request)
    public = []
    for g in groups:
        x = dict(g)
        x["public_address"] = g["address"]
        public.append(x)
    return public


@app.get("/api/groups/{group_id}")
def api_group(group_id: str, request: Request):
    require_user(request)
    for g in groups:
        if g["id"] == group_id:
            return g
    raise HTTPException(404, "Group not found")


@app.post("/api/applications")
async def api_application(data: Application, request: Request):
    require_user(request)
    if not data.name.strip():
        raise HTTPException(400, "Введите имя")
    group = next((g for g in groups if g["id"] == data.group_id), None)
    if not group:
        raise HTTPException(404, "Group not found")
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO applications(group_id,name,telegram,comment) VALUES(?,?,?,?)", (data.group_id, data.name.strip(), data.telegram.strip(), data.comment.strip()))
    con.commit()
    con.close()
    admin = os.getenv("ADMIN_CHAT_ID", "").strip()
    if bot and admin:
        try:
            text = f"🔥 Новая заявка в домашнюю церковь\n\nГруппа: {group['name']}\nЛидеры: {group['leaders']}\nИмя: {data.name}\nTelegram: {data.telegram or '—'}\nКомментарий: {data.comment or '—'}"
            await bot.send_message(admin, text)
        except Exception as exc:
            print(f"Не удалось отправить заявку администратору: {exc}")
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "bot": bool(bot and polling_task and not polling_task.done())}
