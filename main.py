import os
import asyncio
import sqlite3
import random
import json
import logging
from datetime import datetime, timezone, timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, ChatMemberUpdated
from pyrogram.errors import UserNotParticipant, MessageNotModified

# ================= CONFIGURACIÓN =================
API_ID = 37763566
API_HASH = "101d3d52aa8d3036b7c9d389a89a75b5"
BOT_TOKEN = "8942937055:AAEjjYnQiBfAsQmyi8JGQHdpWNg_h1qQzy4"
OWNER_ID = 8922104395

# ID de tu canal privado de Logs (Se añade -100 por ser canal privado en Telegram)
LOG_CHANNEL_ID = -1003798786021
# =================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Client(
    "kai_premium_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    parse_mode=enums.ParseMode.HTML
)

# ================= BASE DE DATOS =================
DB_PATH = os.path.join(os.getcwd(), "bot_data_premium.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS links (link_id TEXT PRIMARY KEY, files_data TEXT, thumb_id TEXT, forcesub TEXT, protect BOOLEAN, resolution TEXT, author TEXT, caption TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, banned BOOLEAN)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS admin_settings (id INTEGER PRIMARY KEY, lang TEXT, p_style INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS downloads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, link_id TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

try:
    cursor.execute("ALTER TABLE links ADD COLUMN resolution TEXT DEFAULT '1080p'")
    cursor.execute("ALTER TABLE links ADD COLUMN author TEXT DEFAULT 'KAI'")
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE links ADD COLUMN caption TEXT DEFAULT ''")
    conn.commit()
except sqlite3.OperationalError:
    pass

cursor.execute("INSERT OR IGNORE INTO admin_settings (id, lang, p_style) VALUES (1, 'es', 1)")
cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
conn.commit()

# ================= VARIABLES GLOBALES =================
admin_states = {}
pending_users = {}

PROGRESS_STYLES = {
    1: ["░", "█"],
    2: ["□", "■"],
    3: ["▱", "▰"],
    4: ["🤍", "💙"]
}

def get_admins():
    cursor.execute("SELECT user_id FROM admins")
    return [row[0] for row in cursor.fetchall()]

def is_admin(user_id):
    return user_id in get_admins()

# Textos exclusivamente en INGLÉS para los usuarios finales (con blockquotes)
USER_MSG = {
    'banned': "<blockquote>🚫 <b>ACCESS DENIED</b>\n\nYour account has been restricted by the administrators.</blockquote>",
    'no_link': "<blockquote>🤖 <b>STORAGE SYSTEM</b>\n\nYou need a valid link to access files.</blockquote>",
    'invalid': "<blockquote>❌ <b>INVALID LINK</b>\n\nThe requested file has expired or does not exist.</blockquote>",
    'fsub_msg': "<blockquote>⚠️ <b>SUBSCRIPTION REQUIRED</b>\n\nTo unlock your files, please join our channel:\n\n👉 <b>{}</b>\n\n<i>Once you join, your files will be sent here automatically.</i></blockquote>",
    'fsub_btn': "📢 Join Required Channel",
    'verify': "<blockquote>✅ <b>VERIFICATION SUCCESSFUL</b>\n\nSending files...</blockquote>",
    'warning': "<blockquote>⚠️ 🟡 <b>SECURITY WARNING</b> 🟡 ⚠️\n\nPlease forward these files to your <b>Saved Messages</b> immediately. For your safety, they will auto-delete from this chat in <b>10 minutes</b>.</blockquote>",
    'expired': "<blockquote>🗑 <b>TIME EXPIRED:</b> The files have been removed for security reasons. Please use your link again if you need them.</blockquote>"
}

# Textos multi-idioma para el panel de administración
LANG = {
    'es': {
        'panel': "<blockquote>🔧 <b>PANEL DE CONTROL</b>\n\nHola. Desde aquí puedes gestionar los enlaces y configurar el bot.\n\nElige una opción del menú:</blockquote>",
        'send_file': "<blockquote>📤 <b>SUBIR ARCHIVOS</b>\n\nEnvía el archivo, video o documento (Máx. 4GB). Si le pones un texto o descripción al enviar, el bot lo guardará.</blockquote>",
        'options': "<blockquote>✅ <b>ARCHIVO REGISTRADO</b>\n\n¿Quieres añadir más archivos a este enlace o continuar?</blockquote>",
        'btn_add': "➕ Añadir otro", 'btn_cont': "➡️ Continuar", 'btn_cancel': "❌ Cancelar",
        'send_thumb': "<blockquote>🖼 <b>MINIATURA</b>\n\nEnvía la imagen que acompañará a la descarga.</blockquote>",
        'send_res': "<blockquote>🎬 <b>CALIDAD DE VIDEO</b>\n\nSelecciona la resolución para este enlace:</blockquote>",
        'send_author': "<blockquote>👤 <b>CREADOR</b>\n\nSelecciona quién está subiendo este contenido:</blockquote>",
        'config': "<blockquote>⚙️ <b>CONFIGURACIÓN</b>\n\nAjusta las reglas del enlace antes de crearlo:</blockquote>",
        'btn_fsub': "📢 ForceSub / Canal", 'btn_prot': "🛡 Anti-Reenvío: ",
        'btn_gen': "💎 Generar Enlace", 'send_fsub': "<blockquote>✍️ <b>CANAL OBLIGATORIO</b>\n\nEnvía el @username o ID del canal donde el usuario debe unirse.</blockquote>",
        'link_ready': "<blockquote>🎉 <b>¡ENLACE LISTO!</b>\n\n🔗 <b>Enlace:</b>\n<code>https://t.me/{}?start={}</code></blockquote>",
        'stats': "<blockquote>📊 <b>ESTADÍSTICAS</b>\n\n🔗 Enlaces creados: <b>{}</b>\n🚫 Usuarios bloqueados: <b>{}</b></blockquote>",
        'deleted': "<blockquote>🗑 <b>PURGA COMPLETADA</b>\n\nTodos los enlaces fueron eliminados correctamente.</blockquote>",
        'btn_create': "➕ Crear Link", 'btn_stats': "📊 Estadísticas", 'btn_lang': "🌐 Idioma",
        'btn_style': "🎨 Estilo Carga", 'btn_dellinks': "🗑 Purgar Links"
    },
    'en': {
        'panel': "<blockquote>🔧 <b>CONTROL PANEL</b>\n\nHello. Manage your links and bot settings here.\n\nChoose an option:</blockquote>",
        'send_file': "<blockquote>📤 <b>UPLOAD FILES</b>\n\nSend the file, video or document (Max 4GB).</blockquote>",
        'options': "<blockquote>✅ <b>FILE SAVED</b>\n\nAdd more files to this link or continue?</blockquote>",
        'btn_add': "➕ Add another", 'btn_cont': "➡️ Continue", 'btn_cancel': "❌ Cancel",
        'send_thumb': "<blockquote>🖼 <b>THUMBNAIL</b>\n\nSend the image for the download stream.</blockquote>",
        'send_res': "<blockquote>🎬 <b>VIDEO QUALITY</b>\n\nSelect the resolution for this link:</blockquote>",
        'send_author': "<blockquote>👤 <b>CREATOR</b>\n\nSelect who is uploading this content:</blockquote>",
        'config': "<blockquote>⚙️ <b>SETTINGS</b>\n\nAdjust the link parameters before creation:</blockquote>",
        'btn_fsub': "📢 ForceSub Channel", 'btn_prot': "🛡 Anti-Forward: ",
        'btn_gen': "💎 Generate Link", 'send_fsub': "<blockquote>✍️ <b>MANDATORY CHANNEL</b>\n\nSend @username or ID of the required channel.</blockquote>",
        'link_ready': "<blockquote>🎉 <b>LINK READY!</b>\n\n🔗 <b>Link:</b>\n<code>https://t.me/{}?start={}</code></blockquote>",
        'stats': "<blockquote>📊 <b>STATISTICS</b>\n\n🔗 Active Links: <b>{}</b>\n🚫 Banned Users: <b>{}</b></blockquote>",
        'deleted': "<blockquote>🗑 <b>CLEANUP COMPLETE</b>\n\nAll links purged successfully.</blockquote>",
        'btn_create': "➕ Create Link", 'btn_stats': "📊 Statistics", 'btn_lang': "🌐 Language",
        'btn_style': "🎨 Progress Style", 'btn_dellinks': "🗑 Purge Links"
    },
    'ar': {
        'panel': "<blockquote>🔧 <b>لوحة التحكم</b>\n\nمرحباً. من هنا يمكنك إدارة الروابط وإعدادات البوت.\n\nاختر خياراً:</blockquote>",
        'send_file': "<blockquote>📤 <b>رفع الملفات</b>\n\nأرسل الملف، الفيديو أو المستند (الحد الأقصى 4 جيجابايت).</blockquote>",
        'options': "<blockquote>✅ <b>تم حفظ الملف</b>\n\nهل تريد إضافة المزيد من الملفات أم المتابعة؟</blockquote>",
        'btn_add': "➕ إضافة آخر", 'btn_cont': "➡️ متابعة", 'btn_cancel': "❌ إلغاء",
        'send_thumb': "<blockquote>🖼 <b>صورة مصغرة</b>\n\nأرسل الصورة المصغرة.</blockquote>",
        'send_res': "<blockquote>🎬 <b>جودة الفيديو</b>\n\nاختر الدقة لهذا الرابط:</blockquote>",
        'send_author': "<blockquote>👤 <b>المنشئ</b>\n\nاختر من يقوم برفع هذا المحتوى:</blockquote>",
        'config': "<blockquote>⚙️ <b>الإعدادات</b>\n\nاضبط إعدادات الرابط قبل إنشائه:</blockquote>",
        'btn_fsub': "📢 قناة إجبارية", 'btn_prot': "🛡 منع التحويل: ",
        'btn_gen': "💎 إنشاء الرابط", 'send_fsub': "<blockquote>✍️ <b>قناة إجبارية</b>\n\nأرسل معرف القناة @username المطلوبة.</blockquote>",
        'link_ready': "<blockquote>🎉 <b>الرابط جاهز!</b>\n\n🔗 <b>الرابط:</b>\n<code>https://t.me/{}?start={}</code></blockquote>",
        'stats': "<blockquote>📊 <b>الإحصائيات</b>\n\n🔗 الروابط النشطة: <b>{}</b>\n🚫 المستخدمين المحظورين: <b>{}</b></blockquote>",
        'deleted': "<blockquote>🗑 <b>تم التنظيف</b>\n\nتم حذف جميع الروابط بنجاح.</blockquote>",
        'btn_create': "➕ إنشاء رابط", 'btn_stats': "📊 إحصائيات", 'btn_lang': "🌐 اللغة",
        'btn_style': "🎨 شكل التحميل", 'btn_dellinks': "🗑 حذف الروابط"
    }
}

async def safe_delete(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

def get_admin_lang():
    cursor.execute("SELECT lang, p_style FROM admin_settings WHERE id = 1")
    res = cursor.fetchone()
    return res if res else ('es', 1)

def get_main_panel_keyboard(lang_code):
    t = LANG.get(lang_code, LANG['es'])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t['btn_create'], callback_data="panel_create")],
        [InlineKeyboardButton(t['btn_stats'], callback_data="panel_stats"), InlineKeyboardButton(t['btn_lang'], callback_data="panel_lang")],
        [InlineKeyboardButton(t['btn_style'], callback_data="panel_style"), InlineKeyboardButton(t['btn_dellinks'], callback_data="panel_dellinks")]
    ])

# ================= COMANDOS =================
@app.on_message(filters.command("addadmin") & filters.user(OWNER_ID))
async def add_admin_cmd(client, message):
    await safe_delete(message)
    if len(message.command) < 2:
        return await client.send_message(OWNER_ID, "<blockquote>⚠️ <b>USO:</b> /addadmin [ID_DEL_USUARIO]</blockquote>")
    new_admin = int(message.command[1])
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin,))
    conn.commit()
    await client.send_message(OWNER_ID, f"<blockquote>✅ <b>NUEVO ADMIN AÑADIDO:</b> <code>{new_admin}</code></blockquote>")

@app.on_message(filters.command("deladmin") & filters.user(OWNER_ID))
async def del_admin_cmd(client, message):
    await safe_delete(message)
    if len(message.command) < 2:
        return await client.send_message(OWNER_ID, "<blockquote>⚠️ <b>USO:</b> /deladmin [ID_DEL_USUARIO]</blockquote>")
    old_admin = int(message.command[1])
    if old_admin == OWNER_ID:
        return await client.send_message(OWNER_ID, "<blockquote>❌ No puedes eliminar al creador del bot.</blockquote>")
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (old_admin,))
    conn.commit()
    await client.send_message(OWNER_ID, f"<blockquote>🗑 <b>ADMIN ELIMINADO:</b> <code>{old_admin}</code></blockquote>")

@app.on_message(filters.command(["ban", "unban"]))
async def ban_user(client, message):
    if not is_admin(message.from_user.id): return
    await safe_delete(message)
    
    if len(message.command) < 2:
        return await client.send_message(message.from_user.id, "<blockquote>⚠️ <b>USO:</b> /ban [ID] o /unban [ID]</blockquote>")
    
    target_id = int(message.command[1])
    is_ban = True if message.command[0] == "ban" else False
    cursor.execute("INSERT OR REPLACE INTO users (user_id, banned) VALUES (?, ?)", (target_id, is_ban))
    conn.commit()
    
    estado = 'bloqueado 🚫' if is_ban else 'desbloqueado ✅'
    await client.send_message(message.from_user.id, f"<blockquote>🛡 <b>MODERACIÓN:</b>\n\nEl usuario <code>{target_id}</code> ha sido {estado}.</blockquote>")

# ================= INICIO =================
@app.on_message(filters.command("start") & filters.private)
async def handle_start(client: Client, message: Message):
    user_id = message.from_user.id
    lang_code, _ = get_admin_lang()
    t = LANG.get(lang_code, LANG['es'])

    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if res and res[0]:
        await safe_delete(message)
        return await client.send_message(user_id, USER_MSG['banned'])

    if len(message.command) < 2:
        if is_admin(user_id):
            await safe_delete(message)
            return await client.send_message(user_id, t['panel'], reply_markup=get_main_panel_keyboard(lang_code))
        else:
            await safe_delete(message)
            return await client.send_message(user_id, USER_MSG['no_link'])

    link_id = message.command[1]
    cursor.execute("SELECT * FROM links WHERE link_id = ?", (link_id,))
    link_data = cursor.fetchone()

    await safe_delete(message)

    if not link_data:
        return await client.send_message(user_id, USER_MSG['invalid'])

    fsub = link_data[3]
    if fsub:
        try:
            member = await client.get_chat_member(fsub, user_id)
            if member.status in [enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT]:
                raise UserNotParticipant()
        except UserNotParticipant:
            pending_users[user_id] = link_id
            fsub_clean = fsub.replace("@", "")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(USER_MSG['fsub_btn'], url=f"https://t.me/{fsub_clean}")]])
            return await client.send_message(user_id, USER_MSG['fsub_msg'].format(fsub), reply_markup=kb)
        except Exception:
            pending_users[user_id] = link_id
            fsub_clean = fsub.replace("@", "")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(USER_MSG['fsub_btn'], url=f"https://t.me/{fsub_clean}")]])
            return await client.send_message(user_id, USER_MSG['fsub_msg'].format(fsub), reply_markup=kb)

    await send_user_files(client, user_id, link_data)

@app.on_message(filters.command(["panel", "kai"]))
async def open_panel(client, message):
    if not is_admin(message.from_user.id): return
    await safe_delete(message)
    lang_code, _ = get_admin_lang()
    await message.reply_text(LANG[lang_code]['panel'], reply_markup=get_main_panel_keyboard(lang_code))

# ================= CALLBACKS =================
@app.on_callback_query()
async def admin_callbacks(client, callback):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        return await callback.answer("Access Denied.", show_alert=True)

    data = callback.data
    lang_code, _ = get_admin_lang()
    t = LANG.get(lang_code, LANG['es'])

    if data.startswith("log_ban_"):
        target_id = int(data.split("_")[2])
        cursor.execute("INSERT OR REPLACE INTO users (user_id, banned) VALUES (?, ?)", (target_id, True))
        conn.commit()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ User Banned", callback_data="log_already_banned")]])
        try:
            await callback.message.edit_reply_markup(kb)
            await callback.answer(f"User {target_id} has been banned successfully.", show_alert=True)
        except Exception as e:
            logger.error(f"Error updating log button: {e}")
            await callback.answer("User banned, but couldn't update the button.", show_alert=True)
        return
        
    elif data == "log_already_banned":
        return await callback.answer("This user is already banned.", show_alert=True)

    await callback.answer()

    if data == "panel_create":
        admin_states[user_id] = {'step': 'WAIT_FILE', 'files': [], 'thumb': None, 'fsub': None, 'protect': False, 'resolution': '1080p', 'author': 'KAI', 'prompt_msg_id': callback.message.id}
        await callback.message.edit_text(t['send_file'])
    
    elif data == "panel_stats":
        cursor.execute("SELECT COUNT(*) FROM links")
        total_links = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
        total_banned = cursor.fetchone()[0]
        await callback.message.edit_text(t['stats'].format(total_links, total_banned), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="panel_home")]]))

    elif data == "panel_lang":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇪🇸 Español", callback_data="setlang_es"), InlineKeyboardButton("🇺🇸 English", callback_data="setlang_en")],
            [InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar")],
            [InlineKeyboardButton("🔙", callback_data="panel_home")]
        ])
        await callback.message.edit_text("<blockquote>🌐 <b>IDIOMA / LANGUAGE:</b>\n\nSelecciona una opción:</blockquote>", reply_markup=kb)

    elif data.startswith("setlang_"):
        new_lang = data.split("_")[1]
        cursor.execute("UPDATE admin_settings SET lang = ? WHERE id = 1", (new_lang,))
        conn.commit()
        await callback.message.edit_text(LANG[new_lang]['panel'], reply_markup=get_main_panel_keyboard(new_lang))

    elif data == "panel_style":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Clásico (░ █)", callback_data="setstyle_1"), InlineKeyboardButton("Minimalista (□ ■)", callback_data="setstyle_2")],
            [InlineKeyboardButton("Elegante (▱ ▰)", callback_data="setstyle_3"), InlineKeyboardButton("Premium (🤍 💙)", callback_data="setstyle_4")],
            [InlineKeyboardButton("🔙", callback_data="panel_home")]
        ])
        await callback.message.edit_text("<blockquote>🎨 <b>BARRA DE PROGRESO:</b>\n\nElige la estética visual para las descargas:</blockquote>", reply_markup=kb)

    elif data.startswith("setstyle_"):
        new_style = int(data.split("_")[1])
        cursor.execute("UPDATE admin_settings SET p_style = ? WHERE id = 1", (new_style,))
        conn.commit()
        await callback.message.edit_text("<blockquote>✅ <b>ESTILO GUARDADO CORRECTAMENTE</b></blockquote>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="panel_home")]]))

    elif data == "panel_dellinks":
        cursor.execute("DELETE FROM links")
        conn.commit()
        await callback.message.edit_text(t['deleted'], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="panel_home")]]))

    elif data == "panel_home":
        await callback.message.edit_text(t['panel'], reply_markup=get_main_panel_keyboard(lang_code))

    elif data == "action_add":
        admin_states[user_id]['step'] = 'WAIT_FILE'
        await callback.message.edit_text(t['send_file'])
    
    elif data == "action_cont":
        admin_states[user_id]['step'] = 'WAIT_THUMB'
        await callback.message.edit_text(t['send_thumb'])
        
    elif data == "action_cancel":
        admin_states.pop(user_id, None)
        await callback.message.edit_text(t['panel'], reply_markup=get_main_panel_keyboard(lang_code))
        
    elif data.startswith("setres_"):
        res = data.split("_")[1]
        admin_states[user_id]['resolution'] = res
        admin_states[user_id]['step'] = 'WAIT_AUTHOR'
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 KAI", callback_data="setauthor_KAI"), InlineKeyboardButton("⚡ ALEYXZ", callback_data="setauthor_ALEYXZ")]
        ])
        await callback.message.edit_text(t['send_author'], reply_markup=kb)

    elif data.startswith("setauthor_"):
        author = data.split("_")[1]
        admin_states[user_id]['author'] = author
        admin_states[user_id]['step'] = 'CONFIG'
        await render_config_panel(callback.message, user_id)

    elif data == "config_fsub":
        admin_states[user_id]['step'] = 'WAIT_FSUB'
        await callback.message.edit_text(t['send_fsub'])
        
    elif data == "config_prot":
        state = admin_states[user_id]
        state['protect'] = not state['protect']
        await render_config_panel(callback.message, user_id)
        
    elif data == "config_gen":
        state = admin_states[user_id]
        link_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=10))
        bot_info = await client.get_me()
        
        cursor.execute("INSERT INTO links VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                       (link_id, json.dumps(state['files']), state['thumb'], state['fsub'], state['protect'], state['resolution'], state['author'], ""))
        conn.commit()
        
        await callback.message.edit_text(t['link_ready'].format(bot_info.username, link_id), reply_markup=get_main_panel_keyboard(lang_code))
        admin_states.pop(user_id, None)

async def render_config_panel(message: Message, user_id):
    lang_code, _ = get_admin_lang()
    t = LANG[lang_code]
    state = admin_states.get(user_id)
    
    prot_status = "ACTIVADO 🟢" if state['protect'] else "DESACTIVADO 🔴"
    fsub_status = f"✅ {state['fsub']}" if state['fsub'] else "📢 Añadir ForceSub"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(fsub_status, callback_data="config_fsub")],
        [InlineKeyboardButton(t['btn_prot'] + prot_status, callback_data="config_prot")],
        [InlineKeyboardButton(t['btn_gen'], callback_data="config_gen")],
        [InlineKeyboardButton("❌ Cancelar Operación", callback_data="action_cancel")]
    ])
    
    try:
        await message.edit_text(t['config'], reply_markup=kb)
    except MessageNotModified:
        pass

# ================= CAPTURA DE ARCHIVOS =================
@app.on_message(filters.document | filters.video | filters.audio)
async def receive_file(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    state = admin_states.get(user_id)
    
    if state and state['step'] == 'WAIT_FILE':
        media = message.document or message.video or message.audio
        media_type = "video" if message.video else "document" if message.document else "audio"
        
        file_caption = ""
        if message.caption:
            try:
                file_caption = message.caption.html
            except AttributeError:
                file_caption = message.caption
        
        state['files'].append({
            "id": media.file_id, 
            "type": media_type, 
            "caption": file_caption
        })
        
        await safe_delete(message)
        
        lang_code, _ = get_admin_lang()
        t = LANG[lang_code]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['btn_add'], callback_data="action_add"), InlineKeyboardButton(t['btn_cont'], callback_data="action_cont")],
            [InlineKeyboardButton(t['btn_cancel'], callback_data="action_cancel")]
        ])
        
        prompt_id = state.get('prompt_msg_id')
        if prompt_id:
            try:
                await client.edit_message_text(user_id, prompt_id, t['options'], reply_markup=kb)
            except MessageNotModified:
                pass
            except Exception:
                msg = await message.reply_text(t['options'], reply_markup=kb)
                state['prompt_msg_id'] = msg.id
        else:
            msg = await message.reply_text(t['options'], reply_markup=kb)
            state['prompt_msg_id'] = msg.id

@app.on_message(filters.photo)
async def receive_thumb(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    state = admin_states.get(user_id)
    if state and state['step'] == 'WAIT_THUMB':
        state['thumb'] = message.photo.file_id
        
        state['step'] = 'WAIT_RES' 
        await safe_delete(message)
        
        lang_code, _ = get_admin_lang()
        t = LANG[lang_code]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 4K", callback_data="setres_4K"), InlineKeyboardButton("📺 1080p", callback_data="setres_1080p")],
            [InlineKeyboardButton("🖥📺 4K/1080p", callback_data="setres_4K/1080p")]
        ])
        
        prompt_id = state.get('prompt_msg_id')
        if prompt_id:
            try:
                await client.edit_message_text(user_id, prompt_id, t['send_res'], reply_markup=kb)
            except MessageNotModified:
                pass
            except Exception:
                msg = await message.reply_text(t['send_res'], reply_markup=kb)
                state['prompt_msg_id'] = msg.id
        else:
            msg = await message.reply_text(t['send_res'], reply_markup=kb)
            state['prompt_msg_id'] = msg.id

@app.on_message(filters.text & ~filters.command(["start", "panel", "kai", "ban", "unban", "addadmin", "deladmin"]))
async def receive_text_inputs(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    state = admin_states.get(user_id)
    if not state: return
    
    if state['step'] == 'WAIT_FSUB':
        state['fsub'] = message.text.strip()
        state['step'] = 'CONFIG'
        
        await safe_delete(message)
        
        prompt_id = state.get('prompt_msg_id')
        if prompt_id:
            try:
                msg = await client.get_messages(user_id, prompt_id)
                await render_config_panel(msg, user_id)
            except Exception:
                await render_config_panel(await message.reply_text("..."), user_id)

# ================= ENTREGA, AUTO-ELIMINACIÓN Y SISTEMA DE LOGS =================
@app.on_chat_member_updated()
async def auto_verify(client, event: ChatMemberUpdated):
    user_id = event.new_chat_member.user.id if event.new_chat_member else None
    if not user_id or user_id not in pending_users: return
        
    if event.new_chat_member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        link_id = pending_users[user_id]
        cursor.execute("SELECT * FROM links WHERE link_id = ?", (link_id,))
        link_data = cursor.fetchone()
        
        if link_data and link_data[3]:
            if str(event.chat.id) == str(link_data[3]) or event.chat.username == link_data[3].replace("@", ""):
                del pending_users[user_id]
                confirm_msg = await client.send_message(user_id, USER_MSG['verify'])
                await asyncio.sleep(2)
                await safe_delete(confirm_msg)
                await send_user_files(client, user_id, link_data)

async def send_log_to_channel(client, user_id, link_id):
    try:
        cursor.execute("INSERT INTO downloads (user_id, link_id) VALUES (?, ?)", (user_id, link_id))
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM downloads WHERE user_id = ? AND link_id = ?", (user_id, link_id))
        specific_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM downloads WHERE user_id = ?", (user_id,))
        total_count = cursor.fetchone()[0]

        user_info = await client.get_users(user_id)
        username = f"@{user_info.username}" if user_info.username else "<i>No username</i>"
        full_name = f"{user_info.first_name or ''} {user_info.last_name or ''}".strip()
        
        now_utc = datetime.now(timezone.utc)
        arab_tz = timezone(timedelta(hours=3))
        mex_tz = timezone(timedelta(hours=-6))
        
        arab_time = now_utc.astimezone(arab_tz).strftime("%Y-%m-%d %H:%M:%S")
        mex_time = now_utc.astimezone(mex_tz).strftime("%Y-%m-%d %H:%M:%S")

        log_caption = f"""<blockquote>🚨 <b>NEW REQUEST DETECTED</b>

🆔 <b>User ID:</b> <code>{user_id}</code>
👤 <b>Name:</b> <a href="tg://user?id={user_id}">{full_name}</a>
🔖 <b>Username:</b> {username}

📁 <b>Requested File:</b> <code>{link_id}</code>
🕐 <b>Time (Arab):</b> {arab_time}
🕐 <b>Time (Mexico):</b> {mex_time}

🔢 <b>Specific file requests:</b> {specific_count}
📊 <b>Total user requests:</b> {total_count}</blockquote>"""

        ban_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Ban User", callback_data=f"log_ban_{user_id}")]
        ])

        photo_sent = False
        async for photo in client.get_chat_photos(user_id, limit=1):
            await client.send_photo(LOG_CHANNEL_ID, photo.file_id, caption=log_caption, reply_markup=ban_kb)
            photo_sent = True
            break
            
        if not photo_sent:
            await client.send_message(LOG_CHANNEL_ID, log_caption, disable_web_page_preview=True, reply_markup=ban_kb)
            
    except Exception as e:
        logger.error(f"Error al enviar log al canal {LOG_CHANNEL_ID}: {e}")

async def send_user_files(client, chat_id, link_data):
    link_id_code = link_data[0]
    asyncio.create_task(send_log_to_channel(client, chat_id, link_id_code))

    files_data = json.loads(link_data[1])
    thumb_id = link_data[2]
    protect = link_data[4]
    
    resolution = link_data[5] if len(link_data) > 5 else "1080p"
    author_name = link_data[6] if len(link_data) > 6 else "KAI"
    
    if author_name == "KAI":
        author_html = '<a href="tg://user?id=8929826850">KAI</a>'
    else:
        author_html = '<a href="tg://user?id=8693298052">ALEYXZ</a>'

    _, style_id = get_admin_lang()
    empty, fill = PROGRESS_STYLES.get(style_id, ["░", "█"])
    
    # Reducción de animaciones (de 10 iteraciones a 4) para evitar errores FloodWait y el congelamiento del panel
    estados = {
        25: "<i>Initializing secure connection...</i>",
        50: "<i>Fetching high-quality media...</i>",
        75: "<i>Processing video data...</i>",
        100: "<i>Ready! Sending media...</i>"
    }
    
    initial_text = f"<blockquote>💎 <b>STORAGE</b>\n<code>[{empty*10}]</code> <b>0%</b>\n\n<i>Loading...</i>\n\n🎬 <b>RESOLUTION:</b> {resolution}\n👤 <b>BY:</b> {author_html}</blockquote>"
    
    try:
        if thumb_id:
            msg = await client.send_photo(chat_id, photo=thumb_id, caption=initial_text)
        else:
            msg = await client.send_message(chat_id, initial_text)
            
        for i in range(1, 5):
            await asyncio.sleep(0.8)
            pct = i * 25
            bars = fill * int(pct/10) + empty * (10 - int(pct/10))
            estado_actual = estados[pct]
            
            texto = f"<blockquote>💎 <b>STORAGE</b>\n<code>[{bars}]</code> <b>{pct}%</b>\n\n{estado_actual}\n\n🎬 <b>RESOLUTION:</b> {resolution}\n👤 <b>BY:</b> {author_html}</blockquote>"
            
            try:
                if thumb_id:
                    await msg.edit_caption(texto)
                else:
                    await msg.edit_text(texto)
            except MessageNotModified:
                pass
            
        await safe_delete(msg)
    except Exception as e:
        logger.error(f"Error en barra de progreso: {e}")
    
    sent_msgs = []
    
    for f in files_data:
        try:
            file_cap = f.get('caption', "")
            if f['type'] == 'video':
                m = await client.send_video(chat_id, f['id'], caption=file_cap, protect_content=protect)
            elif f['type'] == 'audio':
                m = await client.send_audio(chat_id, f['id'], caption=file_cap, protect_content=protect)
            else:
                m = await client.send_document(chat_id, f['id'], caption=file_cap, protect_content=protect)
            sent_msgs.append(m.id)
        except Exception as e:
            logger.error(f"Error enviando media: {e}")
            
    warning_msg = await client.send_message(chat_id, USER_MSG['warning'])
    sent_msgs.append(warning_msg.id)
    
    # 600 Segundos = 10 Minutos para auto-eliminación
    asyncio.create_task(delete_later(client, chat_id, sent_msgs, 600))

async def delete_later(client, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_ids)
        info_msg = await client.send_message(chat_id, USER_MSG['expired'])
        await asyncio.sleep(10)
        await safe_delete(info_msg)
    except Exception as e:
        logger.error(f"Error borrando mensajes: {e}")

if __name__ == "__main__":
    logger.info("Bot Iniciado y Corregido...")
    app.run()


