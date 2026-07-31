import os
import re
import time
import json
import logging
import html
import requests
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

# Fajl za trajno čuvanje kodova na serveru
DATA_FILE = "active_codes.json"
ACTIVE_CODES = {}

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
    "@RaDe013"
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

def check_is_founder(user) -> bool:
    if not user:
        return False
    if user.id in FOUNDERS:
        return True
    if user.username:
        user_uname = f"@{user.username}".lower()
        founders_lower = [str(f).lower() for f in FOUNDERS]
        if user_uname in founders_lower:
            return True
    return False


def get_group_status_from_web(code: str):
    """
    Pomoćna funkcija koja preko requests i BeautifulSoup 
    čita tekst direktno sa miningperia stranice za dati kod.
    Vraća (status_text, members_text, is_invalid_or_full)
    """
    url = f"https://miningperia.com/pages/join.php?custom={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return "Nepoznato", "N/A", False

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text()
        page_text_lower = page_text.lower()
        
        # Provera da li je grupa puna, zatvorena ili je kod nevažeći
        is_invalid_or_full = False
        bad_phrases = [
            "already started or is full", 
            "is full", 
            "has already started", 
            "group code is invalid", 
            "is invalid"
        ]
        if any(phrase in page_text_lower for phrase in bad_phrases):
            is_invalid_or_full = True

        # Pokušavamo da izvučemo broj članova (npr. "8 joined")
        members_text = "Nepoznato"
        match = re.search(r'(\d+)\s+joined', page_text, re.IGNORECASE)
        if match:
            members_text = f"{match.group(1)} članova"
        else:
            if is_invalid_or_full:
                members_text = "Nevažeći / Pun kod"
            else:
                members_text = "Aktivna"

        return "", members_text, is_invalid_or_full
    except Exception as e:
        logger.error(f"Greška pri parsiranju sajta za kod {code}: {e}")
        return "Greška", "N/A", False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Odgovor na /start komandu."""
    await update.message.reply_text(
        "👋 Zdravo! Dobrodošli u MiningPeria promo bot.\n\n"
        "Upotrebite komandu /aktivno da vidite trenutno dostupne promo kodove!"
    )


async def aktivno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Komanda /aktivno otvorena za sve korisnike.
    Prikazuje osnivača, preostale minute, broj članova i dugme sa linkom.
    Automatski izbacuje kodove koji su u međuvremenu postali puni ili nevažeći.
    """
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

        # Provera sa sajta – ako je kod nevažeći ili pun, uklanjamo ga
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


async def background_group_check_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Pozadinski zadatak koji se izvršava na svakih 60 sekundi.
    Proverava sve aktivne kodove i briše nevažeće, pune ili istečene.
    """
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
                        text=f"⚠️ <b>Kod {code} (Founder: {founder_name}) je nevažeći ili puna grupa!</b>\nKod je uklonjen iz aktivnih.",
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
    """Automatsko brisanje koda iz memorije nakon 60 minuta (3600 sekundi)."""
    code = context.job.data
    load_codes()
    if code in ACTIVE_CODES:
        del ACTIVE_CODES[code]
        save_codes()
        logger.info(f"Kod {code} je automatski istekao i obrisan je posle 60 minuta.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user

    if check_is_founder(user):
        code = text.upper()
        
        if code.startswith("/KOD "):
            parts = code.split(maxsplit=1)
            if len(parts) > 1:
                code = parts[1].strip()

        # Provera formata: tačno 6 karaktera (velika slova i/ili brojevi sa bar jednim slovom)
        is_valid_format = bool(re.fullmatch(r'^(?=.*[A-Z])[A-Z0-9]{6}$', code))

        if is_valid_format:
            # Provera statusa sa sajta PRE prihvatanja koda
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
            # Provera sa sajta pri restartu
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
                logger.info(f"Obnovljen tajmer za kod {code}: preostalo {int(remaining)} sekundi.")

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

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("aktivno", aktivno_command))
    app.add_handler(CommandHandler(["obrisi", "del"], obrisi_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    if app.job_queue:
        app.job_queue.run_once(lambda ctx: restore_jobs_on_startup(app), when=1)
        app.job_queue.run_repeating(
            background_group_check_job,
            interval=60,
            first=10,
            name="background_group_check"
        )

    logger.info("Bot uspešno pokrenut sa proširenim proverama za nevažeće i pune kodove...")
    app.run_polling()

if __name__ == "__main__":
    main()
