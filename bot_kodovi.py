import re
import sqlite3
import logging
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import asyncio

# --- PODEŠAVANJA ---
BOT_TOKEN = "8864145955:AAFNAQcoCFUxgPF6AxaExPQ1oos2VOVgZ8Y"

FOUNDERI_USERNAMES = [
    "@PERIABOY", "@Goran1974m", "@Bahro67", "@Stuxnet992", "@Josip0107",
    "@Snave31", "@jagodica113", "@evanescence83", "@rajder987", "@AleksandarVujic",
    "@Alessandro1973Vuk"
]
FOUNDERI_IDS = []

KOD_REGEX = r'\b[A-Z0-9]{6}\b'

DATA_DIR = "/app/data"
if os.path.exists(DATA_DIR):
    DB_PATH = os.path.join(DATA_DIR, "kodovi.db")
else:
    DB_PATH = "kodovi.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA PODATAKA (SQLite) ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kodovi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kod TEXT UNIQUE,
            founder TEXT,
            founder_user_id INTEGER,
            broj_kopiranja INTEGER DEFAULT 1,
            vreme_objave TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            aktivan INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preuzimanja (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kod TEXT,
            user_id INTEGER,
            vreme TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(kod, user_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def dodaj_kod(kod, founder_name, founder_user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    vreme_sada = datetime.now()
    try:
        cursor.execute("""
            INSERT INTO kodovi (kod, founder, founder_user_id, broj_kopiranja, vreme_objave)
            VALUES (?, ?, ?, 1, ?)
        """, (kod, founder_name, founder_user_id, vreme_sada))
        
        cursor.execute("""
            INSERT OR IGNORE INTO preuzimanja (kod, user_id)
            VALUES (?, ?)
        """, (kod, founder_user_id))
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def zabelezi_preuzimanje(kod, user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM preuzimanja WHERE kod = ? AND user_id = ?", (kod, user_id))
    if cursor.fetchone():
        cursor.execute("SELECT broj_kopiranja FROM kodovi WHERE kod = ?", (kod,))
        res = cursor.fetchone()
        conn.close()
        return False, res[0] if res else 1, "VEĆ_PREUZETO"
    
    cursor.execute("SELECT broj_kopiranja, aktivan FROM kodovi WHERE kod = ?", (kod,))
    res = cursor.fetchone()
    if not res or res[0] >= 30 or res[1] == 0:
        conn.close()
        return False, res[0] if res else 30, "ISTEKAO_LIMIT"

    try:
        cursor.execute("INSERT INTO preuzimanja (kod, user_id) VALUES (?, ?)", (kod, user_id))
        cursor.execute("UPDATE kodovi SET broj_kopiranja = broj_kopiranja + 1 WHERE kod = ?", (kod,))
        cursor.execute("SELECT broj_kopiranja FROM kodovi WHERE kod = ?", (kod,))
        novi_broj = cursor.fetchone()[0]
        
        if novi_broj >= 30:
            cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
            
        conn.commit()
        conn.close()
        return True, novi_broj, "USPESNO"
    except Exception as e:
        conn.close()
        return False, 1, "GRESKA"

def dohvati_aktivne_kodove():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    granica = datetime.now() - timedelta(minutes=60)
    cursor.execute("""
        SELECT kod, founder, broj_kopiranja, vreme_objave 
        FROM kodovi 
        WHERE aktivan = 1 AND broj_kopiranja < 30 AND vreme_objave >= ?
        ORDER BY vreme_objave DESC
    """, (granica,))
    redovi = cursor.fetchall()
    conn.close()
    
    rezultat = []
    sada = datetime.now()
    for kod, founder, broj_kopiranja, vreme_objave in redovi:
        if isinstance(vreme_objave, str):
            vreme_dt = datetime.fromisoformat(vreme_objave)
        else:
            vreme_dt = vreme_objave
        
        proteklo_minuta = int((sada - vreme_dt).total_seconds() // 60)
        preostalo_minuta = max(0, 60 - proteklo_minuta)
        
        rezultat.append({
            'kod': kod,
            'founder': founder,
            'broj_kopiranja': broj_kopiranja,
            'preostalo_minuta': preostalo_minuta
        })
    return rezultat

def napravi_tastaturu_za_kod(kod, broj_kopiranja=1):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🎁 Preuzmi kod ({broj_kopiranja}/30)",
        callback_data=f"preuzmi_{kod}"
    )
    return builder.as_markup()

# --- HANDLERI ZA KOMANDE ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Zdravo! Ja sam bot za kodove. Pratite objave u grupi za najnovije kodove sa brzom opcijom kopiranja.")

@dp.message(Command("aktivno"))
async def cmd_aktivno(message: types.Message):
    aktivni = dohvati_aktivne_kodove()
    if not aktivni:
        await message.answer("Trenutno nema aktivnih kodova.")
        return
    
    tekst = "<b>🔥 AKTIVNI KODOVI:</b>\n<i>(Dodirnite kod da ga kopirate ili kliknite na dugme ispod da zabeležite preuzimanje)</i>\n\n"
    builder = InlineKeyboardBuilder()
    
    for item in aktivni:
        tekst += (
            f"• <code>{item['kod']}</code> (Osnivač: {item['founder']})\n"
            f"   ⏱ Preostalo: <b>{item['preostalo_minuta']} min</b> | 📊 Preuzeto: <b>{item['broj_kopiranja']}/30</b>\n\n"
        )
        builder.button(
            text=f"🎁 Preuzmi {item['kod']} ({item['broj_kopiranja']}/30)",
            callback_data=f"preuzmi_{item['kod']}"
        )
    
    builder.adjust(1)
    await message.answer(tekst, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

# --- HANDLER ZA DETEKCIJU KODOVA (POŠILJALAC: FOUNDER) ---

@dp.message(F.text)
async def obradi_poruku(message: types.Message):
    korisnik = message.from_user
    username = f"@{korisnik.username}" if korisnik.username else ""
    user_id = korisnik.id
    
    # Provera bez obzira na velika/mala slova
    is_founder = (username.lower() in [u.lower() for u in FOUNDERI_USERNAMES]) or (user_id in FOUNDERI_IDS)
    if not is_founder:
        return

    pronadjeni_kodovi = re.findall(KOD_REGEX, message.text)
    if not pronadjeni_kodovi:
        return

    for kod in pronadjeni_kodovi:
        uspesno = dodaj_kod(kod, username or korisnik.first_name, user_id)
        if uspesno:
            try:
                await message.delete()
            except Exception:
                pass
            
            prikaz_imena = username if username else korisnik.first_name
            tekst_poruke = (
                f"🚨 <b>NOVI KOD OD OSNIVAČA:</b> {prikaz_imena}\n\n"
                f"Kod: <code>{kod}</code>\n\n"
                f"👉 <i>Dodirnite kod iznad da ga kopirate, ili kliknite na dugme ispod da zabeležite preuzimanje.</i>"
            )
            
            nova_poruka = await message.answer(
                tekst_poruke,
                parse_mode=ParseMode.HTML,
                reply_markup=napravi_tastaturu_za_kod(kod, 1)
            )
            
            try:
                await bot.pin_chat_message(
                    chat_id=message.chat.id,
                    message_id=nova_poruka.message_id,
                    disable_notification=False
                )
            except Exception as e:
                logging.error(f"Neuspešno pinovanje: {e}")

# --- HANDLER ZA KLIK NA DUGME "PREUZMI KOD" ---

@dp.callback_query(F.data.startswith("preuzmi_"))
async def obradi_preuzimanje(callback_query: types.CallbackQuery):
    kod = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    uspesno, novi_broj, status = zabelezi_preuzimanje(kod, user_id)
    
    if status == "VEĆ_PREUZETO":
        await callback_query.answer(
            f"⚠️ Već ste preuzeli kod {kod}! Svaki član može preuzeti kod samo jednom.",
            show_alert=True
        )
    elif status == "ISTEKAO_LIMIT":
        await callback_query.answer(
            f"❌ Kod {kod} je već dostigao maksimalnih 30 preuzimanja!",
            show_alert=True
        )
    elif uspesno:
        try:
            old_markup = callback_query.message.reply_markup
            new_builder = InlineKeyboardBuilder()
            
            for row in old_markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data == f"preuzmi_{kod}":
                        new_builder.button(
                            text=f"🎁 Preuzmi kod {kod} ({novi_broj}/30)",
                            callback_data=f"preuzmi_{kod}"
                        )
                    else:
                        new_builder.button(
                            text=btn.text,
                            callback_data=btn.callback_data
                        )
            
            new_builder.adjust(1)
            await callback_query.message.edit_reply_markup(
                reply_markup=new_builder.as_markup()
            )
        except Exception:
            pass
        
        await callback_query.answer(
            f"✅ Uspešno ste preuzeli kod: {kod}\nUkupno preuzeto: {novi_broj}/30",
            show_alert=True
        )
    else:
        await callback_query.answer("Došlo je do greške pri preuzimanju.", show_alert=True)

async def main():
    print("Bot je pokrenut...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
