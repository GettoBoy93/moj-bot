import re
import sqlite3
import logging
import os
import urllib.request
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
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

# --- BAZA PODATAKA ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kodovi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kod TEXT UNIQUE,
            founder TEXT,
            chat_id INTEGER,
            message_id INTEGER,
            broj_clanova INTEGER DEFAULT 1,
            vreme_objave TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            aktivan INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

init_db()

def dodaj_kod(kod, founder_name, chat_id, message_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    vreme_sada = datetime.now()
    try:
        cursor.execute("""
            INSERT INTO kodovi (kod, founder, chat_id, message_id, broj_clanova, vreme_objave)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (kod, founder_name, chat_id, message_id, vreme_sada))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def dohvati_sve_aktivne_iz_baze():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    granica = datetime.now() - timedelta(minutes=60)
    cursor.execute("""
        SELECT id, kod, founder, chat_id, message_id, broj_clanova, vreme_objave 
        FROM kodovi 
        WHERE aktivan = 1 AND vreme_objave >= ?
    """, (granica,))
    redovi = cursor.fetchall()
    conn.close()
    return redovi

def azuriraj_broj_clanova_u_bazi(kod_id, novi_broj, aktivan=1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE kodovi SET broj_clanova = ?, aktivan = ? WHERE id = ?", (novi_broj, aktivan, kod_id))
    conn.commit()
    conn.close()

def deaktiviraj_istekle():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    granica = datetime.now() - timedelta(minutes=60)
    cursor.execute("UPDATE kodovi SET aktivan = 0 WHERE vreme_objave < ? OR broj_clanova >= 30", (granica,))
    conn.commit()
    conn.close()

# --- SKRAPOVANJE PODATAKA SA PERIA SAJTA ---
def proveri_broj_na_sajtu(kod):
    url = f"https://miningperia.com/pages/join.php?custom={kod}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')
            # Traženje broja članova u formatu "X/30" ili broja iz HTML-a
            match = re.search(r'(\d+)\s*/\s*30', html)
            if match:
                return int(match.group(1))
            # Alternativna provera ako piše broj u nekom drugom obliku
            numbers = re.findall(r'\b\d+\b', html)
            for n in numbers:
                val = int(n)
                if 1 <= val <= 30:
                    return val
    except Exception as e:
        logging.error(f"Greška pri proveri sajta za kod {kod}: {e}")
    return None

# --- TEKST PORUKE ---
def generisi_tekst_poruke(kod, founder, broj_clanova, preostalo_minuta):
    if broj_clanova >= 30 or preostalo_minuta <= 0:
        return (
            f"❌ <b>KOD ISTEKAO / GRUPA POPUNJENA!</b>\n\n"
            f"Kod: <code>{kod}</code> (Osnivač: {founder})\n"
            f"Status: <b>{broj_clanova}/30 članova</b>"
        )
    
    return (
        f"🚨 <b>NOVI KOD OD OSNIVAČA:</b> {founder}\n\n"
        f"Pridruži se PERIA grupi za rudarenje!\n"
        f"Otvori <b>MiningPeria → Mining → Custom</b> i unesi kod:\n\n"
        f"👉 <code>{kod}</code> 👈 <i>(Dodirnite kod da ga kopirate)</i>\n\n"
        f"📊 Popunjeno: <b>{broj_clanova}/30</b>\n"
        f"⏱ Važi još: <b>{preostalo_minuta} min</b>"
    )

# --- BACKROUND TASK (Provera na svakih 15 sekundi) ---
async def petlja_za_azuriranje():
    while True:
        try:
            deaktiviraj_istekle()
            aktivni = dohvati_sve_aktivne_iz_baze()
            sada = datetime.now()
            
            for kod_id, kod, founder, chat_id, message_id, trenutni_broj, vreme_objave in aktivni:
                if isinstance(vreme_objave, str):
                    vreme_dt = datetime.fromisoformat(vreme_objave)
                else:
                    vreme_dt = vreme_objave
                
                proteklo = int((sada - vreme_dt).total_seconds() // 60)
                preostalo = max(0, 60 - proteklo)
                
                # Proveravamo sajt za stvarni broj
                novi_broj = proveri_broj_na_sajtu(kod)
                
                if novi_broj is None:
                    novi_broj = trenutni_broj

                is_aktivan = 1
                if novi_broj >= 30 or preostalo <= 0:
                    is_aktivan = 0

                # Ako se broj promenio ili je kod istekao, osvežavamo poruku na Telegramu
                if novi_broj != trenutni_broj or not is_aktivan or (preostalo % 5 == 0):
                    azuriraj_broj_clanova_u_bazi(kod_id, novi_broj, is_aktivan)
                    novi_tekst = generisi_tekst_poruke(kod, founder, novi_broj, preostalo)
                    
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=novi_tekst,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
        except Exception as e:
            logging.error(f"Greška u pozadinskoj petlji: {e}")
            
        await asyncio.sleep(15)

# --- HANDLERI ZA KOMANDE ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Zdravo! Ja sam bot za PERIA kodove.")

@dp.message(Command("aktivno"))
async def cmd_aktivno(message: types.Message):
    deaktiviraj_istekle()
    aktivni = dohvati_sve_aktivne_iz_baze()
    
    if not aktivni:
        await message.answer("Trenutno nema aktivnih kodova.")
        return
    
    tekst = "<b>🔥 AKTIVNI KODOVI:</b>\n<i>(Dodirnite kod da ga kopirate)</i>\n\n"
    sada = datetime.now()
    
    for kod_id, kod, founder, chat_id, message_id, broj_clanova, vreme_objave in aktivni:
        if isinstance(vreme_objave, str):
            vreme_dt = datetime.fromisoformat(vreme_objave)
        else:
            vreme_dt = vreme_objave
            
        proteklo = int((sada - vreme_dt).total_seconds() // 60)
        preostalo = max(0, 60 - proteklo)
        
        tekst += (
            f"• <code>{kod}</code> (Osnivač: {founder})\n"
            f"   ⏱ Preostalo: <b>{preostalo} min</b> | 📊 Članova: <b>{broj_clanova}/30</b>\n\n"
        )
    
    await message.answer(tekst, parse_mode=ParseMode.HTML)

# --- HANDLER ZA OBJAVU KODA ---

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
        
        # Prvo brišemo originalnu poruku osnivača
        try:
            await message.delete()
        except Exception:
            pass
            
        tekst_poruke = generisi_tekst_poruke(kod, prikaz_imena, 1, 60)
        
        nova_poruka = await message.answer(
            tekst_poruke,
            parse_mode=ParseMode.HTML
        )
        
        dodaj_kod(kod, prikaz_imena, nova_poruka.chat.id, nova_poruka.message_id)
        
        try:
            await bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=nova_poruka.message_id,
                disable_notification=False
            )
        except Exception as e:
            logging.error(f"Neuspešno pinovanje: {e}")

async def main():
    print("Bot je pokrenut sa automatskim praćenjem sajta...")
    asyncio.create_task(petlja_za_azuriranje())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
