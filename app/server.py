
import os, json, sqlite3, asyncio
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from aiogram import Bot
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE.parent / ".env")

app = FastAPI(title="Божья Благодать — Домашние церкви")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

groups = json.loads((BASE / "groups.json").read_text(encoding="utf-8"))
DB = BASE.parent / "applications.db"

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
    con.commit(); con.close()
init_db()

class Application(BaseModel):
    group_id: str
    name: str
    telegram: str = ""
    comment: str = ""

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/groups")
def api_groups():
    # Exact private address is intentionally not sent to the general list UI.
    public=[]
    for g in groups:
        x=dict(g)
        x["public_address"]=g["district"] + " район"
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
    con=sqlite3.connect(DB)
    con.execute("INSERT INTO applications(group_id,name,telegram,comment) VALUES(?,?,?,?)",
                (data.group_id,data.name.strip(),data.telegram.strip(),data.comment.strip()))
    con.commit(); con.close()

    token=os.getenv("BOT_TOKEN","").strip()
    admin=os.getenv("ADMIN_CHAT_ID","").strip()
    if token and admin:
        try:
            bot=Bot(token=token)
            text=(f"🔥 Новая заявка в домашнюю церковь\n\n"
                  f"Группа: {group['name']}\nЛидеры: {group['leaders']}\n"
                  f"Имя: {data.name}\nTelegram: {data.telegram or '—'}\n"
                  f"Комментарий: {data.comment or '—'}")
            await bot.send_message(admin, text)
            await bot.session.close()
        except Exception:
            pass
    return {"ok": True}

@app.get("/health")
def health():
    return {"ok": True}
