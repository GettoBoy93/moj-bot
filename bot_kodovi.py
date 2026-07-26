import os
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

# ---------------------------------------------------------
# PODEŠAVANJA I BAZA U MEMORIJI
# ---------------------------------------------------------

# Lista Telegram ID-jeva osnivača
FOUNDER_IDS = [123456789]  # Zameni sa pravim Telegram ID-jevima

ACTIVE_CODES = {} 

# ---------------------------------------------------------
# HANDLER ZA FOUNDER-E (OBJAVA KODA)
# ---------------------------------------------------------

async def handle_founder_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Kada Founder pošalje kod, bot briše njegovu poruku, 
    odmah uračunava Founder-a kao prvog korisnika (1/30)
    i objavljuje novu poruku sa dugmetom.
    """
    if not update.message or not update.message.text:
        return

    founder_id = update.effective_user.id
    text = update.message.text.strip().upper()

    # Proverava da li je pošiljalac Founder
    if founder_id in FOUNDER_IDS:
        code = text
        max_limit = 30
        
        # 1. Registrujemo kod i ODMAH dodajemo Founder-a u claimed_users (startuje od 1/30)
        ACTIVE_CODES[code] = {
            "max_uses": max_limit,
            "current_uses": 1,  # Startuje od 1 jer si ti prvi!
            "claimed_users": {founder_id},  # Founder se automatski upisuje
            "reward": 100
        }

        # Ovde po potrebi dodaješ nagradu i Founder-u u bazi:
        # add_user_points(founder_id, 100)

        # 2. Brišemo originalnu Founder poruku
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Nije moguće obrisati poruku: {e}")

        # 3. Pravimo dugme za preuzimanje
        keyboard = [
            [InlineKeyboardButton(f"🎁 Preuzmi kod {code}", callback_data=f"claim_{code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 4. Bot šalje zvaničnu objavu sa početnim stanjem 1/30
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"🔥 **NOVI PROMO KOD!** 🔥\n\n"
                f"Kod: `{code}`\n"
                f"Iskorišćeno: **1/{max_limit}**\n\n"
                f"Kliknite na dugme ispod da preuzmete nagradu!"
            ),
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

# ---------------------------------------------------------
# HANDLER ZA KLIK NA DUGME
# ---------------------------------------------------------

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obrađuje klik na dugme 'Preuzmi kod'.
    Povećava brojač za sledeće korisnike i sprečava duplo preuzimanje.
    """
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

        # 1. Provera da li je korisnik (ili Founder) već u listi
        if user_id in code_data["claimed_users"]:
            await query.message.reply_text(
                "⚠️ Već ste preuzeli ovaj promo kod! Svaki korisnik može iskoristiti kod samo jednom.",
                quote=True
            )
            return

        # 2. Provera da li je popunjen maksimalan broj mesta (30/30)
        if code_data["current_uses"] >= code_data["max_uses"]:
            await query.message.reply_text("❌ Sva mesta za ovaj kod su popunjena!", quote=True)
            return

        # 3. Uspelo preuzimanje: Registrujemo novog korisnika i povećavamo brojač
        code_data["claimed_users"].add(user_id)
        code_data["current_uses"] += 1

        current = code_data["current_uses"]
        max_limit = code_data["max_uses"]

        # Ovde dodaješ nagradu novom korisniku u bazu:
        # add_user_points(user_id, code_data['reward'])

        # 4. Ažuriramo brojač u poruci u grupi (npr. sa 1/30 na 2/30)
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

        # Šaljemo obaveštenje korisniku
        await query.message.reply_text(
            f"🎉 Uspešno ste preuzeli kod `{code}`! Dobili ste {code_data['reward']} poena.",
            parse_mode="Markdown",
            quote=True
        )

# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN", "TVOJ_TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(handle_button_click))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_founder_code))

    logger.info("Bot pokrenut...")
    app.run_polling()

if __name__ == "__main__":
    main()
