import os
import re
import logging
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

ACTIVE_CODES = {}

# SVIH 12 OSNIVAČA + VLASNIK GRUPE
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
    "@aei123_AI"
]

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
    """Komanda /aktivno otvorena za sve korisnike."""
    if not ACTIVE_CODES:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    poruka = "📊 **PREGLED AKTIVNIH PROMO KODOVA:**\n\n"
    keyboard = []
    
    for i, (code, data) in enumerate(ACTIVE_CODES.items(), 1):
        founder_display = data.get("founder", "Osnivač")
        generated_link = f"https://miningperia.com/pages/join.php?custom={code}"
        
        poruka += (
            f"🔹 **Promo Kod #{i}** (Founder: {founder_display})\n"
            f"----------------------------------\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"🚀 Preuzmi Kod #{i}", url=generated_link)
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(poruka, reply_markup=reply_markup, parse_mode="Markdown")


async def obrisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Komanda /obrisi KOD ili /del KOD za osnivače i vlasnika.
    """
    user = update.effective_user

    if not check_is_founder(user):
        await update.message.reply_text("❌ Ova komanda je rezervisana samo za osnivače i vlasnika.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Primer upotrebe: `/obrisi GH7M6C` ili `/del GH7M6C`", parse_mode="Markdown")
        return

    code_to_delete = context.args[0].strip().upper()

    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Nije moguće obrisati komandu osnivača: {e}")

    if code_to_delete in ACTIVE_CODES:
        del ACTIVE_CODES[code_to_delete]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Promo kod `{code_to_delete}` je uspešno uklonjen iz aktivnih kodova.",
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Kod `{code_to_delete}` nije pronađen među aktivnim kodovima.",
            parse_mode="Markdown"
        )


async def auto_expire_code(context: ContextTypes.DEFAULT_TYPE):
    """Automatsko brisanje koda iz memorije nakon 60 minuta (3600 sekundi)."""
    code = context.job.data
    if code in ACTIVE_CODES:
        del ACTIVE_CODES[code]
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

            ACTIVE_CODES[code] = {
                "founder": founder_name
            }

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

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    f"🔥 **NOVI PROMO KOD!** 🔥\n\n"
                    f"Founder: **{founder_name}**\n\n"
                    f"Kliknite na dugme ispod da preuzmete nagradu!"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN nije podešen!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("aktivno", aktivno_command))
    app.add_handler(CommandHandler(["obrisi", "del"], obrisi_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    logger.info("Bot uspešno pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
