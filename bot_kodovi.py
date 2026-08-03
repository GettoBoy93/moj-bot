import os
import re
import time
import json
import logging
import html
import requests
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fajlovi za trajno čuvanje podataka na serveru
DATA_FILE = "active_codes.json"
STATUS_FILE = "founder_statuses.json"
CHAT_ID_FILE = "last_chat_id.json"

ACTIVE_CODES = {}
FOUNDER_STATUSES = {}

# Vremenska zona za naše podsetnike (Srbija)
TZ = ZoneInfo("Europe/Belgrade")

# Raspored foundera sa satnicama
SCHEDULE = [
    ("06:00", "@Roboda66"),
    ("07:00", "@jagodica113"),
    ("08:00", "@PeroPericaVezo"),
    ("09:00", "@Jovanj79"),
    ("10:00", "@Josip0107"),
    ("11:00", "@rajder987"),
    ("12:00", "@Stuxnet992"),
    ("13:00", "@RaDe013"),
    ("14:00", "@Alessandro1973Vuk"),
    ("15:00", "@Goran1974m"),
    ("16:00", "@dulehak"),
    ("17:00", "@Bahro67"),
    ("18:00", "@evanescence83"),
    ("19:00", "@Djenedjenee"),
    ("20:00", "@aei123_AI"),
    ("21:00", "@Snave31"),
    ("22:00", "@PERIABOY"),
    ("23:00", "@Iken2014"),
]

# SVIH ZVANIČNIH FOUNDER-A
FOUNDERS = [
    "@PERIABOY",
    "@jagodica113",
    "@Alessandro1973Vuk",
    "@Djenedjenee",
    "@Goran1974m",
    "@Bahro67",
    "@Stuxnet992",
    "@Josip0107",
    "@Snave31",
    "@evanescence83",
    "@rajder987",
    "@PeroPericaVezo",
    "@Iken2014",
    "@aei123_AI",
    "@AleksandarVujic",
    "@Roboda66",
    "@dulehak",
    "@RaDe013",
    "@Jovanj79",
    "@G_Nensyy"
]

def load_codes():
    """Učitava sačuvane kodove iz JSON fajla prilikom pokretanja bota."""
    global ACTIVE_CODES
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                ACTIVE_CODES = json.load(f)
            logger.info(f"Aktivni kodovi uspešno učitani iz fajla. Ukupno: {len(ACTIVE_CODES)}")
        except Exception as e:
            logger.error(f"Greška pri učitavanju kodova: {e}")
            ACTIVE_CODES = {}
    else:
        ACTIVE_CODES = {}

def save_codes():
    """Čuva trenutne aktivne kodove u JSON fajl."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(ACTIVE_CODES, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Greška pri čuvanju kodova: {e}")

def load_statuses():
    """Učitava dnevne statuse slanja kodova."""
    global FOUNDER_STATUSES
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                FOUNDER_STATUSES = json.load(f)
        except Exception as e:
            logger.error(f"Greška pri učitavanju statusa: {e}")
            FOUNDER_STATUSES = {}
    else:
        FOUNDER_STATUSES = {}

def save_statuses():
    """Čuva dnevne statuse slanja kodova."""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(FOUNDER_STATUSES, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Greška pri čuvanju statusa: {e}")

def save_chat_id(chat_id):
    """Čuva ID poslednjeg aktivnog četa/grupe za slanje podsetnika."""
    try:
        with open(CHAT_ID_FILE, "w", encoding="utf-8") as f:
            json.dump({"chat_id": chat_id}, f)
    except Exception as e:
        logger.error(f"Greška pri čuvanju chat_id: {e}")

def get_chat_id():
    """Učitava sačuvani chat ID grupe."""
    if os.path.exists(CHAT_ID_FILE):
        try:
            with open(CHAT_ID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("chat_id")
        except Exception:
            return None
    return None

def get_current_game_date():
    """Dan se resetuje u 02:00 ujutru po našem vremenu. Sve pre 02:00 pripada prethodnom danu."""
    now = datetime.now(TZ)
    if now.hour < 2:
        game_date = (now - timedelta(days=1)).date()
    else:
        game_date = now.date()
    return str(game_date)

def get_founder_status(username: str) -> bool:
    """Proverava da li je founder poslao kod danas (True = poslao/X, False = čeka/⏳)."""
    load_statuses()
    g_date = get_current_game_date()
    if g_date not in FOUNDER_STATUSES:
        FOUNDER_STATUSES[g_date] = {}
    return FOUNDER_STATUSES[g_date].get(username.lower(), False)

def set_founder_status(username: str, status: bool):
    """Postavlja status slanja koda za foundera za tekući dan."""
    load_statuses()
    g_date = get_current_game_date()
    if g_date not in FOUNDER_STATUSES:
        FOUNDER_STATUSES[g_date] = {}
    FOUNDER_STATUSES[g_date][username.lower()] = status
    save_statuses()

def check_is_founder(user) -> bool:
    """Proverava da li je korisnik osnivač (case-insensitive, sa ili bez @)."""
    if not user or not user.username:
        return False
    
    user_uname = f"@{user.username.lstrip('@')}".lower()
    founders_lower = [str(f).lower() for f in FOUNDERS]
    
    return user_uname in founders_lower


def get_group_status_from_web(code: str):
    """Proverava status koda na sajtu."""
    url = f"https://miningperia.com/pages/join.php?custom={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return "Nepoznato", "Aktivna", False

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text()
        page_text_lower = page_text.lower()
        
        bad_phrases = [
            "already started or is full", 
            "is full", 
            "has already started", 
            "group code is invalid", 
            "is invalid",
            "invalid code"
        ]
        if any(phrase in page_text_lower for phrase in bad_phrases):
            return "Nevažeći", "Nevažeći / Pun kod", True

        members_text = "Aktivna"
        match = re.search(r'(\d+)\s+joined', page_text, re.IGNORECASE)
        if match:
            members_text = f"{match.group(1)} članova"

        return "", members_text, False

    except Exception as e:
        logger.error(f"Greška pri parsiranju sajta za kod {code}: {e}")
        return "Greška", "N/A", False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Odgovor na /start komandu."""
    if update.effective_chat:
        save_chat_id(update.effective_chat.id)

    await update.message.reply_text(
        "👋 Zdravo! Dobrodošli u MiningPeria promo bot.\n\n"
        "Upotrebite komandu /aktivno da vidite trenutno dostupne promo kodove!"
    )


async def aktivno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Komanda /aktivno otvorena za sve korisnike."""
    if update.effective_chat:
        save_chat_id(update.effective_chat.id)

    load_codes()

    if not ACTIVE_CODES:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    current_time = time.time()
    valid_codes = {}
    expired_found = False

    for code, data in list(ACTIVE_CODES.items()):
        created_at = data.get("created_at", current_time)
        elapsed_seconds = current_time - created_at

        if elapsed_seconds >= 3600:
            expired_found = True
            continue

        _, _, is_invalid_or_full = get_group_status_from_web(code)
        if is_invalid_or_full:
            expired_found = True
            continue

        valid_codes[code] = data

    if expired_found:
        ACTIVE_CODES.clear()
        ACTIVE_CODES.update(valid_codes)
        save_codes()

    if not ACTIVE_CODES:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    poruka = "📊 <b>PREGLED AKTIVNIH PROMO KODOVA:</b>\n\n"
    poruka_plain = "📊 PREGLED AKTIVNIH PROMO KODOVA:\n\n"
    keyboard = []
    index = 1

    for code, data in ACTIVE_CODES.items():
        created_at = data.get("created_at", current_time)
        elapsed_seconds = current_time - created_at
        remaining_seconds = 3600 - elapsed_seconds

        remaining_minutes = max(1, int(remaining_seconds // 60))
        founder_display = str(data.get("founder", "Osnivač"))
        founder_safe = html.escape(founder_display)
        
        _, members_info, _ = get_group_status_from_web(code)
        generated_link = f"https://miningperia.com/pages/join.php?custom={code}"

        poruka += (
            f"🔹 <b>Promo Kod #{index}</b> (Founder: {founder_safe})\n"
            f"   • Preostalo vreme: <b>{remaining_minutes} min</b>\n"
            f"   • Status/Članovi: <b>{members_info}</b>\n"
            f"----------------------------------\n"
        )
        poruka_plain += (
            f"🔹 Promo Kod #{index} (Founder: {founder_display})\n"
            f"   • Preostalo vreme: {remaining_minutes} min\n"
            f"   • Status/Članovi: {members_info}\n"
            f"----------------------------------\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"🚀 Preuzmi Kod #{index}", url=generated_link)
        ])
        index += 1

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.message.reply_text(poruka, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Greška pri slanju HTML poruke u /aktivno: {e}")
        await update.message.reply_text(poruka_plain, reply_markup=reply_markup)


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Komanda /lista za prikaz rasporeda foundera i statusa slanja kodova."""
    if update.effective_chat:
        save_chat_id(update.effective_chat.id)

    g_date = get_current_game_date()
    text = f"📊 <b>RASPORED FOUNDERA ({g_date})</b>\n\n"

    for time_str, username in SCHEDULE:
        has_sent = get_founder_status(username)
        icon = '❌' if has_sent else '⏳'
        text += f"<code>{time_str}</code> | {username} | {icon}\n"

    try:
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Greška pri slanju /lista poruke: {e}")


async def founder_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """Pozadinski zadatak za slanje podsetnika 15 minuta pre termina."""
    job_data = context.job.data
    username = job_data["username"]
    original_time = job_data["original_time"]

    logger.info(f"Pokrenut reminder job za {username} (termin: {original_time})")

    # Ako je founder već poslao kod danas, ne šaljemo podsetnik
    if get_founder_status(username):
        logger.info(f"Founder {username} je već poslao kod danas, podsetnik preskočen.")
        return

    chat_id = get_chat_id()
    if not chat_id:
        logger.error("GREŠKA: Nema sačuvanog chat_id za slanje podsetnika! Pošaljite poruku ili komandu u grupu da bot zabeleži čet.")
        return

    text = f"Hej {username}, u {original_time} je tvoj red za kod!"
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
        logger.info(f"Uspešno poslat podsetnik za {username} na chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Greška pri slanju podsetnika za {username}: {e}")


def setup_reminders(app):
    """Podešava dnevne podsetnike 15 minuta pre svakog termina iz rasporeda u lokalnoj vremenskoj zoni."""
    if not app.job_queue:
        return
    for time_str, username in SCHEDULE:
        h, m = map(int, time_str.split(":"))
        # Kreiramo datetime objekat sa našom vremenskom zonom i oduzimamo 15 minuta
        dt = datetime(2026, 1, 1, h, m, tzinfo=TZ) - timedelta(minutes=15)
        reminder_time = dt.time()

        app.job_queue.run_daily(
            founder_reminder_job,
            time=reminder_time,
            data={"username": username, "original_time": time_str},
            name=f"reminder_{username}"
        )
    logger.info("Uspešno postavljeni svi dnevni podsetnici za foundere.")


async def background_group_check_job(context: ContextTypes.DEFAULT_TYPE):
    """Pozadinski zadatak za proveru isteka i statusa kodova."""
    load_codes()
    if not ACTIVE_CODES:
        return

    current_time = time.time()
    codes_to_remove = []

    for code, data in list(ACTIVE_CODES.items()):
        if current_time - data.get("created_at", current_time) >= 3600:
            codes_to_remove.append(code)
            continue

        _, _, is_invalid_or_full = get_group_status_from_web(code)
        if is_invalid_or_full:
            codes_to_remove.append(code)
            founder_name = data.get("founder", "Osnivač")
            chat_id = data.get("chat_id")
            if chat_id:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ <b>Kod {code} (Founder: {founder_name}) je nevažeći ili je grupa puna!</b>\nKod je uklonjen iz aktivnih.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Greška pri slanju obaveštenja: {e}")

    if codes_to_remove:
        for code in codes_to_remove:
            if code in ACTIVE_CODES:
                del ACTIVE_CODES[code]
        save_codes()
        logger.info(f"Pozadinski job uklonio nevažeće/pune kodove: {codes_to_remove}")


async def obrisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Komanda /obrisi KOD ili /del KOD za osnivače."""
    if update.effective_chat:
        save_chat_id(update.effective_chat.id)

    user = update.effective_user

    if not check_is_founder(user):
        await update.message.reply_text("❌ Ova komanda je rezervisana samo za osnivače.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Primer upotrebe: /obrisi GH7M6C ili /del GH7M6C")
        return

    code_to_delete = context.args[0].strip().upper()

    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Nije moguće obrisati komandu osnivača: {e}")

    load_codes()
    if code_to_delete in ACTIVE_CODES:
        del ACTIVE_CODES[code_to_delete]
        save_codes()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Promo kod {code_to_delete} je uspešno uklonjen iz aktivnih kodova."
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Kod {code_to_delete} nije pronađen među aktivnim kodovima."
        )


async def auto_expire_code(context: ContextTypes.DEFAULT_TYPE):
    """Automatsko brisanje koda iz memorije nakon 60 minuta."""
    code = context.job.data
    load_codes()
    if code in ACTIVE_CODES:
        del ACTIVE_CODES[code]
        save_codes()
        logger.info(f"Kod {code} je automatski istekao i obrisan je posle 60 minuta.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if update.effective_chat:
        save_chat_id(update.effective_chat.id)

    text = update.message.text.strip()
    user = update.effective_user

    if check_is_founder(user):
        code = text.upper()
        
        if code.startswith("/KOD "):
            parts = code.split(maxsplit=1)
            if len(parts) > 1:
                code = parts[1].strip()

        is_valid_format = bool(re.fullmatch(r'^(?=.*[A-Z])[A-Z0-9]{6}$', code))

        if is_valid_format:
            _, _, is_invalid_or_full = get_group_status_from_web(code)
            if is_invalid_or_full:
                try:
                    await update.message.delete()
                except Exception:
                    pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Kod <b>{code}</b> je <b>nevažeći</b> ili je grupa već <b>puna</b> na sajtu! Nije prihvaćen.",
                    parse_mode="HTML"
                )
                return

            founder_name = f"@{user.username}" if user.username else user.first_name

            load_codes()
            ACTIVE_CODES[code] = {
                "founder": founder_name,
                "created_at": time.time(),
                "chat_id": update.effective_chat.id
            }
            save_codes()

            # Zabeleži da je founder uspešno poslao kod za danas (prebacuje na ❌)
            if user.username:
                set_founder_status(f"@{user.username}", True)

            if context.job_queue:
                context.job_queue.run_once(
                    auto_expire_code,
                    when=3600,
                    data=code,
                    name=f"expire_{code}"
                )

            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Nije moguće obrisati poruku: {e}")

            generated_link = f"https://miningperia.com/pages/join.php?custom={code}"

            keyboard = [
                [InlineKeyboardButton("🚀 Preuzmi Kod", url=generated_link)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            founder_safe = html.escape(founder_name)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    f"🔥 <b>NOVI PROMO KOD!</b> 🔥\n\n"
                    f"Founder: <b>{founder_safe}</b>\n\n"
                    f"Kliknite na dugme ispod da preuzmete nagradu!"
                ),
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return


async def restore_jobs_on_startup(app):
    """Pri pokretanju bota obnavlja tajmere za brisanje iz trajne memorije."""
    load_codes()
    current_time = time.time()
    valid_codes = {}
    expired_found = False

    for code, data in list(ACTIVE_CODES.items()):
        created_at = data.get("created_at", current_time)
        remaining = 3600 - (current_time - created_at)

        if remaining <= 0:
            expired_found = True
        else:
            _, _, is_invalid_or_full = get_group_status_from_web(code)
            if is_invalid_or_full:
                expired_found = True
                continue

            valid_codes[code] = data
            if app.job_queue:
                app.job_queue.run_once(
                    auto_expire_code,
                    when=remaining,
                    data=code,
                    name=f"expire_{code}"
                )

    if expired_found:
        ACTIVE_CODES.clear()
        ACTIVE_CODES.update(valid_codes)
        save_codes()


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN nije podešen!")
        return

    load_codes()
    load_statuses()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("aktivno", aktivno_command))
    app.add_handler(CommandHandler("lista", lista_command))
    app.add_handler(CommandHandler(["obrisi", "del"], obrisi_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    if app.job_queue:
        setup_reminders(app)
        app.job_queue.run_once(lambda ctx: restore_jobs_on_startup(app), when=1)
        app.job_queue.run_repeating(
            background_group_check_job,
            interval=60,
            first=10,
            name="background_group_check"
        )

    logger.info("Bot uspešno pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
