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

FOUNDERI_USERNAMES = [
    "@PERIABOY", "@Goran1974m", "@Bahro67", "@Stuxnet992", "@Josip0107",
    "@Snave31", "@Jagodica113", "@evanescence83", "@rajder987", "@AleksandarVujic"
]
FOUNDERI_IDS = []

KOD_REGEX = r'\b[A-Z0-9]{6}\b'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA PODATAKA (SQLite) ---
def init_db():
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    # Tabela za kodove
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
    # Tabela za praćenje ko je već preuzeo koji kod (1 korisnik = 1 preuzimanje)
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
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    vreme_sada = datetime.now()
    try:
        cursor.execute("""
            INSERT INTO kodovi (kod, founder, founder_user_id, vreme_objave)
            VALUES (?, ?, ?, ?)
        """, (kod, founder_name, founder_user_id, vreme_sada))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def zabelezi_preuzimanje(kod, user_id):
    """
    Vraća (uspesno, trenutni_broj_preuzimanja, poruka)
    Ako je korisnik već preuzeo kod, vraća (False, broj, "VEĆ_PREUZETO")
    """
    conn = sqlite3.connect("kodovi.db")
    cursor = conn.cursor()
    
    # Provera da li je već preuzeo
    cursor.execute("SELECT id FROM preuzimanja WHERE kod = ? AND user_id = ?", (kod, user_id))
    if cursor.fetchone():
        cursor.execute("SELECT broj_kopiranja FROM kodovi WHERE kod = ?", (kod,))
        res = cursor.fetchone()
        conn.close()
        return False, res[0] if res else 0, "VEĆ_PREUZETO"
    
    # Provera limita 30 preuzimanja
    cursor.execute("SELECT broj_kopiranja, aktivan FROM kodovi WHERE kod = ?", (kod,))
    res = cursor.fetchone()
    if not res or res[0] >= 30 or res[1] == 0:
        conn.close()
        return False, res[0] if res else 30, "ISTEKAO_LIMIT"

    try:
        # Zabeleži korisnika
        cursor.execute("INSERT INTO preuzimanja (kod, user_id) VALUES (?, ?)", (kod, user_id))
        # Povećaj brojač
        cursor.execute("UPDATE kodovi SET broj_kopiranja = broj_kopiranja + 1 WHERE kod = ?", (kod,))
        cursor.execute("SELECT broj_kopiranja FROM kodovi WHERE kod = ?", (kod,))
        novi_broj = cursor.fetchone()[0]
        
        # Ako je stiglo do 30, označi kao neaktivan
        if novi_broj >= 30:
            cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
            
        conn.commit()
        conn.close()
        return True, novi_broj, "USPESNO"
    except Exception as e:
        conn.close()
        return False, 0, "GRESKA"

def dohvati_aktivne_kodove():
    conn = sqlite3.connect("kodovi.db")
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

def napravi_tastaturu_za_kod(kod, broj_kopiranja=0):
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
    
    tekst = "<b>🔥 AKTIVNI KODOVI:</b>\n<i>(Dodirnite kod da ga kopirate)</i>\n\n"
    
    for item in aktivni:
        tekst += (
            f"• <code>{item['kod']}</code> (Osnivač: {item['founder']})\n"
            f"   ⏱ Preostalo: <b>{item['preostalo_minuta']} min</b> | 📊 Preuzeto: <b>{item['broj_kopiranja']}/30</b>\n\n"
        )
    
    await message.answer(tekst, parse_mode=ParseMode.HTML)

# --- HANDLER ZA DETEKCIJU KODOVA (POŠILJALAC: FOUNDER) ---

@dp.message(F.text)
async def obradi_poruku(message: types.Message):
    korisnik = message.from_user
    username = f"@{korisnik.username}" if korisnik.username else ""
    user_id = korisnik.id
    
    is_founder = (username in FOUNDERI_USERNAMES) or (user_id in FOUNDERI_IDS)
    if not is_founder:
        return

    pronadjeni_kodovi = re.findall(KOD_REGEX, message.text)
    if not pronadjeni_kodovi:
        return

    for kod in pronadjeni_kodovi:
        uspesno = dodaj_kod(kod, username or korisnik.first_name, user_id)
        if uspesno:
            # Obrisi originalnu poruku founder-a
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
                reply_markup=napravi_tastaturu_za_kod(kod, 0)
            )
            
            # PIN-ovanje poruke sa zvučnim obaveštenjem (stigne svima, čak i ako je na mute)
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
        # Ažuriraj tekst na dugmetu sa novim brojem preuzimanja
        try:
            await callback_query.message.edit_reply_markup(
                reply_markup=napravi_tastaturu_za_kod(kod, novi_broj)
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
