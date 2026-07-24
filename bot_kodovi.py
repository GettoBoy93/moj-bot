import re
import sqlite3
import logging
import os
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.types import WebAppInfo
import asyncio

# --- PODEŠAVANJA ---
BOT_TOKEN = "8864145955:AAFNAQcoCFUxgPF6AxaExPQ1oos2VOVgZ8Y"

FOUNDERI_USERNAMES = [
    "@PERIABOY", "@Goran1974m", "@Bahro67", "@Stuxnet992", "@Josip0107",
    "@Snave31", "@jagodica113", "@evanescence83", "@rajder987", "@AleksandarVujic",
    "@Alessandro1973Vuk", "@Djenedjenee"
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
    
    cursor.execute("SELECT vreme_objave, broj_kopiranja, aktivan FROM kodovi WHERE kod = ?", (kod,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, 30, "NEPOSTOJECE"
        
    vreme_objave, trenutni_broj, aktivan = row
    if isinstance(vreme_objave, str):
        vreme_dt = datetime.fromisoformat(vreme_objave)
    else:
        vreme_dt = vreme_objave

    if (datetime.now() - vreme_dt).total_seconds() > 3600 or aktivan == 0:
        cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE kod = ?", (kod,))
        conn.commit()
        conn.close()
        return False, trenutni_broj, "ISTEKAO_TAJMER"

    cursor.execute("SELECT id FROM preuzimanja WHERE kod = ? AND user_id = ?", (kod, user_id))
    if cursor.fetchone():
        conn.close()
        return False, trenutni_broj, "VEĆ_PREUZETO"
    
    if trenutni_broj >= 30:
        conn.close()
        return False, 30, "ISTEKAO_LIMIT"

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
    except Exception:
        conn.close()
        return False, 1, "GRESKA"

def dohvati_kod_info(kod):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT founder, broj_kopiranja, vreme_objave, aktivan FROM kodovi WHERE kod = ?", (kod,))
    res = cursor.fetchone()
    conn.close()
    if res:
        founder, broj, vreme, aktivan = res
        if isinstance(vreme, str):
            vreme_dt = datetime.fromisoformat(vreme)
        else:
            vreme_dt = vreme
        proteklo = int((datetime.now() - vreme_dt).total_seconds() // 60)
        preostalo = max(0, 60 - proteklo)
        return founder, broj, preostalo, aktivan
    return None, 1, 0, 0

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
    # Povezivanje na WebApp interfejs za prikaz i lak kopir koda
    webapp_url = f"https://miningperia.com/pages/join.php?custom={kod}"
    builder.button(
        text=f"🎁 Preuzmi kod ({broj_kopiranja}/30)",
        web_app=WebAppInfo(url=webapp_url)
    )
    return builder.as_markup()

# --- HANDLERI ZA KOMANDE ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Zdravo! Ja sam bot za PERIA kodove.")

@dp.message(Command("aktivno"))
async def cmd_aktivno(message: types.Message):
    aktivni = dohvati_aktivne_kodove()
    if not aktivni:
        await message.answer("Trenutno nema aktivnih kodova.")
        return
    
    tekst = "<b>🔥 AKTIVNI KODOVI:</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for item in aktivni:
        tekst += (
            f"• Osnivač: <b>{item['founder']}</b>\n"
            f"   ⏱ Preostalo: <b>{item['preostalo_minuta']} min</b> | 📊 Popunjeno: <b>{item['broj_kopiranja']}/30</b>\n\n"
        )
        builder.button(
            text=f"🎁 Preuzmi kod ({item['founder']}) ({item['broj_kopiranja']}/30)",
            web_app=WebAppInfo(url=f"https://miningperia.com/pages/join.php?custom={item['kod']}")
        )
    
    builder.adjust(1)
    await message.answer(tekst, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

# --- HANDLER ZA OBJAVU KODA OD OSNIVAČA ---

@dp.message(F.text)
async def obradi_poruku(message: types.Message):
    korisnik = message.from_user
    username = f"@{korisnik.username}" if korisnik.username else ""
    user_id = korisnik.id
    
    is_founder = (username.lower() in [u.lower() for u in FOUNDERI_USERNAMES]) or (user_id in FOUNDERI_IDS)
    if not is_founder:
        return

    pronadjeni_kodovi = re.findall(KOD_REGEX, message.text)
    if not pronadjeni_kodovi:
        return

    for kod in pronadjeni_kodovi:
        prikaz_imena = username if username else korisnik.first_name
        uspesno = dodaj_kod(kod, prikaz_imena, user_id)
        
        if uspesno:
            tekst_poruke = (
                f"🚨 <b>NOVI KOD OD OSNIVAČA:</b> {prikaz_imena}\n\n"
                f"Pridruži se PERIA grupi za rudarenje!\n"
                f"Otvori <b>MiningPeria → Mining → Custom</b>\n\n"
                f"👉 <i>Kliknite na dugme ispod da preuzmete kod!</i>\n\n"
                f"📊 Popunjeno: <b>1/30</b>\n"
                f"⏱ Važi još: <b>60 min</b>"
            )
            
            try:
                # 1. Prvo šaljemo novu poruku
                nova_poruka = await message.answer(
                    tekst_poruke,
                    parse_mode=ParseMode.HTML,
                    reply_markup=napravi_tastaturu_za_kod(kod, 1)
                )
                
                # 2. Tek ako je nova poruka uspešno poslata, brišemo staru
                try:
                    await message.delete()
                except Exception as e:
                    logging.error(f"Neuspešno brisanje originalne poruke: {e}")

                # 3. Pinujemo novu poruku
                try:
                    await bot.pin_chat_message(
                        chat_id=message.chat.id,
                        message_id=nova_poruka.message_id,
                        disable_notification=False
                    )
                except Exception as e:
                    logging.error(f"Neuspešno pinovanje: {e}")

            except Exception as e:
                # Ako slanje nove poruke ne uspe, obavesti u konzoli/logu
                logging.error(f"Greška pri slanju nove poruke sa kodom: {e}")

# --- HANDLER ZA SINKRONIZACIJU IZ WEBAPP-A ---

@dp.message(F.web_app_data)
async def obradi_web_app_podatke(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        kod = data.get("kod")
        user_id = message.from_user.id
        
        if kod:
            uspesno, novi_broj, status = zabelezi_preuzimanje(kod, user_id)
            founder, trenutni_broj, preostalo, aktivan = dohvati_kod_info(kod)
            
            tekst_grupa = (
                f"🚨 <b>NOVI KOD OD OSNIVAČA:</b> {founder}\n\n"
                f"Pridruži se PERIA grupi za rudarenje!\n"
                f"Otvori <b>MiningPeria → Mining → Custom</b>\n\n"
                f"👉 <i>Kliknite na dugme ispod da preuzmete kod!</i>\n\n"
                f"📊 Popunjeno: <b>{novi_broj}/30</b>\n"
                f"⏱ Važi još: <b>{preostalo} min</b>"
            )
            
            await message.answer(
                tekst_grupa,
                parse_mode=ParseMode.HTML,
                reply_markup=napravi_tastaturu_za_kod(kod, novi_broj)
            )
    except Exception as e:
        logging.error(f"Greška pri obradi WebApp podataka: {e}")

async def main():
    print("Bot je pokrenut...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
