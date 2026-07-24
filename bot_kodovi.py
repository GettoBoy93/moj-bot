import re
import sqlite3
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import asyncio

logging.basicConfig(level=logging.INFO)


BOT_TOKEN = os.getenv("BOT_TOKEN")
KOD_REGEX = r'\b[A-Za-z0-9]{6}\b'

DATA_DIR = "/app/data"
if os.path.exists(DATA_DIR):
    DB_PATH = os.path.join(DATA_DIR, "kodovi.db")
else:
    DB_PATH = "kodovi.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- BAZA PODATAKA ---
def init_db():
    try:
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
    except Exception as e:
        logging.error(f"Greska pri inickalizaciji baze: {e}")

init_db()

def dodaj_kod(kod, founder_name, founder_user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        vreme_sada = datetime.now()
        
        cursor.execute("""
            INSERT INTO kodovi (kod, founder, founder_user_id, broj_kopiranja, vreme_objave)
            VALUES (?, ?, ?, 1, ?)
        """, (kod, founder_name, founder_user_id, vreme_sada))
        
        cursor.execute("""
            INSERT OR IGNORE INTO preuzimanja (kod, user_id)
            VALUES (?, ?)
        """, (kod, founder_user_id))
        
        conn.commit()
        conn.close()
        return True, "OK"
    except sqlite3.IntegrityError:
        return False, "KOD_POSTOJI"
    except Exception as e:
        return False, str(e)

def dohvati_aktivne_kodove():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT kod, founder, broj_kopiranja, vreme_objave 
            FROM kodovi 
            WHERE aktivan = 1 AND broj_kopiranja < 30
            ORDER BY vreme_objave DESC
        """)
        redovi = cursor.fetchall()
        conn.close()
    except Exception as e:
        logging.error(f"Greska pri citanju iz baze: {e}")
        redovi = []
    
    rezultat = []
    sada = datetime.now()
    for kod, founder, broj_kopiranja, vreme_objave in redovi:
        try:
            if isinstance(vreme_objave, str):
                vreme_dt = datetime.fromisoformat(vreme_objave.replace(" ", "T"))
            else:
                vreme_dt = vreme_objave
            
            proteklo_minuta = int((sada - vreme_dt).total_seconds() // 60)
            preostalo_minuta = max(0, 60 - proteklo_minuta)
            
            if preostalo_minuta > 0:
                rezultat.append({
                    'kod': kod,
                    'founder': founder,
                    'broj_kopiranja': broj_kopiranja,
                    'preostalo_minuta': preostalo_minuta
                })
        except Exception:
            rezultat.append({
                'kod': kod,
                'founder': founder,
                'broj_kopiranja': broj_kopiranja,
                'preostalo_minuta': 60
            })
            
    return rezultat

def napravi_tastaturu_za_kod(kod, broj_kopiranja=1):
    builder = InlineKeyboardBuilder()
    link_url = f"https://miningperia.com/pages/join.php?custom={kod}"
    builder.button(
        text=f"🎁 Preuzmi kod ({broj_kopiranja}/30)",
        url=link_url
    )
    return builder.as_markup()

# --- KOMANDE ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Zdravo! Ja sam bot za PERIA kodove.")

@dp.message(Command("aktivno"))
async def cmd_aktivno(message: types.Message):
    try:
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
                url=f"https://miningperia.com/pages/join.php?custom={item['kod']}"
            )
        
        builder.adjust(1)
        await message.answer(tekst, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
    except Exception as e:
        await message.answer(f"Došlo je do greške u komandi: {e}")

# --- OBRAĐIVANJE PORUKA ---

@dp.message(F.text)
async def obradi_poruku(message: types.Message):
    if message.text.startswith("/"):
        return

    try:
        korisnik = message.from_user
        username = f"@{korisnik.username}" if korisnik.username else korisnik.first_name
        user_id = korisnik.id

        pronadjeni_kodovi = re.findall(KOD_REGEX, message.text)
        if not pronadjeni_kodovi:
            return

        for kod in pronadjeni_kodovi:
            kod_velika = kod.upper()
            uspesno, status = dodaj_kod(kod_velika, username, user_id)
            
            if uspesno:
                tekst_poruke = (
                    f"🚨 <b>NOVI KOD OD OSNIVAČA:</b> {username}\n\n"
                    f"Pridruži se PERIA grupi za rudarenje!\n"
                    f"Otvori <b>MiningPeria → Mining → Custom</b>\n\n"
                    f"👉 <i>Kliknite na dugme ispod da preuzmete kod!</i>\n\n"
                    f"📊 Popunjeno: <b>1/30</b>\n"
                    f"⏱ Važi još: <b>60 min</b>"
                )
                
                nova_poruka = await message.answer(
                    tekst_poruke,
                    parse_mode=ParseMode.HTML,
                    reply_markup=napravi_tastaturu_za_kod(kod_velika, 1)
                )
                
                try:
                    await message.delete()
                except Exception:
                    pass

                try:
                    await bot.pin_chat_message(
                        chat_id=message.chat.id,
                        message_id=nova_poruka.message_id,
                        disable_notification=False
                    )
                except Exception:
                    pass
            elif status == "KOD_POSTOJI":
                await message.answer(f"⚠️ Kod <b>{kod_velika}</b> je već objavljen ranije!", parse_mode=ParseMode.HTML)
            else:
                await message.answer(f"❌ Greška pri upisu u bazu: {status}")

    except Exception as e:
        await message.answer(f"❌ Neočekivana greška u botu: {e}")

async def main():
    print("Bot je pokrenut...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
