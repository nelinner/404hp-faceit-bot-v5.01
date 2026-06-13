# main.py — 404hp FACEIT (полный код, новый токен, все функции)
import asyncio, logging, sqlite3, hashlib, secrets, random, os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ChatMemberStatus

# ---------- КОНФИГУРАЦИЯ ----------
TOKEN = "8254209430:AAHzRRGSOrMcie5JRj5DkmuUQIJK8d3ohTg"
PROJECT_NAME = "404hp FACEIT"
CHANNEL_ID = "@hp404faceit"
HEAD_ADMIN_USERNAME = "nelinner"
DB_NAME = "faceit_data.db"
OLD_DB_NAME = "404hp_faceit.db"

# Удаляем только совсем старые базы
for f in ["404hp_faceit_v2.db", "database.db", "404hp_faceit_new.db"]:
    if os.path.exists(f):
        try: os.remove(f)
        except: pass

# Изображения
MAIN_MENU_IMAGE = "https://ibb.co/yczGh1yQ"
REGISTRATION_IMAGE = "https://ibb.co/SD6Sz7Tf"
LEADERBOARD_IMAGE = "https://ibb.co/spHJL8t7"
LOBBY_CREATE_IMAGE = "https://ibb.co/FLk3W6KR"

ROLE_NAMES = {
    'player': '🎮 Игрок',
    'premium': '⭐ Premium',
    'admin': '🛡 Админ',
    'director': '⚡ Руководитель'
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- БАЗА ДАННЫХ (ВЕЧНАЯ) ----------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables(conn):
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY, nick TEXT UNIQUE, pw TEXT, salt TEXT,
        elo INT DEFAULT 0, rank TEXT DEFAULT '🎯 Level 1',
        role TEXT DEFAULT 'player', matches INT DEFAULT 0,
        wins INT DEFAULT 0, losses INT DEFAULT 0, wr REAL DEFAULT 0,
        reg TEXT, banned INT DEFAULT 0, ban_till TEXT, prem_till TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT, creator INT, code TEXT,
        map TEXT, max INT DEFAULT 10, now INT DEFAULT 1,
        status TEXT DEFAULT 'open', msg_id INT, finished INT DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS room_players (
        room INT, pid INT, nick TEXT, role TEXT, pos INT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT, room INT, side TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS team_players (
        team INT, pid INT, nick TEXT, elo INT, pos INT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bans (
        pid INT, till TEXT, reason TEXT, admin TEXT
    )""")
    try: c.execute("ALTER TABLE rooms ADD COLUMN finished INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE players ADD COLUMN prem_till TEXT")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE players ADD COLUMN ban_till TEXT")
    except sqlite3.OperationalError: pass
    conn.commit()

def migrate_old_db():
    if not os.path.exists(OLD_DB_NAME): return
    print("🔍 Перенос игроков из старой базы...")
    try:
        old_conn = sqlite3.connect(OLD_DB_NAME)
        old_conn.row_factory = sqlite3.Row
        old_players = old_conn.execute("SELECT * FROM players").fetchall()
        new_conn = get_db()
        create_tables(new_conn)
        for p in old_players:
            try:
                new_conn.execute("""INSERT INTO players (id, nick, pw, salt, elo, rank, role, matches, wins, losses, wr, reg, banned, ban_till, prem_till)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    p['id'], p['nick'], p['pw'], p['salt'], p['elo'], p['rank'], p['role'],
                    p['matches'], p['wins'], p['losses'], p['wr'], p['reg'],
                    p['banned'], p.get('ban_till'), p.get('prem_till')
                ))
            except sqlite3.IntegrityError: pass
        new_conn.commit(); new_conn.close(); old_conn.close()
        os.rename(OLD_DB_NAME, OLD_DB_NAME + ".backup")
        print("✅ Игроки перенесены")
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")

def init_db():
    if os.path.exists(OLD_DB_NAME): migrate_old_db()
    else:
        conn = get_db(); create_tables(conn); conn.close()

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
def hash_pw(pw, salt=None):
    if not salt: salt = secrets.token_hex(16)
    return hashlib.sha256((pw+salt).encode()).hexdigest(), salt

def check_pw(pw, salt, h): return hashlib.sha256((pw+salt).encode()).hexdigest() == h

def get_rank(elo):
    if elo<200: return "🎯 Level 1"
    if elo<400: return "🎯 Level 2"
    if elo<600: return "🎯 Level 3"
    if elo<800: return "🎯 Level 4"
    if elo<1000: return "🎯 Level 5"
    if elo<1200: return "🎯 Level 6"
    if elo<1400: return "💎 Level 7"
    if elo<1600: return "👑 Level 8"
    if elo<1800: return "🌟 Level 9"
    return "⚡ Level 10"

def gen_code(): return secrets.token_hex(4).upper()

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except: return False

def find_player(query: str):
    conn = get_db()
    if query.isdigit(): p = conn.execute("SELECT * FROM players WHERE id=?", (int(query),)).fetchone()
    else: p = conn.execute("SELECT * FROM players WHERE nick=?", (query,)).fetchone()
    conn.close()
    return p

def is_banned(uid):
    conn = get_db()
    b = conn.execute("SELECT till, reason FROM bans WHERE pid=?", (uid,)).fetchone()
    conn.close()
    if b and b['till']:
        try:
            if datetime.fromisoformat(b['till']) > datetime.now(): return True, b['till'], b['reason']
        except: pass
    return False, None, None

def menu(uid):
    r = get_db().execute("SELECT role FROM players WHERE id=?", (uid,)).fetchone()
    role = r[0] if r else 'player'
    kb = [
        [InlineKeyboardButton(text="🎮 НАЙТИ МАТЧ", callback_data="find")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Рейтинг", callback_data="top")],
        [InlineKeyboardButton(text="ℹ️ Правила", callback_data="rules")]
    ]
    if role in ['premium','admin','director']: kb.insert(1, [InlineKeyboardButton(text="🔰 СОЗДАТЬ ЛОББИ", callback_data="lobby")])
    if role in ['admin','director']: kb.append([InlineKeyboardButton(text="⚙️ Админ", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="🔄 Заменить игрока", callback_data="a_replace")],
        [InlineKeyboardButton(text="🔨 Забанить", callback_data="a_ban")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="a_unban")],
        [InlineKeyboardButton(text="👑 Назначить админа", callback_data="a_assign")],
        [InlineKeyboardButton(text="🥾 Снять админа", callback_data="a_revoke")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="a_prem")],
        [InlineKeyboardButton(text="🔙 Меню", callback_data="back")]
    ])

async def is_admin(uid):
    r = get_db().execute("SELECT role FROM players WHERE id=?", (uid,)).fetchone()
    return r and r[0] in ['admin','director']

async def is_director(uid):
    r = get_db().execute("SELECT role FROM players WHERE id=?", (uid,)).fetchone()
    return r and r[0] == 'director'

# ---------- ОБНОВЛЕНИЕ ПОСТА ЛОББИ ----------
async def update_lobby_post(room_id):
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if not room or not room['msg_id']: conn.close(); return
    players = conn.execute("SELECT nick FROM room_players WHERE room=? ORDER BY pos", (room_id,)).fetchall()
    conn.close()
    player_list = "\n".join(f"• {p['nick']}" for p in players)
    map_name = MAPS.get(room['map'], '?')
    creator = get_db().execute("SELECT nick FROM players WHERE id=?", (room['creator'],)).fetchone()
    creator_nick = creator['nick'] if creator else "?"
    text = (
        f"🔰 <b>ЛОББИ #{room_id}</b>\n━━━━━━━━━━━━━━\n"
        f"👤 <b>Создатель:</b> {creator_nick}\n"
        f"🗺 <b>Карта:</b> {map_name}\n"
        f"🔑 <b>Код:</b> <code>{room['code']}</code>\n\n"
        f"👥 <b>Игроки ({room['now']}/{room['max']}):</b>\n{player_list}\n\n"
        f"⚡ <i>Нажмите кнопку ниже, чтобы присоединиться</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔰 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_{room_id}")]
    ])
    try:
        await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=room['msg_id'], text=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        print(f"Ошибка обновления поста: {e}")

# ---------- /start ----------
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    if not await check_sub(msg.from_user.id):
        await msg.answer_photo(MAIN_MENU_IMAGE, caption=f"🔒 Подпишитесь на {CHANNEL_ID}")
        return
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (msg.from_user.id,)).fetchone()
    if not p:
        await msg.answer_photo(REGISTRATION_IMAGE, caption="🎮 Введите игровой никнейм:")
        await state.set_state(Reg.nick)
    else:
        if (msg.from_user.username or "").lower() == HEAD_ADMIN_USERNAME and p['role'] != 'director':
            conn.execute("UPDATE players SET role='director' WHERE id=?", (msg.from_user.id,))
            conn.commit()
            p = conn.execute("SELECT * FROM players WHERE id=?", (msg.from_user.id,)).fetchone()
        role_display = ROLE_NAMES.get(p['role'], 'Игрок')
        await msg.answer_photo(MAIN_MENU_IMAGE,
            caption=f"👋 {p['nick']}\n🎭 Роль: {role_display}\n🏅 {p['rank']} | ELO: {p['elo']}\nМатчей: {p['matches']}\n\nВыберите действие:",
            reply_markup=menu(msg.from_user.id))
    conn.close()

# ---------- FSM ----------
class Reg(StatesGroup): nick = State(); pw = State(); pw2 = State()
class Lobby(StatesGroup): map = State(); confirm = State()
class Result(StatesGroup): photo = State(); score = State()
class AdminFSM(StatesGroup): assign = State(); revoke = State(); prem = State(); ban_user = State(); ban_reason = State(); ban_dur = State(); unban_user = State()
class Replace(StatesGroup): lobby = State(); old = State(); new = State(); confirm = State()

MAPS = {
    "sandstone":"🏝 Sandstone","dune":"🏜 Dune",
    "province":"🏘 Province","rust":"🏗 Rust",
    "breeze":"🌴 Breeze","hanami":"🌸 Hanami",
    "prison":"🔒 Prison"
}

# ---------- РЕГИСТРАЦИЯ ----------
@dp.message(Reg.nick)
async def reg_nick(msg: types.Message, state: FSMContext):
    nick = msg.text.strip()
    if len(nick) < 3: await msg.answer_photo(REGISTRATION_IMAGE, caption="❌ Минимум 3 символа"); return
    conn = get_db()
    if conn.execute("SELECT 1 FROM players WHERE nick=?", (nick,)).fetchone():
        await msg.answer_photo(REGISTRATION_IMAGE, caption="❌ Ник занят"); conn.close(); return
    conn.close()
    await state.update_data(n=nick)
    await msg.answer_photo(REGISTRATION_IMAGE, caption="🔐 Придумайте пароль (мин. 6):")
    await state.set_state(Reg.pw)

@dp.message(Reg.pw)
async def reg_pw(msg: types.Message, state: FSMContext):
    pw = msg.text.strip()
    if len(pw) < 6: await msg.answer_photo(REGISTRATION_IMAGE, caption="❌ Минимум 6 символов"); return
    await state.update_data(p=pw)
    await msg.answer_photo(REGISTRATION_IMAGE, caption="🔐 Повторите пароль:")
    await state.set_state(Reg.pw2)

@dp.message(Reg.pw2)
async def reg_pw2(msg: types.Message, state: FSMContext):
    if msg.text.strip() != (await state.get_data())['p']:
        await msg.answer_photo(REGISTRATION_IMAGE, caption="❌ Не совпадают"); await state.set_state(Reg.pw); return
    data = await state.get_data()
    h, s = hash_pw(data['p'])
    role = 'director' if (msg.from_user.username or "").lower() == HEAD_ADMIN_USERNAME else 'player'
    conn = get_db()
    conn.execute("INSERT INTO players (id,nick,pw,salt,role,reg) VALUES (?,?,?,?,?,datetime('now'))",
                 (msg.from_user.id, data['n'], h, s, role))
    conn.commit(); conn.close()
    await msg.answer_photo(REGISTRATION_IMAGE, caption=f"✅ Добро пожаловать, {data['n']}!\nРоль: {ROLE_NAMES[role]}\nELO: 0")
    await state.clear()

# ---------- ВХОД (ИСПРАВЛЕН) ----------
@dp.message(Command("login"))
async def login(msg: types.Message):
    parts = msg.text.split()
    if len(parts) != 3:
        await msg.answer("/login ник пароль")
        return
    nick, pw = parts[1], parts[2]
    conn = get_db()
    u = conn.execute("SELECT id, pw, salt, role FROM players WHERE nick=?", (nick,)).fetchone()
    if not u:
        await msg.answer("❌ Пользователь с таким ником не найден")
        conn.close()
        return
    if check_pw(pw, u['salt'], u['pw']):
        conn.execute("UPDATE players SET id=? WHERE id=?", (msg.from_user.id, u['id']))
        conn.commit()
        conn.close()
        await msg.answer_photo(MAIN_MENU_IMAGE, caption=f"✅ Вход выполнен!\nРоль: {ROLE_NAMES.get(u['role'], 'Игрок')}")
    else:
        conn.close()
        await msg.answer_photo(MAIN_MENU_IMAGE, caption="❌ Неверный пароль")

# ---------- ПОИСК МАТЧА ----------
@dp.callback_query(lambda c: c.data == "find")
async def find_match(cb: types.CallbackQuery):
    uid = cb.from_user.id
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (uid,)).fetchone()
    if not p: await cb.answer("❌ Сначала зарегистрируйтесь /start", show_alert=True); conn.close(); return
    banned, until, _ = is_banned(uid)
    if banned: await cb.answer(f"⛔ Вы заблокированы до {until}", show_alert=True); conn.close(); return
    rooms = conn.execute("SELECT id, map, now, code FROM rooms WHERE status='open' AND now < max ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    await cb.message.delete()
    if not rooms: await bot.send_message(cb.from_user.id, "😔 Нет открытых лобби. Создайте своё или подождите."); return
    kb = [[InlineKeyboardButton(text=f"Лобби #{r['id']} | {MAPS.get(r['map'],'?')} ({r['now']}/10)", callback_data=f"join_{r['id']}")] for r in rooms]
    kb.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="find")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    await bot.send_message(cb.from_user.id, "🎮 Доступные лобби:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ---------- СОЗДАНИЕ ЛОББИ ----------
@dp.callback_query(lambda c: c.data == "lobby")
async def create_lobby(cb: types.CallbackQuery, state: FSMContext):
    kb = [[InlineKeyboardButton(text=v, callback_data=f"map_{k}")] for k,v in MAPS.items()]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, LOBBY_CREATE_IMAGE, caption="🗺 Выберите карту:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(Lobby.map)

@dp.callback_query(lambda c: c.data.startswith("map_"), Lobby.map)
async def lobby_map(cb: types.CallbackQuery, state: FSMContext):
    map_id = cb.data.split("_")[1]; c = gen_code()
    await state.update_data(m=map_id, c=c)
    await cb.message.delete()
    await bot.send_photo(cb.from_user.id, LOBBY_CREATE_IMAGE, caption=f"🔰 Создание лобби\n🗺 {MAPS[map_id]}\n🔑 Код: {c}\n\nПодтвердите:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Создать", callback_data="pub"), InlineKeyboardButton(text="🔙 Отмена", callback_data="back")]]))
    await state.set_state(Lobby.confirm)

@dp.callback_query(lambda c: c.data == "pub", Lobby.confirm)
async def publish_lobby(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data(); map_id, code = data['m'], data['c']
    uid = cb.from_user.id
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (uid,)).fetchone()
    cur = conn.execute("INSERT INTO rooms (creator, code, map) VALUES (?,?,?)", (uid, code, map_id))
    conn.commit()
    rid = cur.lastrowid
    conn.execute("INSERT INTO room_players VALUES (?,?,?,?,1)", (rid, uid, p['nick'], p['role']))
    conn.commit()
    players = conn.execute("SELECT nick FROM room_players WHERE room=? ORDER BY pos", (rid,)).fetchall()
    player_list = "\n".join(f"• {pl['nick']}" for pl in players)
    txt = (
        f"🔰 <b>ЛОББИ #{rid}</b>\n━━━━━━━━━━━━━━\n"
        f"👤 <b>Создатель:</b> {p['nick']}\n"
        f"🗺 <b>Карта:</b> {MAPS[map_id]}\n"
        f"🔑 <b>Код:</b> <code>{code}</code>\n\n"
        f"👥 <b>Игроки (1/10):</b>\n{player_list}\n\n"
        f"⚡ <i>Нажмите кнопку ниже, чтобы присоединиться</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔰 ПРИСОЕДИНИТЬСЯ", callback_data=f"join_{rid}")]
    ])
    try:
        msg = await bot.send_message(CHANNEL_ID, txt, parse_mode="HTML", reply_markup=kb)
        conn.execute("UPDATE rooms SET msg_id=? WHERE id=?", (msg.message_id, rid))
        conn.commit()
    except Exception as e:
        print(f"Ошибка отправки в канал: {e}")
    conn.close()
    await cb.message.delete()
    await bot.send_photo(cb.from_user.id, LOBBY_CREATE_IMAGE, caption=f"✅ Лобби создано!\n🔑 {code}\n👥 1/10")
    await state.clear()

# ---------- ПРИСОЕДИНЕНИЕ К ЛОББИ ----------
@dp.callback_query(lambda c: c.data.startswith("join_"))
async def join_lobby(cb: types.CallbackQuery):
    rid = int(cb.data.split("_")[1]); uid = cb.from_user.id
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (uid,)).fetchone()
    if not p: await cb.answer("❌ Зарегистрируйтесь", show_alert=True); conn.close(); return
    r = conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
    if not r or r['status']!='open': await cb.answer("❌ Лобби не найдено", show_alert=True); conn.close(); return
    if r['now'] >= r['max']: await cb.answer("❌ Заполнено", show_alert=True); conn.close(); return
    if conn.execute("SELECT 1 FROM room_players WHERE room=? AND pid=?", (rid, uid)).fetchone(): await cb.answer("❌ Вы уже в лобби", show_alert=True); conn.close(); return
    n = r['now'] + 1
    conn.execute("INSERT INTO room_players VALUES (?,?,?,?,?)", (rid, uid, p['nick'], p['role'], n))
    conn.execute("UPDATE rooms SET now=? WHERE id=?", (n, rid))
    conn.commit(); conn.close()
    await update_lobby_post(rid)
    await cb.answer(f"✅ Вы присоединились ({n}/10)", show_alert=True)
    if n >= 10:
        try: await bot.send_message(r['creator'], f"🎯 Лобби #{rid} заполнено! /draw {rid}")
        except: pass

# ---------- ЖЕРЕБЬЁВКА ----------
@dp.message(Command("draw"))
async def draw(msg: types.Message):
    try:
        parts = msg.text.split()
        if len(parts) != 2: await msg.answer("/draw номер_лобби"); return
        rid = int(parts[1])
        conn = get_db()
        r = conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not r: await msg.answer("❌ Лобби не найдено"); conn.close(); return
        if r['now'] < 10: await msg.answer("❌ Недостаточно игроков"); conn.close(); return
        pls = conn.execute("SELECT * FROM room_players WHERE room=? ORDER BY pos", (rid,)).fetchall()
        pls = [dict(p) for p in pls]; random.shuffle(pls)
        ct, t = pls[:5], pls[5:10]
        cur = conn.execute("INSERT INTO teams (room, side) VALUES (?,'CT')", (rid,))
        conn.commit()
        ct_id = cur.lastrowid
        for i,p in enumerate(ct):
            elo = conn.execute("SELECT elo FROM players WHERE id=?", (p['pid'],)).fetchone()[0]
            conn.execute("INSERT INTO team_players VALUES (?,?,?,?,?)", (ct_id, p['pid'], p['nick'], elo, i+1))
        cur = conn.execute("INSERT INTO teams (room, side) VALUES (?,'T')", (rid,))
        conn.commit()
        t_id = cur.lastrowid
        for i,p in enumerate(t):
            elo = conn.execute("SELECT elo FROM players WHERE id=?", (p['pid'],)).fetchone()[0]
            conn.execute("INSERT INTO team_players VALUES (?,?,?,?,?)", (t_id, p['pid'], p['nick'], elo, i+1))
        conn.execute("UPDATE rooms SET status='closed' WHERE id=?", (rid,))
        conn.commit(); conn.close()
        txt = f"🎲 ЖЕРЕБЬЁВКА\nЛобби #{rid}\n━━━━━━━━━━━━━━\n\n🔵 CT:\n"
        for i,p in enumerate(ct): txt += f"{i+1}. {p['nick']}\n"
        txt += "\n🔴 T:\n"
        for i,p in enumerate(t): txt += f"{i+1}. {p['nick']}\n"
        txt += "\n🎯 Удачной игры!\nПосле матча: /result"
        await bot.send_message(CHANNEL_ID, txt)
        await msg.answer("✅ Жеребьёвка завершена!")
    except Exception as e:
        print(f"Ошибка в draw: {e}")
        await msg.answer("❌ Ошибка при жеребьёвке")

# ---------- РЕЗУЛЬТАТ (С ОБЯЗАТЕЛЬНЫМ СКРИНШОТОМ И ХОСТОМ) ----------
@dp.message(Command("result"))
async def result_start(msg: types.Message, state: FSMContext):
    if not await is_admin(msg.from_user.id): await msg.answer("❌ Только админ"); return
    await msg.answer_photo(MAIN_MENU_IMAGE, caption="📸 Пожалуйста, отправьте скриншот результата матча.")
    await state.set_state(Result.photo)

@dp.message(Result.photo, F.photo)
async def result_photo(msg: types.Message, state: FSMContext):
    photo_id = msg.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await msg.answer("📊 Теперь введите счёт матча в формате:\nCT T номер_лобби\nПример: 16 14 5")
    await state.set_state(Result.score)

@dp.message(Result.score)
async def result_score(msg: types.Message, state: FSMContext):
    try:
        ct, t, rid = map(int, msg.text.split())
        data = await state.get_data()
        photo_id = data.get('photo')
        conn = get_db()
        teams = conn.execute("SELECT * FROM teams WHERE room=?", (rid,)).fetchall()
        if len(teams) != 2: await msg.answer("❌ Команды не найдены"); conn.close(); await state.clear(); return
        ct_team = teams[0] if teams[0]['side']=='CT' else teams[1]
        t_team = teams[1] if teams[0]['side']=='CT' else teams[0]
        ct_pl = conn.execute("SELECT * FROM team_players WHERE team=? ORDER BY pos", (ct_team['id'],)).fetchall()
        t_pl = conn.execute("SELECT * FROM team_players WHERE team=? ORDER BY pos", (t_team['id'],)).fetchall()
        ct_won = ct > t
        for p in ct_pl:
            u = conn.execute("SELECT * FROM players WHERE id=?", (p['pid'],)).fetchone()
            if u:
                ch = random.randint(15,35) if ct_won else random.randint(10,30)
                ne = max(0, u['elo']+ch if ct_won else u['elo']-ch)
                m, w, l = u['matches']+1, u['wins']+(1 if ct_won else 0), u['losses']+(0 if ct_won else 1)
                conn.execute("UPDATE players SET elo=?, rank=?, matches=?, wins=?, losses=?, wr=? WHERE id=?", (ne, get_rank(ne), m, w, l, round(w/m*100,1), p['pid']))
        for p in t_pl:
            u = conn.execute("SELECT * FROM players WHERE id=?", (p['pid'],)).fetchone()
            if u:
                ch = random.randint(15,35) if not ct_won else random.randint(10,30)
                ne = max(0, u['elo']+ch if not ct_won else u['elo']-ch)
                m, w, l = u['matches']+1, u['wins']+(1 if not ct_won else 0), u['losses']+(0 if not ct_won else 1)
                conn.execute("UPDATE players SET elo=?, rank=?, matches=?, wins=?, losses=?, wr=? WHERE id=?", (ne, get_rank(ne), m, w, l, round(w/m*100,1), p['pid']))
        conn.execute("UPDATE rooms SET finished=1 WHERE id=?", (rid,))
        room = conn.execute("SELECT creator FROM rooms WHERE id=?", (rid,)).fetchone()
        host_nick = None
        if room:
            host = conn.execute("SELECT nick FROM players WHERE id=?", (room['creator'],)).fetchone()
            if host: host_nick = host['nick']
        conn.commit(); conn.close()
        txt = f"📊 РЕЗУЛЬТАТ МАТЧА\nЛобби #{rid}\n"
        if host_nick: txt += f"👑 Хост лобби: {host_nick}\n"
        txt += f"🔵 CT: {ct}\n"
        for p in ct_pl: txt += f"• {p['nick']}\n"
        txt += f"\n🔴 T: {t}\n"
        for p in t_pl: txt += f"• {p['nick']}\n"
        txt += f"\n🏆 Победитель: {'CT' if ct_won else 'T'}"
        await bot.send_photo(CHANNEL_ID, photo=photo_id, caption=txt)
        await msg.answer("✅ Результаты сохранены и опубликованы со скриншотом!")
        await state.clear()
    except:
        await msg.answer("❌ Формат: CT T номер_лобби")

# ---------- ПРОФИЛЬ ----------
@dp.callback_query(lambda c: c.data == "profile")
async def profile(cb: types.CallbackQuery):
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (cb.from_user.id,)).fetchone()
    conn.close()
    if not p: await cb.answer("❌ Не найден", show_alert=True); return
    txt = f"👤 ПРОФИЛЬ\n━━━━━━━━━━━━━━\n🎮 {p['nick']}\n🎭 Роль: {ROLE_NAMES.get(p['role'],'Игрок')}\n🏅 {p['rank']}\n📊 ELO: {p['elo']}\n\n📈 Статистика:\n🎯 Матчей: {p['matches']}\n✅ Побед: {p['wins']}\n❌ Поражений: {p['losses']}\n📊 Winrate: {p['wr']}%"
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Меню", callback_data="back")]]))

# ---------- РЕЙТИНГ ----------
@dp.callback_query(lambda c: c.data == "top")
async def top(cb: types.CallbackQuery):
    conn = get_db()
    pls = conn.execute("SELECT * FROM players WHERE banned=0 ORDER BY elo DESC LIMIT 15").fetchall()
    conn.close()
    txt = "🏆 ТОП-15\n━━━━━━━━━━━━━━\n\n"
    medals = ["🥇","🥈","🥉"] + ["👤"]*12
    for i,p in enumerate(pls): txt += f"{medals[i]} #{i+1} {p['nick']}\n   🏅 {p['rank']} | ELO: {p['elo']} | W/L: {p['wins']}/{p['losses']}\n\n"
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, LEADERBOARD_IMAGE, caption=txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="top")], [InlineKeyboardButton(text="🔙 Меню", callback_data="back")]]))

# ---------- ПРАВИЛА ----------
@dp.callback_query(lambda c: c.data == "rules")
async def rules(cb: types.CallbackQuery):
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption="📜 Правила:\n1. Честная игра\n2. Уважение\n3. Обязательно играть\n4. Бан за нарушения", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ознакомлен", callback_data="back")]]))

# ---------- АДМИН-ПАНЕЛЬ ----------
@dp.callback_query(lambda c: c.data == "admin")
async def admin_panel(cb: types.CallbackQuery):
    if not await is_admin(cb.from_user.id): await cb.answer("❌ Нет доступа", show_alert=True); return
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption="⚙️ Админ-панель", reply_markup=admin_kb())

@dp.callback_query(lambda c: c.data == "a_users")
async def a_users(cb: types.CallbackQuery):
    if not await is_admin(cb.from_user.id): return
    conn = get_db()
    pls = conn.execute("SELECT * FROM players LIMIT 20").fetchall()
    conn.close()
    txt = "👥 Пользователи:\n" + "\n".join(f"{p['nick']} | {ROLE_NAMES.get(p['role'],'?')} | ELO: {p['elo']}" for p in pls)
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=txt, reply_markup=admin_kb())

# ---------- ЗАМЕНА ИГРОКА ----------
@dp.callback_query(lambda c: c.data == "a_replace")
async def replace_start(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    conn = get_db()
    rooms = conn.execute("SELECT r.id, r.map FROM rooms r INNER JOIN teams t ON r.id = t.room WHERE r.status = 'closed' AND r.finished = 0 GROUP BY r.id ORDER BY r.id DESC LIMIT 10").fetchall()
    conn.close()
    if not rooms: await cb.message.answer("❌ Нет лобби с командами, ожидающих результата"); return
    kb = [[InlineKeyboardButton(text=f"Лобби #{r['id']} – {MAPS.get(r['map'],'?')}", callback_data=f"repl_{r['id']}")] for r in rooms]
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="admin")])
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption="🔄 Выберите лобби для замены:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(Replace.lobby)

@dp.callback_query(lambda c: c.data.startswith("repl_"), Replace.lobby)
async def repl_lobby(cb: types.CallbackQuery, state: FSMContext):
    rid = int(cb.data.split("_")[1])
    conn = get_db()
    teams = conn.execute("SELECT id, side FROM teams WHERE room=?", (rid,)).fetchall()
    if len(teams) != 2: await cb.answer("❌ Команды не сформированы", show_alert=True); conn.close(); return
    await state.update_data(repl_rid=rid)
    kb = []
    for team in teams:
        players = conn.execute("SELECT pid, nick FROM team_players WHERE team=? ORDER BY pos", (team['id'],)).fetchall()
        em = "🔵" if team['side'] == 'CT' else "🔴"
        for p in players: kb.append([InlineKeyboardButton(text=f"{em} {p['nick']}", callback_data=f"old_{p['pid']}")])
    kb.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="admin")])
    conn.close()
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=f"🔄 Выберите игрока для замены в лобби #{rid}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(Replace.old)

@dp.callback_query(lambda c: c.data.startswith("old_"), Replace.old)
async def repl_old(cb: types.CallbackQuery, state: FSMContext):
    old_id = int(cb.data.split("_")[1])
    conn = get_db(); old_nick = conn.execute("SELECT nick FROM players WHERE id=?", (old_id,)).fetchone(); conn.close()
    await state.update_data(old_id=old_id, old_nick=old_nick[0] if old_nick else "?")
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=f"🔄 Замена {old_nick[0] if old_nick else 'игрока'}\nВведите ID или @username нового игрока:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="admin")]]))
    await state.set_state(Replace.new)

@dp.message(Replace.new)
async def repl_new(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    banned, until, _ = is_banned(p['id'])
    if banned: await msg.answer(f"❌ Игрок заблокирован до {until}"); await state.clear(); return
    data = await state.get_data()
    conn = get_db()
    if conn.execute("SELECT 1 FROM room_players WHERE room=? AND pid=?", (data['repl_rid'], p['id'])).fetchone(): await msg.answer("❌ Игрок уже в этом лобби"); conn.close(); await state.clear(); return
    conn.close()
    await state.update_data(new_id=p['id'], new_nick=p['nick'], new_elo=p['elo'])
    data = await state.get_data()
    await msg.answer_photo(MAIN_MENU_IMAGE, caption=f"🔄 Подтвердите замену:\n❌ {data['old_nick']}\n✅ {data['new_nick']} (ELO: {data['new_elo']})\nЛобби #{data['repl_rid']}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить", callback_data="repl_ok"), InlineKeyboardButton(text="❌ Отмена", callback_data="admin")]]))
    await state.set_state(Replace.confirm)

@dp.callback_query(lambda c: c.data == "repl_ok", Replace.confirm)
async def repl_ok(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rid, old_id, new_id = data['repl_rid'], data['old_id'], data['new_id']
    old_nick, new_nick, new_elo = data['old_nick'], data['new_nick'], data.get('new_elo', 0)
    conn = get_db()
    team = conn.execute("SELECT t.id, t.side FROM teams t INNER JOIN team_players tp ON t.id = tp.team WHERE tp.pid = ? AND t.room = ?", (old_id, rid)).fetchone()
    if not team: await cb.answer("❌ Игрок не найден в командах", show_alert=True); conn.close(); await state.clear(); return
    conn.execute("UPDATE team_players SET pid=?, nick=?, elo=? WHERE team=? AND pid=?", (new_id, new_nick, new_elo, team['id'], old_id))
    conn.execute("UPDATE room_players SET pid=?, nick=? WHERE room=? AND pid=?", (new_id, new_nick, rid, old_id))
    conn.commit(); conn.close()
    side_emoji = "🔵" if team['side'] == 'CT' else "🔴"
    try:
        await bot.send_message(CHANNEL_ID, f"🔄 <b>ЗАМЕНА ИГРОКА</b>\n━━━━━━━━━━━━━━\n🎯 Лобби #{rid}\n👮 Администратор: {cb.from_user.full_name}\n❌ Заменён: {old_nick}\n✅ Новый: {new_nick} (ELO: {new_elo})\n{side_emoji} Команда: {team['side']}", parse_mode="HTML")
    except: pass
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=f"✅ Замена выполнена!\n{old_nick} → {new_nick}\n{side_emoji} {team['side']}", reply_markup=admin_kb())
    try: await bot.send_message(new_id, f"🔄 Вы добавлены в лобби #{rid}!\n{side_emoji} {team['side']}")
    except: pass
    try: await bot.send_message(old_id, f"ℹ️ Вас заменили в лобби #{rid} на игрока {new_nick}")
    except: pass
    await state.clear()

# ---------- БАН ----------
@dp.callback_query(lambda c: c.data == "a_ban")
async def a_ban(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("Введите ID или никнейм игрока для бана:")
    await state.set_state(AdminFSM.ban_user)

@dp.message(AdminFSM.ban_user)
async def ban_user(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    if p['role'] in ['admin','director']: await msg.answer("❌ Нельзя забанить администратора"); await state.clear(); return
    await state.update_data(ban_id=p['id'])
    await msg.answer(f"📝 Причина бана для {p['nick']}:")
    await state.set_state(AdminFSM.ban_reason)

@dp.message(AdminFSM.ban_reason)
async def ban_reason(msg: types.Message, state: FSMContext):
    await state.update_data(ban_reason=msg.text.strip())
    await msg.answer("🔨 Срок бана:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ 10 минут", callback_data="ban_10")],
        [InlineKeyboardButton(text="🕐 1 час", callback_data="ban_60")],
        [InlineKeyboardButton(text="📅 1 день", callback_data="ban_1440")],
        [InlineKeyboardButton(text="📆 1 неделя", callback_data="ban_10080")],
        [InlineKeyboardButton(text="🗓 1 месяц", callback_data="ban_43200")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="admin")]
    ]))
    await state.set_state(AdminFSM.ban_dur)

@dp.callback_query(lambda c: c.data.startswith("ban_"), AdminFSM.ban_dur)
async def ban_dur(cb: types.CallbackQuery, state: FSMContext):
    mins = int(cb.data.split("_")[1])
    data = await state.get_data()
    uid, reason = data['ban_id'], data['ban_reason']
    until = (datetime.now() + timedelta(minutes=mins)).isoformat()
    conn = get_db()
    conn.execute("UPDATE players SET banned=1, ban_till=? WHERE id=?", (until, uid))
    conn.execute("INSERT OR REPLACE INTO bans VALUES (?,?,?,?)", (uid, until, reason, cb.from_user.full_name))
    conn.commit()
    p = conn.execute("SELECT nick FROM players WHERE id=?", (uid,)).fetchone()
    conn.close()
    dur_text = "10 минут" if mins==10 else "1 час" if mins==60 else "1 день" if mins==1440 else "1 неделя" if mins==10080 else "1 месяц"
    try:
        await bot.send_message(CHANNEL_ID, f"🔨 <b>БЛОКИРОВКА</b>\n━━━━━━━━━━━━━━\n👤 Игрок: {p['nick']}\n👮 Администратор: {cb.from_user.full_name}\n⏱ Срок: {dur_text}\n📅 Разблокировка: {datetime.fromisoformat(until).strftime('%d.%m.%Y %H:%M')}\n📝 Причина: {reason}", parse_mode="HTML")
    except: pass
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=f"🔨 {p['nick']} заблокирован", reply_markup=admin_kb())
    await state.clear()

# ---------- РАЗБАН ----------
@dp.callback_query(lambda c: c.data == "a_unban")
async def a_unban(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("Введите ID или никнейм игрока для разбана:")
    await state.set_state(AdminFSM.unban_user)

@dp.message(AdminFSM.unban_user)
async def unban_user(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    conn = get_db()
    conn.execute("UPDATE players SET banned=0, ban_till=NULL WHERE id=?", (p['id'],))
    conn.execute("DELETE FROM bans WHERE pid=?", (p['id'],))
    conn.commit(); conn.close()
    await msg.answer(f"✅ {p['nick']} разблокирован")
    await state.clear()

# ---------- PREMIUM ----------
@dp.callback_query(lambda c: c.data == "a_prem")
async def a_prem(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("Введите ID или никнейм для выдачи Premium:")
    await state.set_state(AdminFSM.prem)

@dp.message(AdminFSM.prem)
async def do_prem(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    until = (datetime.now() + timedelta(days=30)).isoformat()
    conn = get_db()
    conn.execute("UPDATE players SET prem_till=? WHERE id=?", (until, p['id']))
    conn.commit(); conn.close()
    await msg.answer(f"✅ Premium выдан {p['nick']} на 1 месяц")
    await state.clear()

# ---------- НАЗНАЧИТЬ / СНЯТЬ АДМИНА ----------
@dp.callback_query(lambda c: c.data == "a_assign")
async def a_assign(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("Введите ID или никнейм пользователя для назначения админом:")
    await state.set_state(AdminFSM.assign)

@dp.message(AdminFSM.assign)
async def do_assign(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    conn = get_db()
    conn.execute("UPDATE players SET role='admin' WHERE id=?", (p['id'],))
    conn.commit(); conn.close()
    await msg.answer(f"✅ {p['nick']} теперь админ")
    await state.clear()

@dp.callback_query(lambda c: c.data == "a_revoke")
async def a_revoke(cb: types.CallbackQuery, state: FSMContext):
    if not await is_director(cb.from_user.id): await cb.answer("❌ Только руководитель может снимать админов", show_alert=True); return
    await cb.message.answer("Введите ID или никнейм админа для снятия:")
    await state.set_state(AdminFSM.revoke)

@dp.message(AdminFSM.revoke)
async def do_revoke(msg: types.Message, state: FSMContext):
    query = msg.text.strip()
    p = find_player(query)
    if not p: await msg.answer("❌ Игрок не найден"); await state.clear(); return
    if p['role'] != 'admin': await msg.answer("❌ Этот пользователь не админ"); await state.clear(); return
    conn = get_db()
    conn.execute("UPDATE players SET role='player' WHERE id=?", (p['id'],))
    conn.commit(); conn.close()
    await msg.answer(f"✅ Администратор {p['nick']} снят")
    await state.clear()

# ---------- НАЗАД ----------
@dp.callback_query(lambda c: c.data == "back")
async def back(cb: types.CallbackQuery):
    conn = get_db()
    p = conn.execute("SELECT * FROM players WHERE id=?", (cb.from_user.id,)).fetchone()
    conn.close()
    if p:
        role_display = ROLE_NAMES.get(p['role'], 'Игрок')
        cap = f"🎮 {PROJECT_NAME}\n👤 {p['nick']}\n🎭 Роль: {role_display}\n🏅 {p['rank']} | ELO: {p['elo']}"
    else: cap = f"🎮 {PROJECT_NAME}"
    await cb.message.delete(); await bot.send_photo(cb.from_user.id, MAIN_MENU_IMAGE, caption=cap, reply_markup=menu(cb.from_user.id))

# ---------- ЗАПУСК ----------
async def main():
    init_db()
    print(f"🔥 {PROJECT_NAME} ЗАПУЩЕН!")
    while True:
        try: await dp.start_polling(bot)
        except Exception as e:
            print(f"Ошибка: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
