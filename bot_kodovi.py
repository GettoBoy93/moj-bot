import re
import sqlite3
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import asyncio

# --- PODEŠAVANJA ---
BOT_TOKEN = "8864145955:AAFNAQcoCFUxgPF6AxaExPQ1oos2VOVgZ8Y"

# Unesi korisnička imena (sa @) ili numeričke ID-jeve 10 foundera
FOUNDERI_USERNAMES = [
    "@PERIABOY", "@Goran1974m", "@Bahro67", "@Stuxnet992", "@Josip0107",
    "@Snave31", "@jagodica113", "@evanescence83", "@rajder987", "@AleksandarVujic"
]
FOUNDERI_IDS = []  # Možeš dodati i numeričke Telegram ID-jeve ako preferiraš

# Regex za prepoznavanje koda: tačno 6 velikih slova i brojeva
KOD_REGEX = r'\b[A-Z0-9]{6}\b'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA PODATAKA (SQLite) ---
def init_db():
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kodovi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kod TEXT UNIQUE,
            founder TEXT,
            founder_user_id INTEGER,
            broj_kopiranja INTEGER DEFAULT 0,
            vreme_objave TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            aktivan INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

init_db()

def dodaj_kod(kod, founder_name, founder_user_id):
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    vreme_sada = datetime.now()
    try:
        cursor.execute(
            "INSERT INTO kodovi (kod, founder, founder_user_id, vreme_objave) VALUES (?, ?, ?, ?)",
            (kod, founder_name, founder_user_id, vreme_sada)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def preuzmi_i_povecaj(kod):
    """Proverava validnost koda (vreme + broj) i povećava brojač."""
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()

    cursor.execute("SELECT broj_kopiranja, vreme_objave, aktivan FROM kodovi WHERE kod = ?", (kod,))
    red = cursor.fetchone()

    if not red:
        conn.close()
        return None, "Kod ne postoji u bazi."

    broj, vreme_str, aktivan = red
    vreme_objave = datetime.fromisoformat(vreme_str) if isinstance(vreme_str, str) else vreme_str

    # Provera 1: Da li je manuelno ili automatski neaktivan
    if aktivan == 0:
        conn.close()
        return None, "❌ Ovaj kod više nije aktivan!"

    # Provera 2: Vremensko ograničenje od 60 minuta
    if datetime.now() - vreme_objave > timedelta(minutes=60):
        cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
        conn.commit()
        conn.close()
        return None, "⏳ Isteklo je vreme od 60 minuta za ovaj kod!"

    # Provera 3: Limit od 30 preuzimanja
    if broj >= 30:
        cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
        conn.commit()
        conn.close()
        return None, "❌ Kod je već dostigao maksimalnih 30 preuzimanja!"

    # Povećaj brojač
    novi_broj = broj + 1
    if novi_broj >= 30:
        cursor.execute("UPDATE kodovi SET broj_kopiranja = ?, aktivan = 0 WHERE kod = ?", (novi_broj, kod))
    else:
        cursor.execute("UPDATE kodovi SET broj_kopiranja = ? WHERE kod = ?", (novi_broj, kod))

    conn.commit()
    conn.close()
    return novi_broj, None

def preuzmi_aktivne_kodove():
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    cursor.execute("SELECT kod, founder, broj_kopiranja, vreme_objave FROM kodovi WHERE aktivan = 1")
    svi_kodovi = cursor.fetchall()
    conn.close()

    aktivni = []
    sada = datetime.now()

    for kod, founder, broj, vreme_str in svi_kodovi:
        vreme_objave = datetime.fromisoformat(vreme_str) if isinstance(vreme_str, str) else vreme_str

        if (sada - vreme_objave <= timedelta(minutes=60)) and (broj < 30):
            preostalo_minuta = 60 - int((sada - vreme_objave).total_seconds() // 60)
            aktivni.append((kod, founder, broj, preostalo_minuta))

    return aktivni

def deaktiviraj_kod(kod, user_id, username):
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()

    cursor.execute("SELECT founder_user_id, founder FROM kodovi WHERE kod = ? AND aktivan = 1", (kod,))
    red = cursor.fetchone()

    if not red:
        conn.close()
        return False, "Kod ne postoji ili je već neaktivan."

    f_user_id, f_name = red

    is_founder = (username in FOUNDERI_USERNAMES) or (user_id in FOUNDERI_IDS) or (user_id == f_user_id)

    if not is_founder:
        conn.close()
        return False, "Nemate dozvolu da obrišete ovaj kod."

    cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
    conn.commit()
    conn.close()
    return True, f"Uspešno je deaktiviran kod: `{kod}`"

# --- HANDLERI ---

# 1. Founder objavi kod
@dp.message(F.text)
async def obradi_poruku(message: types.Message):
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    user_id = message.from_user.id

    is_founder = (username in FOUNDERI_USERNAMES) or (user_id in FOUNDERI_IDS)
    if not is_founder:
        return

    pronadjeni_kodovi = re.findall(KOD_REGEX, message.text)

    for kod in pronadjeni_kodovi:
        uspesno = dodaj_kod(kod, message.from_user.full_name, user_id)
        if uspesno:
            builder = InlineKeyboardBuilder()
            builder.button(
                text="📋 Preuzmi Kod (0/30)",
                callback_data=f"copy_{kod}"
            )

            poruka_tekst = (
                f"🚨 **Novi kod je dostupan!**\n\n"
                f"👤 **Founder:** {message.from_user.full_name}\n"
                f"⏱️ **Važi narednih 60 minuta.**\n\n"
                f"👇 *Klikni na dugme ispod da preuzmeš i kopiraš kod.*"
            )

            await message.reply(
                poruka_tekst,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=builder.as_markup()
            )

# 2. Klik na dugme za preuzimanje koda
@dp.callback_query(F.data.startswith("copy_"))
async def obradi_kopiranje(callback: types.CallbackQuery):
    kod = callback.data.split("_")[1]

    novi_broj, greska = preuzmi_i_povecaj(kod)

    if greska:
        await callback.answer(greska, show_alert=True)
        return

    # Ažuriraj tekst dugmeta u grupi sa novim brojem preuzimanja
    builder = InlineKeyboardBuilder()
    if novi_broj >= 30:
        builder.button(text="❌ Kod popunjen (30/30)", callback_data="neaktivan")
    else:
        builder.button(text=f"📋 Preuzmi Kod ({novi_broj}/30)", callback_data=f"copy_{kod}")

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

    # Šaljemo pop-up (Alert) sa kodom u MONO formatu za lako kopiranje 1 tapom
    await callback.answer(
        text=f"Tvoj kod je:\n\n`{kod}`\n\n(Broj preuzimanja: {novi_broj}/30)",
        show_alert=True
    )

# 3. Komanda /aktivno
@dp.message(Command("aktivno"))
async def lista_aktivnih(message: types.Message):
    kodovi = preuzmi_aktivne_kodove()

    if not kodovi:
        await message.reply("Trenutno nema aktivnih kodova.")
        return

    odgovor = "🔥 **Trenutno aktivni kodovi:**\n\n"
    for kod, founder, broj, preostalo_min in kodovi:
        odgovor += (
            f"• Kod od: **{founder}**\n"
            f"  └ Kod: `{kod}` (Klikni na kod da ga kopiraš)\n"
            f"  └ Preuzeto: **{broj}/30** | Ističe za: **{preostalo_min} min**\n\n"
        )

    await message.reply(odgovor, parse_mode=ParseMode.MARKDOWN)

# 4. Komanda /obrisi_kod (za Ručno Deaktiviranje)
@dp.message(Command("obrisi_kod"))
async def obrisi_kod_handler(message: types.Message):
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    user_id = message.from_user.id

    delovi = message.text.split()
    if len(delovi) < 2:
        await message.reply("⚠️ Pogrešna komanda! Unesi: `/obrisi_kod TVOJKOD`", parse_mode=ParseMode.MARKDOWN)
        return

    kod_za_brisanje = delovi[1].upper()
    uspeh, poruka = deaktiviraj_kod(kod_za_brisanje, user_id, username)

    await message.reply(poruka, parse_mode=ParseMode.MARKDOWN)

# --- POKRETANJE BOTA ---
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot je pokrenut...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
