import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
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

# SVIH 11 OSNIVAČA
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
    "@rajder987"
]

def check_is_founder(user) -> bool:
    """Proverava da li je korisnik osnivač (poređenje ignorisanem velikih/malih slova)."""
    if not user:
        return False
        
    # Provera po ID-ju (ako pošalješ svoj ID u budućnosti)
    if user.id in FOUNDERS:
        return True

    # Provera po username-u
    if user.username:
        user_uname = f"@{user.username}".lower()
        founders_lower = [f.lower() for f in FOUNDERS if isinstance(f, str)]
        if user_uname in founders_lower:
            return True

    return False


async def aktivno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not check_is_founder(user):
        # Ako iz nekog razloga ne prepozna osnivača, odštampaće u konzoli tačan ID/username radi lakše provere
        logger.warning(f"Korisnik {user.id} (@{user.username}) nije prepoznat kao founder.")
        await update.message.reply_text("❌ Ova komanda je rezervisana samo za osnivače.")
        return

    if not ACTIVE_CODES:
        await update.message.reply_text("ℹ️ Trenutno nema aktivnih promo kodova.")
        return

    poruka = "📊 **PREGLED AKTIVNIH PROMO KODOVA:**\n\n"
    for code, data in ACTIVE_CODES.items():
        poruka += (
            f"🔹 Kod: `{code}`\n"
            f"   • Iskorišćeno: **{data['current_uses']}/{data['max_uses']}**\n"
            f"   • Nagrada: {data['reward']} poena\n"
            f"----------------------------------\n"
        )

    await update.message.reply_text(poruka, parse_mode="Markdown")


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

        # Provera formata: 6 karaktera, slova i/ili brojevi
        is_valid_format = bool(re.fullmatch(r'^(?=.*[A-Z])[A-Z0-9]{6}$', code))

        if is_valid_format:
            max_uses = 30
            
            ACTIVE_CODES[code] = {
                "max_uses": max_uses,
                "current_uses": 1,
                "claimed_users": {user.id},
                "reward": 100
            }

            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Nije moguće obrisati poruku: {e}")

            keyboard = [
                [InlineKeyboardButton(f"🎁 Preuzmi kod {code}", callback_data=f"claim_{code}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    f"🔥 **NOVI PROMO KOD!** 🔥\n\n"
                    f"Kod: `{code}`\n"
                    f"Iskorišćeno: **1/{max_uses}**\n\n"
                    f"Kliknite na dugme ispod da preuzmete nagradu!"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data.startswith("claim_"):
        code = data.replace("claim_", "")

        if code not in ACTIVE_CODES:
            await query.message.reply_text("❌ Ovaj kod više nije aktivan.", quote=True)
            return

        code_data = ACTIVE_CODES[code]

        if user_id in code_data["claimed_users"]:
            await query.message.reply_text(
                "⚠️ Već ste preuzeli ovaj promo kod! Svaki korisnik može iskoristiti kod samo jednom.",
                quote=True
            )
            return

        if code_data["current_uses"] >= code_data["max_uses"]:
            await query.message.reply_text("❌ Sva mesta za ovaj kod su popunjena!", quote=True)
            return

        code_data["claimed_users"].add(user_id)
        code_data["current_uses"] += 1

        current = code_data["current_uses"]
        max_limit = code_data["max_uses"]

        keyboard = [
            [InlineKeyboardButton(f"🎁 Preuzmi kod {code}", callback_data=f"claim_{code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=(
                    f"🔥 **NOVI PROMO KOD!** 🔥\n\n"
                    f"Kod: `{code}`\n"
                    f"Iskorišćeno: **{current}/{max_limit}**\n\n"
                    f"Kliknite na dugme ispod da preuzmete nagradu!"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception:
            pass

        await query.message.reply_text(
            f"🎉 Uspešno ste preuzeli kod `{code}`!",
            parse_mode="Markdown",
            quote=True
        )


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN", "TVOJ_TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("aktivno", aktivno_command))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    logger.info("Bot pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
