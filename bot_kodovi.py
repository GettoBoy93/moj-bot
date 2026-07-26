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

# Baza aktivnih kodova u memoriji
ACTIVE_CODES = {}

# TAČNA I KOMPLETNA LISTA OSNIVAČA (11 članova)
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user
    username = f"@{user.username}" if user.username else ""

    # Provera da li je pošiljalac osnivač (preko username-a ili ID-ja)
    is_founder = (username in FOUNDERS) or (user.id in FOUNDERS)

    if is_founder:
        code = text.upper()
        
        # Ako je poslat preko komande /kod ABCDEF ili /kod GH7M5C
        if code.startswith("/KOD "):
            parts = code.split(maxsplit=1)
            if len(parts) > 1:
                code = parts[1].strip()

        # PRAVILO: Tačno 6 karaktera, mora sadržati bar jedno velika slovo (A-Z) 
        # i može sadržati brojeve (0-9). Samo čisti brojevi (npr. 123456) NE PROLAZE.
        # Prolaze: GH7M5C, ABCDEF, A1B2C3
        is_valid_format = bool(re.fullmatch(r'^(?=.*[A-Z])[A-Z0-9]{6}$', code))

        if is_valid_format:
            max_uses = 30
            
            # Kod startuje od 1/30 (Osnivač koji je objavio je prvi)
            ACTIVE_CODES[code] = {
                "max_uses": max_uses,
                "current_uses": 1,
                "claimed_users": {user.id},
                "reward": 100
            }

            # Brišemo poruku osnivača
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Nije moguće obrisati poruku: {e}")

            # Generišemo dugme za preuzimanje
            keyboard = [
                [InlineKeyboardButton(f"🎁 Preuzmi kod {code}", callback_data=f"claim_{code}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Šaljemo zvaničnu objavu sa stanjem 1/30
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

        # 1. Provera jednokratnog preuzimanja po korisniku
        if user_id in code_data["claimed_users"]:
            await query.message.reply_text(
                "⚠️ Već ste preuzeli ovaj promo kod! Svaki korisnik može iskoristiti kod samo jednom.",
                quote=True
            )
            return

        # 2. Provera popunjenosti svih 30 mesta
        if code_data["current_uses"] >= code_data["max_uses"]:
            await query.message.reply_text("❌ Sva mesta za ovaj kod su popunjena!", quote=True)
            return

        # 3. Dodajemo korisnika u listu i povećavamo brojač
        code_data["claimed_users"].add(user_id)
        code_data["current_uses"] += 1

        current = code_data["current_uses"]
        max_limit = code_data["max_uses"]

        keyboard = [
            [InlineKeyboardButton(f"🎁 Preuzmi kod {code}", callback_data=f"claim_{code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Osvežavamo prikaz brojača u poruci (sa 1/30 na 2/30...)
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

    app.add_handler(CallbackQueryHandler(handle_button_click))
    # Sluša sve tekstualne poruke (uključujući i komande poput /kod)
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    logger.info("Bot je pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
