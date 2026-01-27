import telegram
import telegram.ext
from database import Database
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

import html

import utils

import psutil
import shutil
import platform

from dotenv import load_dotenv
import os
import config

load_dotenv()
# Povezava z bazo - use config's DB_PATH which respects TEST_BOT mode
db = Database(config.DB_PATH)


# ===== DEV MODE MESSAGE ROUTING =====
async def send_message(context, chat_id, text, parse_mode="HTML", **kwargs):
    """
    Smart message sender that respects DEV_MODE.
    If DEV_MODE=1, routes all messages to ADMIN_ID only.
    """
    from config import TEST_BOT, DEV_MODE, ADMIN_ID
    
    target_chat = chat_id
    msg_text = text
    
    # If dev mode enabled, route to admin only
    if (TEST_BOT or DEV_MODE) and ADMIN_ID:
        target_chat = int(ADMIN_ID)
        if isinstance(msg_text, str):
            msg_text = f"🧪 <b>[DEV MODE]</b> [Original target: {chat_id}]\n\n{msg_text}"
    
    try:
        return await context.bot.send_message(
            chat_id=target_chat,
            text=msg_text,
            parse_mode=parse_mode,
            **kwargs
        )
    except Exception as e:
        print(f"❌ Error sending message to {target_chat}: {e}")
        return None


async def start_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    user = update.effective_user
    if not user: return

    # 1. Registracija v bazi
    is_new = db.register_user(user.id, user.first_name, user.username)

    if is_new:
        # --- OBVESTILO ZA ADMINA ---
        # Uporabimo html.escape, da ime kot npr. <Luka> ne zruši bota
        safe_name = html.escape(user.first_name)
        safe_username = html.escape(user.username) if user.username else "Nima"
        
        admin_alert = (
            "🔔 <b>NOV UPORABNIK!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 Ime: <b>{safe_name}</b>\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"🏷 Username: @{safe_username}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🚀 Sistem mu je avtomatsko podelil <b>TRIAL</b> paket."
        )
        try:
            # KLJUČNO: ADMIN_ID spremenimo v int(), da Telegram ne vrne errorja
            await send_message(context, int(ADMIN_ID), admin_alert, parse_mode="HTML")
        except Exception as e:
            print(f"Napaka pri obveščanju admina: {e}")

        # Sporočilo za novega uporabnika
        msg = (
            f"Pozdravljen, <b>{safe_name}</b>! 👋\n\n"
            "Sem MarketPulse - tvoj osebni asistent za sledenje novim oglasom.\n Ker si nov, sem ti pravkar "
            "avtomatsko aktiviral <b>3-dnevni BREZPLAČNI PREIZKUS (TRIAL)</b>! 🎉\n\n"
            "<b>Tvoj paket vključuje:</b>\n"
            "• 1 URL za sledenje\n"
            "• Osveževanje na 15 minut\n\n"
            "Da začneš, mi pošlji URL z ukazom <code>/add_url</code> ali poglej navodila na /help."
        )
        db.log_user_activity(user.id, "/start", "Nov uporabnik - Trial aktiviran")
    else:
        # Sporočilo za obstoječega uporabnika
        safe_name = html.escape(user.first_name)
        msg = (
            f"Pozdravljen nazaj, <b>{safe_name}</b>! 👋\n\n"
            "Tvoj profil je že aktiven. Za pregled tvojih iskanj uporabi /list, "
            "za več informacij o paketu pa /info."
        )
        db.log_user_activity(user.id, "/start", "Povratek starega uporabnika")

    await update.message.reply_text(msg, parse_mode="HTML")


async def add_url_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from scraper.avtonet.scraper import Scraper
    import utils 
    
    msg_obj = update.effective_message
    if not msg_obj:
        return

    if not context.args:
        await msg_obj.reply_text("❌ <b>Manjka URL!</b>\nPrimer: <code>/add_url https://www.avto.net/...</code>", parse_mode="HTML")
        return

    raw_url = context.args[0]
    t_id = update.effective_user.id
    t_name = update.effective_user.first_name

    # 1. Validacija linka
    is_avtonet = "avto.net" in raw_url.lower() and "results.asp" in raw_url.lower()
    is_bolha = "bolha.com" in raw_url.lower()
    
    if not (is_avtonet or is_bolha):
        db.log_user_activity(t_id, "/add_url", f"ZAVRNJENO: Neveljaven link")
        await msg_obj.reply_text(
            "❌ <b>NAPAKA: To ni veljaven iskalni link!</b>\n\n"
            "Pojdi na Avto.net ali Bolha.com, nastavi filtre in kopiraj <b>celoten</b> naslov iz brskalnika.",
            parse_mode="HTML"
        )
        return

    # 2. Čiščenje in popravek sortiranja
    if is_avtonet:
        fixed_url = utils.fix_avtonet_url(raw_url)
    elif is_bolha:
        fixed_url = utils.fix_bolha_url(raw_url)
    else:
        fixed_url = raw_url

    # 3. Preveri naročnino in limite
    user_info = db.get_user_subscription_info(t_id)
    if not user_info:
        await msg_obj.reply_text("❌ Tvoj profil ni registriran. Uporabi /start.", parse_mode="HTML")
        return

    if user_info['current_url_count'] >= user_info['max_urls']:
        db.log_user_activity(t_id, "/add_url", f"ZAVRNJENO: Dosežen limit")
        await msg_obj.reply_text(
            f"🚫 <b>Limit dosežen!</b>\n\n"
            f"Tvoj paket {user_info['subscription_type']} dovoljuje največ <code>{user_info['max_urls']}</code> iskanj.\n"
            "Za več mest kontaktiraj admina.",
            parse_mode="HTML"
        )
        return

    # 3.5. Validacija URL-ja: Preveri, če ima redno ponudbo (ne samo izpostavljene oglase)
    validation_msg = await msg_obj.reply_text("🔍 Preverjam URL...")
    try:
        if is_bolha:
            from scraper.bolha.scraper import Scraper as BolhaScraper
            from bs4 import BeautifulSoup
            test_scraper = BolhaScraper(db)
            test_html, _, test_status = test_scraper.get_latest_offers(fixed_url)
            if test_status == 200:
                soup = BeautifulSoup(test_html, 'html.parser')
                # Check if EntityList--Regular section exists (indicates regular user listings)
                regular_section = soup.find('section', class_='EntityList--Regular')
                if not regular_section:
                    await validation_msg.edit_text(
                        "❌ <b>URL ZAVRNJEN!</b>\n\n"
                        "Ta iskalna stran je <b>premalo specifična</b> - ima samo izpostavljene oglase (ni redne ponudbe).\n\n"
                        "Poskusi s konkretnejšo kategorijo, npr:\n"
                        "• bolha.com/avtodeli\n"
                        "• bolha.com/racunalnistvo\n"
                        "• bolha.com/elektronika",
                        parse_mode="HTML"
                    )
                    db.log_user_activity(t_id, "/add_url", f"ZAVRNJENO: Ni redne ponudbe")
                    return
                else:
                    test_ads = test_scraper.extract_all_ads(test_html)
                    await validation_msg.edit_text(f"✅ Najdeno {len(test_ads)} oglasov...")
            else:
                await validation_msg.delete()
        # Za Avtonet je logika že implementirana, zato preskoči
    except Exception as e:
        print(f"URL validation error: {e}")
        await validation_msg.delete()

    # 4. Dodajanje v bazo
    status, new_url_id = db.add_search_url(t_id, fixed_url)

    if status == "exists":
        await msg_obj.reply_text("ℹ️ Temu URL-ju že slediš! Ni ga treba dodajati dvakrat.", parse_mode="HTML")
        return
    elif status is True:
        db.log_user_activity(t_id, "/add_url", f"Dodan URL ID: {new_url_id}")
        
        # --- KLJUČNI POPRAVEK: Preverimo, če je uporabnik sploh aktiven ---
        if user_info.get('is_active'):
            # UPORABNIK JE AKTIVEN - Standardni sync in uspeh
            sync_msg = await msg_obj.reply_text("⏳ Sinhroniziram trenutne oglase (tiha sinhronizacija)...")
            try:
                # Izberemo pravilni scraper glede naURL
                if is_avtonet:
                    temp_scraper = Scraper(db)
                    url_bin = fixed_url.encode('latin-1', 'ignore')
                    pending_data = [{
                        'url_id': new_url_id, 
                        'url': fixed_url, 
                        'url_bin': url_bin,
                        'telegram_name': t_name
                    }]
                    await asyncio.to_thread(temp_scraper.run, pending_data)
                elif is_bolha:
                    from scraper.bolha.scraper import Scraper as BolhaScraper
                    bolha_scraper = BolhaScraper(db)
                    print(f"[BOLHA ADD_URL] Scraping: {fixed_url}")
                    ads = await asyncio.to_thread(bolha_scraper.run_with_pagination, fixed_url)
                    print(f"[BOLHA ADD_URL] Found {len(ads) if ads else 0} ads")
                    if ads:
                        saved = await asyncio.to_thread(bolha_scraper.save_ads_to_scraped_data, ads, new_url_id)
                        print(f"[BOLHA ADD_URL] Saved {saved} ads to ScrapedData")
                
                await sync_msg.edit_text(
                    "✅ <b>Iskanje uspešno dodano!</b>\n\n"
                    "Sistem si je zapomnil trenutno ponudbo. Obvestim te takoj, ko se pojavi kakšen <b>nov</b> oglas! 🚀",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Sync Error: {e}")
                await sync_msg.edit_text("✅ <b>Iskanje dodano!</b>\nSinhronizacija bo končana ob naslednjem pregledu.", parse_mode="HTML")
        else:
            # UPORABNIK JE NEAKTIVEN - Samo shranimo link, a ne skeniramo
            await msg_obj.reply_text(
                "⚠️ <b>Iskanje dodano, VENDAR...</b>\n\n"
                "Tvoj profil trenutno <b>ni aktiven</b> 🔴. Iskanje je varno shranjeno, vendar bot ne bo preverjal oglasov, dokler ne podaljšaš naročnine.\n\n"
                "Preveri ponudbo z ukazom /packages",
                parse_mode="HTML"
            )
    else:
        await msg_obj.reply_text("❌ Prišlo je do napake pri vpisu v bazo. Poskusi kasneje.")



async def remove_url_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Prosim navedi ID iskanja. Primer: `/remove_url 5`", parse_mode="Markdown")
        return

    input_id = context.args[0]
    
    # Preverimo, če je vpisana številka
    if not input_id.isdigit():
        await update.message.reply_text("⚠️ ID mora biti številka!")
        return

    t_id = update.effective_user.id
    
    # Uporabimo tvojo obstoječo funkcijo
    if db.remove_subscription_by_id(t_id, int(input_id)):
        # --- LOGGING USPEHA ---
        db.log_user_activity(t_id, "/remove_url", f"Uspešno izbrisal ID: {input_id}")
        # ----------------------
        await update.message.reply_text(f"🗑️ Iskanje z ID `{input_id}` je bilo uspešno odstranjeno.", parse_mode="Markdown")
    else:
        # --- LOGGING NAPAKE (Če ID ne obstaja ali ni pravi) ---
        db.log_user_activity(t_id, "/remove_url", f"Neuspešen izbris (ID {input_id} ne obstaja)")
        # ----------------------
        await update.message.reply_text("❓ Iskanja s tem ID-jem nismo našli na tvojem seznamu.")


async def list_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    urls = db.get_user_urls_with_status(user_id)
    user_info = db.get_user_subscription_info(user_id)

    if not urls:
        await update.message.reply_text("Trenutno nimaš shranjenih iskanj. Dodaj jih z <code>/add_url</code>.", parse_mode="HTML")
        return

    msg = "📋 <b>TVOJA ISKANJA</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"
    
    # Shranimo prvi ID za primer v navodilih spodaj
    example_id = urls[0]['url_id']

    for u in urls:
        status_emoji = "✅" if u['active'] else "⏸️"
        
        # Determine source based on URL
        if "bolha.com" in u['url'].lower():
            source = "Bolha.com"
        else:
            source = "Avto.net"
        
        msg += f"{status_emoji} <b>ID: {u['url_id']}</b> - "
        msg += f"<a href='{u['url']}'>Odpri iskanje na {source}</a>\n"
        
        if not u['active']:
            msg += "<i>(Zamrznjeno - nad limitom paketa)</i>\n"
        msg += "──────────────────\n"

    if user_info:
        status_text = "🟢 Aktiven" if user_info['is_active'] else "🔴 Neaktiven"
        msg += f"\n📊 Zasedenost: <b>{len(urls)} / {user_info['max_urls']}</b> mest\n"
        msg += f"📦 Paket: <b>{user_info['subscription_type']}</b> ({status_text})\n"
        
        if not user_info['is_active']:
            msg += "\n⚠️ <b>POZOR:</b> Tvoj profil je neaktiven, zato bot ne skenira teh linkov!"

    msg += "\n\n🗑️ <b>ODSTRANITEV ISKANJA:</b>\n"
    msg += f"Za izbris uporabi ukaz <code>/remove_url {example_id}</code>"

    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)



async def info_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    # 1. Pridobimo CELOTEN objekt uporabnika
    user_obj = update.effective_user
    if not user_obj:
        return

    # 2. Shranimo ID v ločeno spremenljivko za lažje delo
    t_id = user_obj.id

    # 3. OSVEŽIMO PODATKE V BAZI (Tukaj je bila napaka)
    # user_obj.id je številka, user_obj.first_name je besedilo, user_obj.username je @handle
    db.register_user(t_id, user_obj.first_name, user_obj.username)
    
    # 4. Pridobimo podatke za izpis
    user_data = db.get_user(t_id)
    pregledi_24h = db.get_user_stats_24h(t_id)
    
    if not user_data:
        await update.message.reply_text("Nisi registriran. Uporabi /start.")
        return

    status_icon = "🟢" if user_data.get('is_active') else "🔴"

    msg = (
        "ℹ️ <b>INFORMACIJE O PROFILU</b>\n\n"
        f"👤 <b>Uporabnik:</b> <code>{t_id}</code>\n"
        f"📦 <b>Paket:</b> <code>{user_data.get('subscription_type', 'NONE')}</code>\n"
        f"✅ <b>Status:</b> {status_icon} {'Aktiven' if user_data.get('is_active') else 'Neaktiven'}\n"
        f"⏳ <b>Veljavnost do:</b> <code>{user_data.get('subscription_end', '---')}</code>\n\n"
        f"📊 <b>MOJI LIMITI:</b>\n"
        f"• URL Limit: <code>{user_data.get('max_urls', 1)}</code> iskanj\n"
        f"• Interval: <code>{user_data.get('scan_interval', 15)} min</code>\n\n"
        f"----------------------------------\n"
        f"🔍 <b>Skeniranj zate (24h):</b> <code>{pregledi_24h}</code>\n"
        f"----------------------------------\n"
        "<i>Številka zgoraj prikazuje, kolikokrat smo zate danes obiskali Avto.net.</i>"
    )
    
    # Gumbi
    keyboard = [
        [
            InlineKeyboardButton("📖 Pomoč", callback_data='help_cmd'),
            InlineKeyboardButton("💎 Paketi", callback_data='packages_cmd')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    db.log_user_activity(t_id, "/info", "Pregled profila (osvežitev)")
    
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=reply_markup)


async def help_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Navodila za uporabo bota. Deluje na ukaz in na gumb."""
    # Pridobimo sporočilo, na katerega odgovorimo (ne glede na to ali je gumb ali tekst)
    target_msg = update.effective_message
    if not target_msg:
        return

    msg = (
        "<b>📖 NAVODILA ZA UPORABO</b>\n\n"
        "1️⃣ <b>Pripravi iskanje:</b>\n"
        "Pojdi na Avto.net in nastavi filtre (znamka, cena, letnik...).\n\n"
        "2️⃣ <b>⚠️ NUJEN KORAK:</b>\n"
        "Rezultate obvezno razvrsti po <b>'datumu objave (najnovejši zgoraj)'</b>. "
        "Brez tega koraka bot morda ne bo zaznal novih oglasov takoj!\n\n"
        "3️⃣ <b>Kopiraj URL:</b>\n"
        "Kopiraj celoten naslov iz brskalnika.\n\n"
        "4️⃣ <b>Dodaj v bota:</b>\n"
        "Vpiši: <code>/add_url tvoj_link</code>\n\n"
        "🚀 <b>In to je to!</b> Bot te bo obvestil takoj, ko AI zazna nov oglas.\n\n"
        "<b>SEZNAM UKAZOV:</b>\n"
        "• <code>/list</code> - Pregled in status tvojih iskanj\n"
        "• <code>/remove_url ID</code> - Izbris iskanja\n"
        "• <code>/info</code> - Status tvojega profila\n"
        "• <code>/packages</code> - Pregled paketov"
    )

    await target_msg.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def packages_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Prikaže prodajni meni s paketi. Vključen novi SOLO paket."""
    from config import SUBSCRIPTION_PACKAGES
    
    target_msg = update.effective_message
    user_id = update.effective_user.id
    if not target_msg:
        return
    
    msg = "<b>📦 RAZPOLOŽLJIVI PAKETI</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"
    
    for code, pkg in SUBSCRIPTION_PACKAGES.items():
        if code == "CUSTOM": continue 
        
        # Izbira emojija za vizualno hierarhijo
        emoji = "🆓" # TRIAL
        if code == "SOLO": emoji = "👤"   # Novo: Osebni paket
        if code == "BASIC": emoji = "🚗"
        if code == "PRO": emoji = "🔥"
        if code == "ULTRA": emoji = "⚡"
        if code == "VIP": emoji = "💎"
        
        # Poseben izpis za VIP in TRIAL (brez decimalk pri ceni)
        if code == "VIP" or code == "TRIAL":
            price_display = "BREZPLAČNO" if code == "TRIAL" else pkg['price']
            msg += (
                f"{emoji} <b>{pkg['label']} ({code})</b>\n"
                f"• Št. URL-jev: <b>{pkg['urls']}</b>\n"
                f"• Osveževanje: <b>{pkg['interval']}</b>\n"
                f"• Cena: <b>{price_display}</b>\n\n"
            )
        else:
            # Standardni paketi s formatirano ceno
            msg += (
                f"{emoji} <b>{pkg['label']} ({code})</b>\n"
                f"• Št. URL-jev: <code>{pkg['urls']}</code>\n"
                f"• Osveževanje: <code>{pkg['interval']} min</code>\n"
                f"• Cena: <b>{float(pkg['price']):.2f}€ / mesec</b>\n\n"
            )

    # --- NOVO: RAZDELEK ZA POPUSTE NA DALJŠI ZAKUP ---
    msg += "<b>🎁 POSEBNA PONUDBA (Večmesečni nakupi):</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += "• 3 meseci: <b>-10% POPUSTA</b>\n"
    msg += "• 6 mesecev: <b>-25% POPUSTA</b> 🔥 <i>(Priporočeno)</i>\n"
    
    
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"🆔 <b>Tvoj ID za aktivacijo:</b> <code>{user_id}</code>\n"
    msg += "<i>(Klikni na številko zgoraj, da jo kopiraš)</i>\n\n"
    
    msg += '💳 <b>Za nakup piši adminu:</b> <a href="https://t.me/JanJu_123">JanJu</a>'
    
    await target_msg.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)





async def broadcast_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return

    # Pridobimo surovo besedilo celotnega sporočila
    raw_text = update.effective_message.text
    
    # Odrežemo ukaz '/broadcast' z začetka (prvih 10 ali 11 znakov)
    if not raw_text or len(raw_text.split()) <= 1:
        await update.message.reply_text("❌ Vpiši sporočilo!")
        return

    # To odreže "/broadcast " in obdrži vse ENTER-je in presledke
    vsebina = raw_text.split(None, 1)[1]

    # Sestavimo sporočilo (pazimo, da ne uporabljamo ponovno join(args))
    sporočilo = (
        "📢 <b>OBVESTILO ADMINA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{vsebina}"
    )
    
    vsi_id = db.get_all_chat_ids()
    print(f"📣 [BROADCAST] Pošiljam {len(vsi_id)} uporabnikom...")
    
    poslano = 0
    for chat_id in vsi_id:
        try:
            await send_message(context, chat_id=chat_id, text=sporočilo, parse_mode="HTML")
            poslano += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Ni mogoče poslati {chat_id}: {e}")
            continue

    await update.message.reply_text(f"✅ Poslano <b>{poslano}</b> uporabnikom.", parse_mode="HTML")


async def list_users_admin(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return

    users = db.get_all_users_admin()
    if not users:
        await update.message.reply_text("Baza je prazna.")
        return

    # Definiramo širine stolpcev za monospace pisavo
    # Ker so emojiji široki, bomo uporabili fiksne presledke
    w_pkg = 5   # BAS, PRO, ULT
    w_id = 10   # ID
    w_name = 10 # IME
    w_hnd = 10  # HANDLE

    # Sestavimo GLAVO tabele
    # Dodamo 3 presledke na začetku, da se ujema z emoji-jem spodaj
    header = f"   {'PKG':<{w_pkg}} | {'ID':<{w_id}} | {'IME':<{w_name}} | {'HANDLE':<{w_hnd}} | {'EXP'}"
    separator = "-" * len(header)
    
    table_rows = [header, separator]

    for row in users:
        u = dict(row)
        
        # Emoji status
        st = "💎" if u['is_active'] else "❌"
        
        # --- VARNI PREVZEM PAKETA ---
        pkg_map = {"TRIAL": "TRI", "BASIC": "BAS", "PRO": "PRO", "ULTRA": "ULT", "VIP": "VIP", "NONE": "---"}
        raw_pkg = u.get('subscription_type')
        pkg = pkg_map.get(raw_pkg.upper(), "---") if raw_pkg else "---"
        
        uid = str(u['telegram_id'])
        
        # Ime (skrajšamo na 10)
        name = u['telegram_name'] or "Neznan"
        if len(name) > w_name: name = name[:w_name-1] + "."
        
        # Handle (skrajšamo na 10)
        hnd = u.get('telegram_username') or "---"
        if len(hnd) > w_hnd: hnd = hnd[:w_hnd-1] + "."
        
        # Datum (samo DD.MM)
        exp = "---"
        if u['subscription_end']:
            try:
                parts = u['subscription_end'].split(".")
                exp = f"{parts[0]}.{parts[1]}"
            except:
                exp = "err"

        # Sestava vrstice
        line = f"{st} {pkg:<{w_pkg}} | {uid:<{w_id}} | {name:<{w_name}} | {hnd:<{w_hnd}} | {exp}"
        table_rows.append(line)


    # VSE združimo v en sam <pre> blok
    # To prepreči prelamljanje in omogoči horizontalni scroll
    final_table = "\n".join(table_rows)
    msg = f"👥 <b>ADMIN DASHBOARD</b>\n\n<pre>{final_table}</pre>"

    await update.message.reply_text(msg, parse_mode="HTML")
    

async def activate_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID, SUBSCRIPTION_PACKAGES
    if str(update.effective_user.id) != str(ADMIN_ID): 
        return

    try:
        # /activate <ID> <PAKET> <DNI>
        args = context.args
        if len(args) < 3:
            raise ValueError("Premalo argumentov")

        target_user_id = args[0]
        pkg_name = args[1].upper()
        days = int(args[2])

        # Določimo limite na podlagi paketa
        if pkg_name == "CUSTOM":
            # /activate <ID> CUSTOM <DNI> <URLS> <MIN>
            max_urls = int(args[3])
            interval = int(args[4])
        elif pkg_name in SUBSCRIPTION_PACKAGES:
            pkg_info = SUBSCRIPTION_PACKAGES[pkg_name]
            max_urls = pkg_info['urls']
            interval = pkg_info['interval']
        else:
            await update.message.reply_text(f"❌ Paket '{pkg_name}' ne obstaja.")
            return

        # POKLIČEMO POSODOBLJENO METODO (ki sama sešteje dni!)
        # Vrstni red: telegram_id, pkg_type, max_urls, interval, days_to_add
        new_expiry = db.update_user_subscription(
            target_user_id, 
            pkg_name, 
            max_urls, 
            interval, 
            days
        )

        await update.message.reply_text(
            f"🚀 <b>UPORABNIK NADGRAJEN</b>\n\n"
            f"👤 ID: <code>{target_user_id}</code>\n"
            f"📦 Paket: <b>{pkg_name}</b>\n"
            f"🔗 Limit: <b>{max_urls} URL / {interval} min</b>\n"
            f"📅 Novo veljavnost: <b>{new_expiry}</b>\n\n"
            f"<i>(Dnevi so bili uspešno prišteti obstoječi naročnini!)</i>",
            parse_mode="HTML"
        )
        
        # Obvestimo še uporabnika, da je dobil podaljšanje
        try:
            await send_message(
                context,
                chat_id=target_user_id,
                text=f"🎉 <b>Tvoja naročnina je bila podaljšana!</b>\n\nNov datum poteka: <code>{new_expiry}</code>",
                parse_mode="HTML"
            )
        except:
            pass

    except Exception as e:
        print(f"Napaka pri aktivaciji: {e}")
        await update.message.reply_text(
            "❌ <b>NAPAKA PRI UKAZU</b>\n\n"
            "Uporaba: <code>/activate &lt;ID&gt; &lt;PAKET&gt; &lt;DNI&gt;</code>\n"
            "Primer: <code>/activate 8004323652 PRO 30</code>",
            parse_mode="HTML"
        )



# 2. Ukaz za deaktivacijo: /deactivate <ID>
async def deactivate_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID):
        return

    try:
        u_id = int(context.args[0])
        db.update_user_status(u_id, sub_type=None)
        
        await update.message.reply_text(f"🚫 Uporabnik `{u_id}` je bil deaktiviran.")
        await send_message(context, chat_id=u_id, text="⚠️ Tvoja naročnina je potekla ali bila preklicana. Za podaljšanje kontaktiraj admina.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uporabi: `/deactivate ID`", parse_mode="Markdown")


async def admin_overview_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return

    conn = db.get_connection()
    c = conn.cursor()

    # 1. Razvrstitev po paketih
    stats_pkg = c.execute("SELECT subscription_type, COUNT(*) FROM Users GROUP BY subscription_type").fetchall()
    
    # 2. Kdo nima URL-jev (Ghost users)
    ghosts = c.execute("""
        SELECT telegram_name, telegram_id FROM Users 
        WHERE telegram_id NOT IN (SELECT telegram_id FROM Tracking)
        AND is_active = 1
    """).fetchall()

    # 3. Kdo ima pokvarjene linke (Fails)
    failed_links = c.execute("""
        SELECT us.telegram_name, u.url_id FROM Urls u 
        JOIN Tracking t ON u.url_id = t.url_id 
        JOIN Users us ON t.telegram_id = us.telegram_id 
        WHERE u.fail_count > 0
    """).fetchall()

    msg = "📊 <b>SUPER ADMIN PREGLED</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"
    
    msg += "📦 <b>STATISTIKA PAKETOV:</b>\n"
    for pkg in stats_pkg:
        msg += f"• {pkg[0]}: <b>{pkg[1]}</b>\n"
    
    msg += "\n👻 <b>GHOST UPORABNIKI (Brez linkov):</b>\n"
    if ghosts:
        for g in ghosts:
            msg += f"• {g[0]} (<code>{g[1]}</code>)\n"
    else:
        msg += "<i>Vsi so aktivni!</i>\n"

    msg += "\n⚠️ <b>PROBLEMATIČNI LINKI:</b>\n"
    if failed_links:
        for f in failed_links:
            msg += f"• {f[0]} (URL ID: {f[1]})\n"
    else:
        msg += "<i>Vsi linki delujejo BP.</i>\n"

    await update.message.reply_text(msg, parse_mode="HTML")


def get_todays_requests_count(self):
    """Prešteje vse requeste v tabeli UserRequests za tekoči dan."""
    conn = self.get_connection()
    cursor = conn.cursor()
    # Prešteje zapise, ki so se zgodili danes
    cursor.execute("SELECT COUNT(*) FROM UserRequests WHERE date(timestamp) = date('now')")
    count = cursor.fetchone()[0]
    conn.close()
    return count

async def admin_stats_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID, DB_PATH
    if str(update.effective_user.id) != str(ADMIN_ID): return
    
    db = Database(DB_PATH)
    stats = db.get_admin_stats()

    req_danes = stats.get('requesti_danes', 0)
    cost_danes = stats.get('cost_danes', 0)
    mins_today = stats.get('minutes_today', 1)
    

    req_per_min = req_danes / mins_today
    cost_per_1k = (cost_danes / req_danes * 1000) if req_danes > 0 else 0

    msg = (
        "📊 <b>ADMIN STATISTIKA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📅 <b>DANES (od 00:00):</b>\n"
        f"🌐 Skupaj requestov: <b>{req_danes}</b>\n"
        f"⚡ Obremenitev: <b>{req_per_min:.1f} req/min</b>\n"
        f"💰 Realen strošek: <b>{cost_danes:.4f}€</b>\n"
        f"📉 Cena / 1000 skenov: <b>{cost_per_1k:.2f}€</b>\n\n"
        "👤 <b>PORABA PO UPORABNIKIH (Danes):</b>\n"
    )

    # Sortirani uporabniki po porabi
    day_breakdown = stats.get('user_breakdown_day', [])
    if not day_breakdown:
        msg += "<i>Danes še ni bilo aktivnosti.</i>\n"
    for row in day_breakdown:
        name = row['telegram_name'] or "Neznan"
        msg += f"• {name}: <code>{row['cnt']}</code> req\n"

    msg += (
        "\n🗓️ <b>TEKOČI MESEC:</b>\n"
        f"👥 Uporabniki: <b>{stats['skupaj_uporabnikov']}</b>\n"
        f"🔗 Aktivni URL-ji: <b>{stats['aktivni_urlji']}</b>\n"
        f"🌐 Skupaj requestov: <b>{stats['requesti_mesec']}</b>\n"
        f"💳 Realen strošek: <b>{stats['cost_mesec']:.2f}€</b>\n\n"
        "🏆 <b>TOP PORABNIKI (Mesec):</b>\n"
    )

    month_breakdown = stats.get('user_breakdown_month', [])
    for row in month_breakdown[:5]: # Pokažemo le Top 5 za preglednost
        name = row['telegram_name'] or "Neznan"
        msg += f"👤 {name}: <code>{row['cnt']}</code> req\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def health_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return
    
    stats = db.get_admin_health_stats()
    if not stats or stats['total_scans'] == 0:
        await update.message.reply_text("Nekaj je narobe, v zadnjih 24h ni zapisov o skeniranju.")
        return

    mb_used = round((stats['total_bytes'] or 0) / (1024 * 1024), 2)
    
    msg = (
        "📊 **SISTEMSKO ZDRAVJE (24h)**\n\n"
        f"🔄 Skupaj skenov: `{stats['total_scans']}`\n"
        f"⏱ Povprečni čas: `{round(stats['avg_time'], 2)}s`\n"
        f"💾 Poraba podatkov: `{mb_used} MB`\n"
        f"🚫 Število napak: `{stats['errors']}`\n"
    )
    
    if stats['errors'] > 0:
        msg += "\n⚠️ *Pozor: Scraper javlja napake. Preveri loge!*"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def check_user_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return
    if not context.args:
        await update.message.reply_text("Uporaba: <code>/check_user ID</code>", parse_mode="HTML")
        return
        
    target_id = context.args[0]
    user = db.get_user(target_id) # tvoja obstoječa funkcija
    url_count = db.get_user_stats_24h(target_id) # tvoja obstoječa funkcija
    
    if not user:
        await update.message.reply_text("Uporabnika ni v bazi.")
        return

    # 1. Pridobimo seznam dejanskih URL-jev
    tracked_urls = db.get_user_tracked_urls(target_id)
    urls_list_text = ""
    for i, u in enumerate(tracked_urls, 1):
        # Skrajšamo prikaz linka, da sporočilo ni predolgo, a ostane klikljivo
        urls_list_text += f"{i}. 🆔 {u['url_id']}: <a href='{u['url']}'>Odpri link</a>\n"
    
    if not urls_list_text:
        urls_list_text = "Uporabnik nima dodanih URL-jev."

    # 2. Pridobimo zadnjih 5 oglasov (iz SentAds)
    # Tukaj uporabi svojo obstoječo logiko ali klic baze
    _, _, last_ads = db.get_user_diagnostic(target_id)
    ads_info = "\n".join([f"• {a['sent_at']}" for a in last_ads]) if last_ads else "Ni še prejel oglasov."

    status_icon = "🟢" if user['is_active'] else "🔴"

    msg = (
        f"🔍 <b>DIAGNOZA: {user.get('telegram_name', 'Neznan')}</b> (<code>{target_id}</code>)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Paket:</b> {user['subscription_type']}\n"
        f"⏳ <b>Poteče:</b> <code>{user['subscription_end']}</code>\n"
        f"✅ <b>Status:</b> {status_icon} {'Aktiven' if user['is_active'] else 'Neaktiven'}\n"
        f"⏱ <b>Interval:</b> {user['scan_interval']} min\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>TRENUTNA ISKANJA ({len(tracked_urls)}/{user['max_urls']}):</b>\n"
        f"{urls_list_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📨 <b>ZADNJA OBVESTILA:</b>\n"
        f"{ads_info}"
    )

    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def admin_help_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return
        
    msg = (
        "👑 <b>ADMIN KOMANDNI CENTER</b>\n\n"
        "📊 <b>Sistem & Nadzor</b>\n"
        "• `/overview` - <b>Pregled 'duhov' in pokvarjenih linkov</b>\n"
        "• `/server` - Poraba virov (RAM/CPU)\n"
        "• `/health` - Status scraperja (24h)\n"
        "• `/proxy_stats` - Stroški in napoved\n"
        "• `/logs` - Zadnjih 5 tehničnih zapisov\n\n"
        
        "👥 <b>Uporabniki</b>\n"
        "• `/users` - Seznam vseh uporabnikov\n"
        "• `/check_user ID` - Diagnoza in seznam linkov\n"
        "• `/activate ID TIP DNI` - Podaljšaj (ali vklopi trial)\n"
        "• `/deactivate ID` - Hard reset statusa na 0\n\n"
        
        "📢 <b>Komunikacija</b>\n"
        "• `/broadcast TEXT` - Pošlji vsem obvestilo\n"
        "• `/admin_stats` - Hitra statistika baze"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def handle_message(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "živjo" in text or "hello" in text:
        await update.message.reply_text("Živjo! Kako ti lahko pomagam?")
    else:
        await update.message.reply_text("Ne razumem tega ukaza. Poskusi z /info.")

async def proxy_stats_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID, PROXY_PRICE_GB
    if str(update.effective_user.id) != str(ADMIN_ID): return

    # Nastavi svojo ceno na GB (npr. 5€)

    
    stats = db.get_proxy_cost_analysis(PROXY_PRICE_GB)
    
    # Izračunamo še "Efficiency" (koliko KB na en najden oglas)
    # To ti pove, če preveč skeniraš prazne URL-je
    
    msg = (
        "💸 **FINANČNA ANALIZA PROXYJEV**\n\n"
        f"💰 Cena: `{PROXY_PRICE_GB}€ / GB`\n"
        "------------------\n"
        f"📅 **Danes:**\n"
        f"• Poraba: `{round(stats['daily_gb'] * 1024, 2)} MB`\n"
        f"• Strošek: `{round(stats['daily_cost'], 4)}€`\n\n"
        
        f"📈 **Napoved (30 dni):**\n"
        f"• Predviden promet: `{round(stats['avg_daily_gb'] * 30, 2)} GB`\n"
        f"• Predviden strošek: `€{round(stats['monthly_projection'], 2)}`\n"
        "------------------\n"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def admin_logs_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from main import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): 
        return

    # 1. Sistemski logi (zdaj UserActivity)
    activities = db.get_recent_system_logs(5)
    
    msg = "📜 **ZADNJE AKTIVNOSTI:**\n"
    for act in activities:
        # Prilagojeno stolpcem: timestamp, command, details
        msg += f"`{act['timestamp']}` | `{act['command']}`: {act['details']}\n"

    # 2. Scraper logi (to že imaš in bi moralo delovati)
    scrap_logs = db.get_scraper_health(5)
    msg += "\n**SKENIRANJA:**\n"
    for log in scrap_logs:
        kb = round(log['bytes_used'] / 1024, 1) if log['bytes_used'] else 0
        msg += f"ID:{log['url_id']} | {log['found_count']} oglasov | {kb}KB | {log['duration']}s\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def server_status_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return

    # 1. Poraba procesorja (CPU)
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # 2. Poraba RAM-a
    ram = psutil.virtual_memory()
    ram_total = round(ram.total / (1024**3), 2)
    ram_used = round(ram.used / (1024**3), 2)
    ram_percent = ram.percent

    # 3. Poraba Diska
    total, used, free = shutil.disk_usage("/")
    disk_total = total // (2**30)
    disk_used = used // (2**30)
    disk_percent = (used / total) * 100

    # 4. Sistemske informacije
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%d.%m.%Y %H:%M:%S")

    msg = (
        "🖥️ <b>STATUS STREŽNIKA (VPS)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 <b>CPU:</b> <code>{cpu_usage}%</code>\n"
        f"🧠 <b>RAM:</b> <code>{ram_used}GB / {ram_total}GB ({ram_percent}%)</code>\n"
        f"💾 <b>DISK:</b> <code>{disk_used}GB / {disk_total}GB ({disk_percent:.1f}%)</code>\n\n"
        "<b>SISTEM:</b>\n"
        f"🐧 OS: <code>Ubuntu {platform.release()}</code>\n"
        f"⏱️ Zadnji zagon: <code>{boot_time}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🚀 <i>Vsi sistemi delujejo normalno.</i>"
    )

    await update.message.reply_text(msg, parse_mode="HTML")


async def add_url_user_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    from scraper.avtonet.scraper import Scraper
    import utils
    
    # 1. Preverba Admina
    if str(update.effective_user.id) != str(ADMIN_ID): return

    try:
        # Ukaz: /add_url_user 12345678 https://www.avto.net/... OR https://www.bolha.com/...
        if len(context.args) < 2:
            raise ValueError

        target_id = context.args[0]
        raw_url = context.args[1]

        # 2. Validacija linka
        is_avtonet = "avto.net" in raw_url.lower() and "results.asp" in raw_url.lower()
        is_bolha = "bolha.com" in raw_url.lower()
        
        if not (is_avtonet or is_bolha):
            await update.message.reply_text("❌ Neveljaven URL! Dovolimo samo Avto.net in Bolha.com iskalne linke.", parse_mode="HTML")
            return

        # 3. Čiščenje URL-ja
        if is_avtonet:
            fixed_url = utils.fix_avtonet_url(raw_url)
        elif is_bolha:
            fixed_url = utils.fix_bolha_url(raw_url)
        else:
            fixed_url = raw_url

        # 4. Dodajanje v bazo (uporabimo tvojo obstoječo metodo)
        status, new_url_id = db.add_search_url(target_id, fixed_url)

        if status == "exists":
            await update.message.reply_text("ℹ️ Uporabnik temu URL-ju že sledi.")
            return
        
        if status is True:
            # 4. Tiha sinhronizacija na VPS (da diler ne dobi 50 sporočil takoj)
            temp_scraper = Scraper(db)
            pending_data = [{'url_id': new_url_id, 'url': fixed_url, 'telegram_name': f"User_{target_id}"}]
            await asyncio.to_thread(temp_scraper.run, pending_data)

            # 5. Obvestilo ADMINU
            await update.message.reply_text(f"✅ URL uspešno dodan uporabniku <code>{target_id}</code> in sinhroniziran.", parse_mode="HTML")
            
            # 6. Obvestilo UPORABNIKU (da vidi, da si mu zrihtal)
            try:
                await send_message(
                    context,
                    chat_id=target_id, 
                    text="🛠️ <b>ADMIN SERVIS:</b>\nSkrbnik ti je pravkar dodal novo iskanje. Bot že išče nove oglase!",
                    parse_mode="HTML"
                )
            except: pass
            
            db.log_user_activity(ADMIN_ID, "/add_url_user", f"Dodal URL ID {new_url_id} uporabniku {target_id}")

    except Exception as e:
        await update.message.reply_text("❌ <b>Napaka!</b>\nUporaba: <code>/add_url_user ID URL</code>", parse_mode="HTML")



async def admin_errors_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if str(update.effective_user.id) != str(ADMIN_ID): return

    # 1. Določimo limit (privzeto 10, ali pa tisto kar napišeš: /errors 20)
    limit = 10
    if context.args and context.args[0].isdigit():
        limit = int(context.args[0])
        # Varnostna omejitev, da sporočilo ni predolgo za Telegram
        if limit > 50: limit = 50

    conn = db.get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 2. Pridobimo zadnjih N napak z imeni uporabnikov
    query = """
        SELECT u.telegram_name, sl.url_id, sl.status_code, sl.error_msg, sl.timestamp
        FROM ScraperLogs sl
        JOIN Tracking t ON sl.url_id = t.url_id
        JOIN Users u ON t.telegram_id = u.telegram_id
        WHERE sl.status_code != 200
        ORDER BY sl.id DESC
        LIMIT ?
    """
    errors = c.execute(query, (limit,)).fetchall()
    conn.close()

    if not errors:
        await update.message.reply_text(f"✅ V bazi ni zabeleženih napak (preverjeno zadnjih {limit}).")
        return

    msg = f"❌ <b>ZADNJE NAPAKE ({len(errors)})</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n\n"

    for e in errors:
        name = e['telegram_name'] or "Neznan"
        u_id = e['url_id']
        timestamp = e['timestamp'].split(' ')[1] # Samo ura
        err_detail = e['error_msg']
        code = e['status_code']
        
        # 3. Pametne ikone glede na tvojo novo diagnostiko
        if code == 403:
            icon = "🛡️" # Cloudflare
        elif code == 0:
            icon = "🔗" # Napačen link / Network
        elif code >= 500:
            icon = "🛠️" # Server error
        else:
            icon = "⚠️" # Ostalo

        msg += f"{icon} <b>{name}</b> (ID: {u_id})\n"
        msg += f"🕒 {timestamp} | <code>{err_detail}</code>\n"
        msg += "──────────────────\n"

    await update.message.reply_text(msg, parse_mode="HTML")



async def button_callback_handler(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Upravlja klike na gumbe pod sporočili."""
    query = update.callback_query
    
    # ZELO POMEMBNO: Vedno odgovorimo na query, da Telegram odstrani "loading" animacijo na gumbu
    await query.answer()

    if query.data == 'help_cmd':
        # Pokličemo funkcijo za pomoč
        await help_command(update, context)
    
    elif query.data == 'packages_cmd':
        # Pokličemo funkcijo za pakete
        await packages_command(update, context)



async def error(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")


async def post_init(application: telegram.ext.Application) -> None:
    from config import ADMIN_ID
    # 1. Ukazi za navadne uporabnike
    user_commands = [
        BotCommand("start", " Začetek in registracija"),
        BotCommand("add_url", " Dodaj nov URL"),
        BotCommand("list", " Moja iskanja"),
        BotCommand("remove_url", " Izbriši URL"),
        BotCommand("info", "ℹ Moj profil in status"),
        BotCommand("help", " Navodila za uporabo"),
        BotCommand("packages", " Cenik paketov")
    ]
    await application.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # 2. Ukazi samo zate (Admin)
    admin_commands = user_commands + [
        BotCommand("admin", "👑 Admin Center (Pomoč)"),
        BotCommand("admin_overview", "📊 Hitri pregled baze (Ghost/Errors)"),
        BotCommand("server", "🖥️ Status strežnika (RAM/CPU)"),
        BotCommand("admin_stats", "📉 Globalna statistika"),
        BotCommand("proxy_stats", "💸 Stroški proxyjev"),
        BotCommand("health", "🏥 Zdravje sistema"),
        BotCommand("users", "👥 Seznam uporabnikov"),
        BotCommand("check_user", "🔍 Diagnoza uporabnika (ID)"),
        BotCommand("activate", "🚀 Aktiviraj (ID PAKET DNI)"),
        BotCommand("deactivate", "🚫 Deaktiviraj (ID)"),
        BotCommand("add_url_user", "➕ Dodaj URL drugemu uporabniku (ID URL)"),
        BotCommand("send", "✉️ Pošlji direktno sporočilo (ID TEKST)"),
        BotCommand("logs", "📜 Zadnje aktivnosti"),
        BotCommand("broadcast", "📢 Pošlji vsem obvestilo"),
        BotCommand("errors", "Pošlji zadnjih par errorjev")
    ]
    
    try:
        await application.bot.set_my_commands(
            admin_commands, 
            scope=BotCommandScopeChat(chat_id=int(ADMIN_ID))
        )
        print(f"   [OK] Ukazi za Admina in Uporabnike so nastavljeni.")
    except Exception as e:
        print(f"⚠️ Napaka pri nastavljanju admin ukazov: {e}")


async def send_dm_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    # Preverimo, če si to ti
    if str(update.effective_user.id) != str(ADMIN_ID): 
        return

    try:
        # Pričakovan format: /send 12345678 Živjo, kako ti služi bot?
        if len(context.args) < 2:
            raise ValueError("Manjkajo podatki")

        target_id = context.args[0]
        text = " ".join(context.args[1:])
        
        # --- GUMB ZA ODGOVOR ---
        # Zamenjaj 'JanJu_123' s svojim dejanskim Telegram username-om (brez @)
        keyboard = [[InlineKeyboardButton("💬 Piši Janu (Admin)", url="https://t.me/JanJu_123")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        full_msg = (
            "✉️ <b>SPOROČILO SKRBNIKA</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"{text}\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Če imaš vprašanje, klikni spodnji gumb:</i>"
        )
        
        await send_message(
            context,
            chat_id=target_id, 
            text=full_msg, 
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        await update.message.reply_text(f"✅ Sporočilo uspešno poslano uporabniku <code>{target_id}</code>.", parse_mode="HTML")
        db.log_user_activity(update.effective_user.id, "/send", f"Poslal sporočilo ID-ju: {target_id}")

    except Exception as e:
        await update.message.reply_text("❌ <b>Napaka pri pošiljanju!</b>\nUporaba: <code>/send ID SPOROČILO</code>", parse_mode="HTML")




def setup_bot(token):
    app = telegram.ext.Application.builder().token(token).build()

    # Ukazi
    app.add_handler(telegram.ext.CommandHandler("start", start_command))
    app.add_handler(telegram.ext.CommandHandler("list", list_command))
    app.add_handler(telegram.ext.CommandHandler("add_url", add_url_command))
    app.add_handler(telegram.ext.CommandHandler("remove_url", remove_url_command))
    app.add_handler(telegram.ext.CommandHandler("info", info_command))

    # Navadna sporočila
    app.add_handler(telegram.ext.MessageHandler(telegram.ext.filters.TEXT & (~telegram.ext.filters.COMMAND), handle_message))

    app.add_error_handler(error)
    return app

if __name__ == "__main__":
    from main import TOKEN
    print("Bot se zaganja...")
    application = setup_bot(TOKEN)
    application.run_polling()