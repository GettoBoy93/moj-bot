import os
import re
import time
import json
import logging
import html
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

# SVIH 15 ZVANIČNIH FOUNDER-A
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
    "@AleksandarVujic"
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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Odgovor na /start komandu."""
    await update.message.reply_text(
        "👋 Zdravo! Dobrodošli u MiningPeria promo bot.\n\n"
        "Upotrebite komandu /aktivno da vidite trenutno dostupne promo kodove!"
    )


async def aktivno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Komanda /aktivno otvorena za sve korisnike.
    Prikazuje osnivača, preostale minute do isteka koda i dugme sa linkom.
    """
    load_codes()

    if not ACTIVE_CODES:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    current_time = time.time()
    expired_codes = []
    poruka = "📊 <b>PREGLED AKTIVNIH PROMO KODOVA:</b>\n\n"
    poruka_plain = "📊 PREGLED AKTIVNIH PROMO KODOVA:\n\n"
    keyboard = []
    index = 1

    for code, data in list(ACTIVE_CODES.items()):
        created_at = data.get("created_at", current_time)
        elapsed_seconds = current_time - created_at
        remaining_seconds = 3600 - elapsed_seconds

        # Ako je prošlo više od 60 min, markiraj za brisanje
        if remaining_seconds <= 0:
            expired_codes.append(code)
            continue

        remaining_minutes = max(1, int(remaining_seconds // 60))
        founder_display = str(data.get("founder", "Osnivač"))
        founder_safe = html.escape(founder_display)
        generated_link = f"https://miningperia.com/pages/join.php?custom={code}"

        poruka += (
            f"🔹 <b>Promo Kod #{index}</b> (Founder: {founder_safe})\n"
            f"   • Preostalo: <b>{remaining_minutes} min</b>\n"
            f"----------------------------------\n"
        )
        poruka_plain += (
            f"🔹 Promo Kod #{index} (Founder: {founder_display})\n"
            f"   • Preostalo: {remaining_minutes} min\n"
            f"----------------------------------\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"🚀 Preuzmi Kod #{index}", url=generated_link)
        ])
        index += 1

    # Obrisati sve kodove koji su u međuvremenu istekli
    if expired_codes:
        for code in expired_codes:
            if code in ACTIVE_CODES:
                del ACTIVE_CODES[code]
        save_codes()

    if not keyboard:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.message.reply_text(poruka, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Greška pri slanju HTML poruke u /aktivno: {e}")
        await update.message.reply_text(poruka_plain, reply_markup=reply_markup)


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
            founder_name = f"@{user.username}" if user.username else user.first_name

            load_codes()
            ACTIVE_CODES[code] = {
                "founder": founder_name,
                "created_at": time.time()
            }
            save_codes()

            # Zakazivanje automatskog brisanja nakon 60 minuta (3600 sekundi)
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
    """
    Pri pokretanju bota obnavlja tajmere za brisanje iz trajne memorije.
    """
    load_codes()
    current_time = time.time()
    expired = []

    for code, data in list(ACTIVE_CODES.items()):
        created_at = data.get("created_at", current_time)
        remaining = 3600 - (current_time - created_at)

        if remaining <= 0:
            expired.append(code)
        else:
            if app.job_queue:
                app.job_queue.run_once(
                    auto_expire_code,
                    when=remaining,
                    data=code,
                    name=f"expire_{code}"
                )
                logger.info(f"Obnovljen tajmer za kod {code}: preostalo {int(remaining)} sekundi.")

    if expired:
        for code in expired:
            if code in ACTIVE_CODES:
                del ACTIVE_CODES[code]
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

    # Obnavljanje tajmera pri restartu
    if app.job_queue:
        app.job_queue.run_once(lambda ctx: restore_jobs_on_startup(app), when=1)

    logger.info("Bot uspešno pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
