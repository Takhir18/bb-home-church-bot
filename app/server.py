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
    con.execute("""CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id TEXT NOT NULL,name TEXT NOT NULL,telegram TEXT,comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS authorized_users(user_id INTEGER PRIMARY KEY,authorized_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit(); con.close()
init_db()

class Application(BaseModel):
    group_id: str
    name: str
    telegram: str = ""
    comment: str = ""

def authorize_user(user_id: int):
    con=sqlite3.connect(DB); con.execute("INSERT OR IGNORE INTO authorized_users(user_id) VALUES(?)",(user_id,)); con.commit(); con.close()

def is_authorized(user_id:int)->bool:
    con=sqlite3.connect(DB); row=con.execute("SELECT 1 FROM authorized_users WHERE user_id=?",(user_id,)).fetchone(); con.close(); return bool(row)

def validate_telegram_init_data(init_data:str)->dict:
    if not TOKEN or not init_data: raise HTTPException(401,"Откройте приложение через Telegram")
    try:
        pairs=dict(parse_qsl(init_data,keep_blank_values=True)); received_hash=pairs.pop("hash")
        data_check_string="\n".join(f"{k}={v}" for k,v in sorted(pairs.items()))
        secret_key=hmac.new(b"WebAppData",TOKEN.encode(),hashlib.sha256).digest()
        calculated_hash=hmac.new(secret_key,data_check_string.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash,received_hash): raise ValueError("bad hash")
        auth_date=int(pairs.get("auth_date","0"))
        if auth_date<=0 or time.time()-auth_date>86400: raise ValueError("expired")
        user=json.loads(pairs.get("user","{}"))
        if not user.get("id"): raise ValueError("no user")
        return user
    except HTTPException: raise
    except Exception: raise HTTPException(401,"Недействительный доступ Telegram")

def require_user(request:Request)->dict:
    user=validate_telegram_init_data(request.headers.get("X-Telegram-Init-Data",""))
    if not is_authorized(int(user["id"])): raise HTTPException(403,"Доступ только по приглашению")
    return user

async def start_handler(message:Message):
    if not WEBAPP_URL:
        await message.answer("Mini App пока не настроен. Попробуйте чуть позже."); return
    parts=(message.text or "").split(maxsplit=1); payload=parts[1].strip() if len(parts)>1 else ""
    if payload!=INVITE_CODE:
        await message.answer("Доступ к приложению возможен только по пригласительной ссылке или QR-коду."); return
    if not message.from_user:
        await message.answer("Не удалось подтвердить пользователя Telegram."); return
    authorize_user(message.from_user.id)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔥 Найти домашнюю церковь",web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("Добро пожаловать в «Божью Благодать»!\n\nДоступ подтверждён. Нажмите кнопку ниже, чтобы открыть домашние церкви.",reply_markup=kb)

@app.on_event("startup")
async def startup_bot():
    global bot,dp,polling_task
    if not TOKEN:
        print("BOT_TOKEN не задан — Telegram polling не запущен"); return
    bot=Bot(TOKEN); dp=Dispatcher(); dp.message.register(start_handler,CommandStart()); polling_task=asyncio.create_task(dp.start_polling(bot)); print("Telegram bot polling started")

@app.on_event("shutdown")
async def shutdown_bot():
    global polling_task,bot
    if polling_task:
        polling_task.cancel()
        with suppress(asyncio.CancelledError): await polling_task
    if bot: await bot.session.close()

@app.get("/")
def index():
    html=(BASE/"static"/"index.html").read_text(encoding="utf-8")
    html=html.replace('<img id="aboutHeroImg" alt="Что такое домашняя церковь">','<img id="aboutHeroImg" src="/static/assets/about_hero_HQ.jpg?v=6" alt="Что такое домашняя церковь">')
    old_loader="fetch('/static/assets/about_hero_exact.b64?v=1',{cache:'no-store'}).then(r=>r.text()).then(s=>{const el=document.getElementById('aboutHeroImg');if(el)el.src='data:image/jpeg;base64,'+s.trim()});"
    html=html.replace(old_loader,"")
    icon_style="""<style id="aboutIconStyle">#about .value .i{width:54px;height:54px;border-radius:50%;background:radial-gradient(circle at 35% 30%,#242424,#151515 68%);border:1px solid #292929;display:grid;place-items:center;flex:none;color:#ff5a0a;box-shadow:inset 0 1px 0 rgba(255,255,255,.025)}#about .value .i svg{width:31px;height:31px;display:block;fill:currentColor;stroke:none}</style>"""
    html=html.replace("</head>",icon_style+"</head>")
    icons={
      "🍽":'<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="8"/><rect x="3" y="7" width="2.5" height="19" rx="1.2"/><rect x="27" y="7" width="2.5" height="19" rx="1.2"/><rect x="2" y="7" width="1.5" height="8" rx=".7"/><rect x="5.5" y="7" width="1.5" height="8" rx=".7"/><path d="M26 7c-2 3-2 8 0 10h3V7z"/></svg>',
      "🙏":'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M14.4 3.5c1.2 0 1.8 1 1.6 2.2l-1.7 9.1 1.7 2.8 1.7-2.8L16 5.7c-.2-1.2.4-2.2 1.6-2.2 1 0 1.7.7 2 1.7l3 12.2 4.2 7.2c.8 1.4-.2 3.1-1.8 3.1h-5.2c-1 0-1.8-.5-2.2-1.4L16 22.8l-1.6 3.5c-.4.9-1.2 1.4-2.2 1.4H7c-1.6 0-2.6-1.7-1.8-3.1l4.2-7.2 3-12.2c.3-1 1-1.7 2-1.7z"/></svg>',
      "📖":'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 7.5c4.8-1.6 8.7-.8 12 2.2v16.1c-3.3-2.8-7.2-3.6-12-2V7.5zm26 0c-4.8-1.6-8.7-.8-12 2.2v16.1c3.3-2.8 7.2-3.6 12-2V7.5z"/></svg>',
      "❤️":'<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 28 4.5 16.8C-2 10.4 7.4.2 14 6.7L16 8.8l2-2.1c6.6-6.5 16 3.7 9.5 10.1L16 28z"/></svg>',
      "🌍":'<svg viewBox="0 0 32 32" aria-hidden="true" fill-rule="evenodd"><path d="M16 2a14 14 0 1 0 0 28 14 14 0 0 0 0-28zm-2.2 3.2c-1.4 2-2.4 4.6-2.7 7.3H6.2a10.8 10.8 0 0 1 7.6-7.3zm4.4 0a10.8 10.8 0 0 1 7.6 7.3h-4.9c-.3-2.7-1.3-5.3-2.7-7.3zM14 5.8v6.7h-1.1c.2-2.4.6-4.8 1.1-6.7zm4 0c.5 1.9.9 4.3 1.1 6.7H18V5.8zM5.4 15h5.5v2H5.4a10.8 10.8 0 0 1 0-2zm7.4 0H14v2h-1.2v-2zm5.2 0h1.2v2H18v-2zm3.1 0h5.5a10.8 10.8 0 0 1 0 2h-5.5v-2zM6.2 19.5h4.9c.3 2.7 1.3 5.3 2.7 7.3a10.8 10.8 0 0 1-7.6-7.3zm6.7 0H14v6.7c-.5-1.9-.9-4.3-1.1-6.7zm5.1 0h1.1c-.2 2.4-.6 4.8-1.1 6.7v-6.7zm2.9 0h4.9a10.8 10.8 0 0 1-7.6 7.3c1.4-2 2.4-4.6 2.7-7.3z"/></svg>'}
    for emoji,svg in icons.items(): html=html.replace(f'<div class="i">{emoji}</div>',f'<div class="i">{svg}</div>')
    old_start="const tg=window.Telegram?.WebApp;if(tg){tg.ready();tg.expand();}let groups=[],current=null,filter='all',stack=['home'];"
    new_start="const tg=window.Telegram?.WebApp;const initData=tg?.initData||'';if(tg){tg.ready();tg.expand();}const authHeaders={'X-Telegram-Init-Data':initData};let groups=[],current=null,filter='all',stack=['home'];if(!initData){document.querySelector('.app').innerHTML='<div style=\"padding:60px 24px;text-align:center\"><h2>Доступ только через Telegram</h2><p style=\"color:#aaa;line-height:1.5\">Откройте приложение по пригласительной ссылке или QR-коду.</p></div>';throw new Error('Telegram access required');}"
    html=html.replace(old_start,new_start)
    html=html.replace("fetch('/api/groups',{cache:'no-store'})","fetch('/api/groups',{cache:'no-store',headers:authHeaders})")
    html=html.replace("fetch('/api/groups/'+id,{cache:'no-store'})","fetch('/api/groups/'+id,{cache:'no-store',headers:authHeaders})")
    html=html.replace("headers:{'Content-Type':'application/json'}","headers:{'Content-Type':'application/json','X-Telegram-Init-Data':initData}")
    html=html.replace('<div class="notice">В целях приватности на общей странице показывается район. Точный адрес используется только для маршрута и организационной связи.</div>','<div class="notice" id="addressNotice"></div>')
    old_badges="document.getElementById('dBadges').innerHTML=`<span class=\"badge\">📍 ${current.district}</span><span class=\"badge\">🕒 ${current.time}</span><span class=\"badge\">👥 ${current.members} участников</span><span class=\"badge\">Возраст ${current.age}</span><span class=\"badge\">🐾 ${current.pets}</span>`;"
    new_badges="document.getElementById('dBadges').innerHTML=`<span class=\"badge\">📍 ${current.address}</span><span class=\"badge\">🕒 ${current.time}</span><span class=\"badge\">👥 ${current.members} участников</span><span class=\"badge\">Возраст ${current.age}</span><span class=\"badge\">🐾 ${current.pets}</span>`;document.getElementById('addressNotice').textContent='Точный адрес: '+current.address;"
    html=html.replace(old_badges,new_badges)
    return HTMLResponse(html,headers={"Cache-Control":"no-store, max-age=0"})

@app.get("/about-hero.jpg")
def about_hero():
    b64_path=BASE/"static"/"assets"/"about_hero_exact.b64"
    try:
        encoded="".join(b64_path.read_text(encoding="utf-8").split()); image=base64.b64decode(encoded,validate=True)
    except Exception as exc: raise HTTPException(500,f"About hero image error: {exc}")
    return Response(content=image,media_type="image/jpeg",headers={"Cache-Control":"public, max-age=3600"})

@app.get("/api/groups")
def api_groups(request:Request):
    require_user(request); public=[]
    for g in groups:
        x=dict(g); x["public_address"]=g["address"]; public.append(x)
    return public

@app.get("/api/groups/{group_id}")
def api_group(group_id:str,request:Request):
    require_user(request)
    for g in groups:
        if g["id"]==group_id: return g
    raise HTTPException(404,"Group not found")

@app.post("/api/applications")
async def api_application(data:Application,request:Request):
    require_user(request)
    if not data.name.strip(): raise HTTPException(400,"Введите имя")
    group=next((g for g in groups if g["id"]==data.group_id),None)
    if not group: raise HTTPException(404,"Group not found")
    con=sqlite3.connect(DB); con.execute("INSERT INTO applications(group_id,name,telegram,comment) VALUES(?,?,?,?)",(data.group_id,data.name.strip(),data.telegram.strip(),data.comment.strip())); con.commit(); con.close()
    admin=os.getenv("ADMIN_CHAT_ID","").strip()
    if bot and admin:
        try:
            text=f"🔥 Новая заявка в домашнюю церковь\n\nГруппа: {group['name']}\nЛидеры: {group['leaders']}\nИмя: {data.name}\nTelegram: {data.telegram or '—'}\nКомментарий: {data.comment or '—'}"; await bot.send_message(admin,text)
        except Exception as exc: print(f"Не удалось отправить заявку администратору: {exc}")
    return {"ok":True}

@app.get("/health")
def health():
    return {"ok":True,"bot":bool(bot and polling_task and not polling_task.done())}
