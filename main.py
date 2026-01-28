import asyncio
import telegram
import telegram.ext
from database import Database
from scraper.avtonet.scraper import Scraper
from scraper.bolha.scraper import Scraper as BolhaScraper
from scraper.nepremicnine.scraper import Scraper as NepremicnineScraper
from data_manager import DataManager
from telegram.ext import CallbackQueryHandler
from scraper.avtonet.master_crawler import run_master_crawler_once

from telegram_bot import start_command, list_command, add_url_command, remove_url_command, info_command, activate_user, \
    deactivate_user, admin_stats_command, admin_help_command, broadcast_command, list_users_admin, admin_logs_command, \
    health_command, check_user_command, proxy_stats_command, packages_command, help_command, post_init, server_status_command, \
    admin_overview_command, send_dm_command, add_url_user_command, button_callback_handler, admin_errors_command, send_message

from dotenv import load_dotenv
import os
import datetime
import pytz

import logging

# ---- LOGGING ---- #
# Nastavitev zapisovanja v datoteko app_debug.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("app_debug.log", encoding='utf-8'),
        logging.StreamHandler() # Da še vedno vidiš v konzoli
    ]
)
logger = logging.getLogger("Main")

# Utišamo hrupne knjižnice (postavimo na WARNING nivo)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# Barve za terminal (ANSI kode)
B_BLUE = "\033[94m"
B_CYAN = "\033[96m"
B_GREEN = "\033[92m"
B_YELLOW = "\033[93m"
B_END = "\033[0m"


# --- KONSTANTE --- #
from config import (
    SUBSCRIPTION_PACKAGES,
    TOKEN,
    DB_PATH,
    ADMIN_ID,
    PROXY_PRICE_GB,
    ENABLE_MASTER_CRAWLER,
    MASTER_CRAWL_INTERVAL,
    TEST_BOT,                           
    DEV_MODE,
)

async def check_for_new_ads(context: telegram.ext.ContextTypes.DEFAULT_TYPE, send_notifications=True):
    def get_time():
        return datetime.datetime.now().strftime('%H:%M:%S')

    print(f"\n{B_CYAN}--- [ PAMETNI CIKEL PREVERJANJA: {get_time()} ] ---{B_END}")
    
    db = Database(DB_PATH)
    
    # Clear previous cycle's ScrapedData snapshot (VPS behavior)
    db.clear_scraped_snapshot()
    
    pending_urls = db.get_pending_urls()
    
    # V razvojnem načinu procesujem samo svoje URL-je (ADMIN_ID)
    if TEST_BOT or DEV_MODE:
        admin_id_int = int(ADMIN_ID)
        pending_urls = [u for u in pending_urls if u.get('telegram_id') == admin_id_int]
    
    if not pending_urls:
        print(f"{B_BLUE}[{get_time()}] IDLE - Noben URL še ni na vrsti.{B_END}")
        return

    pending_ids = [u['url_id'] for u in pending_urls]
    print(f"{B_GREEN}[{get_time()}] START - {len(pending_ids)} URL-jev na vrsti{B_END}")

    # Ločimo URL-je po virih
    avtonet_urls = [u for u in pending_urls if "avto.net" in u['url'].lower()]
    bolha_urls = [u for u in pending_urls if "bolha.com" in u['url'].lower()]
    nepremicnine_urls = [u for u in pending_urls if "nepremicnine.net" in u['url'].lower()]
    
    # Log which URLs are pending
    if avtonet_urls:
        print(f"{B_YELLOW}[{get_time()}] AVTONET - {len(avtonet_urls)} URL(s) pending{B_END}")
    if bolha_urls:
        print(f"{B_YELLOW}[{get_time()}] BOLHA - {len(bolha_urls)} URL(s) pending{B_END}")
    if nepremicnine_urls:
        print(f"{B_YELLOW}[{get_time()}] NEPREMICNINE - {len(nepremicnine_urls)} URL(s) pending{B_END}")
    
    manager = DataManager(db)

    # Avtonet obdelava (obstoječa logika)
    if avtonet_urls:
        scraper = Scraper(DataBase=db)
        await asyncio.to_thread(scraper.run, avtonet_urls)
    
    # Bolha obdelava (paralelno za vsak URL)
    if bolha_urls:
        
        async def process_bolha_url(url_entry):
            bolha_scraper = BolhaScraper(db)
            try:
                print(f"{B_CYAN}[{get_time()}] BOLHA SCAN - URL ID {url_entry['url_id']} ({url_entry.get('telegram_name', 'Neznan')})...{B_END}")
                ads = await asyncio.to_thread(bolha_scraper.run_with_pagination, url_entry['url'])
                if ads:
                    print(f"[{get_time()}] BOLHA - Najdeno {len(ads)} oglasov, shranjevanje...")
                    await asyncio.to_thread(bolha_scraper.save_ads_to_scraped_data, ads, url_entry['url_id'])
            except Exception as e:
                print(f"[{get_time()}] ❌ BOLHA napaka za URL ID {url_entry['url_id']}: {e}")
        
        # Izvrši vse Bolha URL-je paralelno
        await asyncio.gather(*[process_bolha_url(url) for url in bolha_urls]) 

    # Nepremičnine obdelava (paralelno za vsak URL)
    if nepremicnine_urls:
        async def process_nepremicnine_url(url_entry):
            nepremicnine_scraper = NepremicnineScraper(db)
            try:
                print(f"{B_CYAN}[{get_time()}] NEPREMICNINE SCAN - URL ID {url_entry['url_id']} ({url_entry.get('telegram_name', 'Neznan')})...{B_END}")
                html, bytes_used, status_code = await asyncio.to_thread(
                    nepremicnine_scraper.get_latest_offers, url_entry['url']
                )
                
                if status_code == 200 and html:
                    ads = nepremicnine_scraper.extract_all_ads(html)
                    if ads:
                        print(f"[{get_time()}] NEPREMICNINE - Najdeno {len(ads)} oglasov, shranjevanje...")
                        saved = await asyncio.to_thread(
                            nepremicnine_scraper.save_ads_to_scraped_data, ads, url_entry['url_id']
                        )
                        print(f"[{get_time()}] NEPREMICNINE - Shranjeno {saved} novih oglasov")
                    else:
                        print(f"[{get_time()}] NEPREMICNINE - Ni najdenih oglasov")
                else:
                    print(f"[{get_time()}] ❌ NEPREMICNINE fetch napaka (HTTP {status_code})")
            except Exception as e:
                print(f"[{get_time()}] ❌ NEPREMICNINE napaka za URL ID {url_entry['url_id']}: {e}")
        
        # Izvrši vse Nepremičnine URL-je paralelno
        await asyncio.gather(*[process_nepremicnine_url(url) for url in nepremicnine_urls])
    
    failed_ones = db.get_newly_failed_urls()
    for f in failed_ones:
        t_id = f['telegram_id']
        u_id = f['url_id']
        u_name = f['telegram_name']
        
        user_msg = (
            "⚠️ <b>TEŽAVA Z ISKALNIM LINKOM</b>\n\n"
            f"Opazili smo, da tvoj link (ID: {u_id}) ne deluje pravilno. "
            "Sistem ga je začasno <b>zamrznil</b>.\n\n"
            "Preveri link in ga dodaj ponovno z <code>/add_url</code>."
        )
        
        try:
            await send_message(context, chat_id=t_id, text=user_msg, parse_mode="HTML")
            await send_message(context, chat_id=ADMIN_ID, text=f"🚨 POKVARJEN LINK: {u_name} ({t_id})", parse_mode="HTML")
            db.update_url_fail_count(u_id) 
        except:
            pass

    novi_oglasi = manager.check_new_offers(filter_url_ids=pending_ids)
    
    if not novi_oglasi:
        print(f"{B_BLUE}[{get_time()}] INFO - Ni novih oglasov za te skene.{B_END}")
        return

    # On startup, mark as sent but don't send notifications
    if not send_notifications:
        for oglas in novi_oglasi:
            db.add_sent_ad(oglas['target_user_id'], oglas['content_id'])
        print(f"{B_YELLOW}[{get_time()}] STARTUP - Silent check: {len(novi_oglasi)} ads indexed and marked for this user, notifications skipped.{B_END}")
        return

    print(f"{B_YELLOW}[{get_time()}] SEND - Pošiljam {len(novi_oglasi)} novih obvestil...{B_END}")

    for oglas in novi_oglasi:
        chat_id = oglas['target_user_id']
        tekst = manager.format_telegram_message(oglas)
        # Try both slika_url (Avtonet) and image_url (Bolha)
        slika = oglas.get("slika_url") or oglas.get("image_url")

        try:
            # --- VARNO POŠILJANJE S FALLBACKOM ---
            success = False
            if slika and slika.startswith('http'):
                try:
                    await context.bot.send_photo(
                        chat_id=chat_id, 
                        photo=slika, 
                        caption=tekst, 
                        parse_mode="HTML"
                    )
                    success = True
                except Exception as img_err:
                    print(f"⚠️ Napaka pri sliki (ID:{oglas['content_id']}): {img_err}. Poskušam samo tekst...")
            
            # Če slike ni ali pa je pošiljanje slike spodletelo
            if not success:
                await send_message(
                    context,
                    chat_id=chat_id, 
                    text=tekst, 
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )
            
            db.add_sent_ad(chat_id, oglas['content_id'])
            await asyncio.sleep(0.5) 
            
        except Exception as e:
            print(f"[{get_time()}] ❌ Kritična napaka pri pošiljanju uporabniku {chat_id}: {e}")

    print(f"{B_GREEN}[{get_time()}] --- [ CIKEL KONČAN: Uspešno poslano ] ---{B_END}")


async def daily_maintenance(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    print(f"\n{B_YELLOW}--- [ DNEVNO VZDRŽEVANJE BAZE ] ---{B_END}")
    db = Database(os.getenv("DB_PATH"))
    db.cleanup_sent_ads(days=14)
    print(f"{B_GREEN}--- [ VZDRŽEVANJE KONČANO ] ---{B_END}")


async def check_subscription_expirations(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    db = Database(DB_PATH)
    expiring_users = db.get_users_for_expiry_reminder()
    
    for user in expiring_users:
        t_id = user['telegram_id']
        pkg = user['package_type']
        end_date = user['subscription_end']
        
        msg = (
            "⚠️ **OPOZORILO O POTEKU NAROČNINE**\n\n"
            f"Tvoj paket <b>{pkg}</b> poteče čez manj kot 24 ur!\n"
            f"📅 Veljavnost do: <code>{end_date}</code>\n\n"
            "Če želiš neprekinjeno prejemanje oglasov, prosim pravočasno podaljšaj naročnino.\n"
            "Preveri ponudbo z ukazom: /packages"
        )
        
        try:
            await send_message(context, chat_id=t_id, text=msg, parse_mode="HTML")
            db.set_expiry_reminder_sent(t_id) # Označi v bazi, da ne pošljemo še enkrat
            print(f"[SYSTEM] Poslano opozorilo o poteku uporabniku {t_id}")
        except Exception as e:
            print(f"Napaka pri pošiljanju opomina uporabniku {t_id}: {e}")

# V main.py posodobi tole funkcijo:

async def check_subscription_expirations(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    db = Database(DB_PATH)
    now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # --- 1. DEL: OPOMNIKI (24 ur prej) ---
    expiring_soon = db.get_users_for_expiry_reminder()
    for user in expiring_soon:
        t_id = user['telegram_id']
        msg = (
            "⚠️ <b>OPOZORILO O POTEKU NAROČNINE</b>\n\n"
            f"Tvoj paket <b>{user['subscription_type']}</b> poteče čez manj kot 24 ur!\n"
            f"📅 Veljavnost do: <code>{user['subscription_end']}</code>\n\n"
            "Če želiš neprekinjeno prejemanje oglasov, prosim pravočasno podaljšaj naročnino.\n"
            "Preveri ponudbo z ukazom: /packages"
        )
        try:
            await send_message(context, chat_id=t_id, text=msg, parse_mode="HTML")
            db.set_expiry_reminder_sent(t_id)
        except: pass

    # --- 2. DEL: DEJANSKI POTEK (Final Goodbye) ---
    expired_ids = db.get_newly_expired_users()
    for t_id in expired_ids:
        msg = (
            "🚫 <b>NAROČNINA JE POTEKLA</b>\n\n"
            "Tvoja naročnina je pravkar potekla. Tvoji URL-ji so varno shranjeni v bazi, "
            "vendar je <b>skeniranje novih oglasov ustavljeno</b>.\n\n"
            "Za ponovni zagon in prejem novih obvestil klikni /packages in kontaktiraj admina."
        )
        try:
            await send_message(context, chat_id=t_id, text=msg, parse_mode="HTML")
            db.deactivate_user_after_expiry(t_id)
            print(f"[SYSTEM] Uporabnik {t_id} je bil deaktiviran (potek naročnine).")
        except Exception as e:
            print(f"Napaka pri deaktivaciji uporabnika {t_id}: {e}")



def main():
    # Iniciacija baze
    db = Database(DB_PATH)
    db.init_db()

    # Nastavitev bota
    # Uporabimo defaults, da ne pišemo parse_mode v vsak klic
    application = telegram.ext.Application.builder().token(TOKEN).post_init(post_init).build()

    # --- REGISTRACIJA HANDLERJEV ---
    
    application.add_handler(telegram.ext.CommandHandler("start", start_command))
    application.add_handler(telegram.ext.CommandHandler("add_url", add_url_command))
    application.add_handler(telegram.ext.CommandHandler("list", list_command))
    application.add_handler(telegram.ext.CommandHandler("remove_url", remove_url_command))
    application.add_handler(telegram.ext.CommandHandler("info", info_command))
    application.add_handler(telegram.ext.CommandHandler("info", info_command))

    application.add_handler(telegram.ext.CommandHandler("help", help_command))
    application.add_handler(telegram.ext.CommandHandler("packages", packages_command))

    application.add_handler(CallbackQueryHandler(button_callback_handler))

    # Adming commands
        # Primer: /activate 12345678 paid 30  ALI  /activate 12345678 trial 7
    application.add_handler(telegram.ext.CommandHandler("activate", activate_user))
    application.add_handler(telegram.ext.CommandHandler("deactivate", deactivate_user))
    application.add_handler(telegram.ext.CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(telegram.ext.CommandHandler("admin", admin_help_command))
    application.add_handler(telegram.ext.CommandHandler("broadcast", broadcast_command))
    application.add_handler(telegram.ext.CommandHandler("users", list_users_admin))
    application.add_handler(telegram.ext.CommandHandler("health", health_command))
    application.add_handler(telegram.ext.CommandHandler("check_user", check_user_command))
    application.add_handler(telegram.ext.CommandHandler("proxy_stats", proxy_stats_command))
    application.add_handler(telegram.ext.CommandHandler("admin_overview", admin_overview_command))
    application.add_handler(telegram.ext.CommandHandler("errors", admin_errors_command))

    application.add_handler(telegram.ext.CommandHandler("send", send_dm_command))
    application.add_handler(telegram.ext.CommandHandler("add_url_user", add_url_user_command))

    application.add_handler(telegram.ext.CommandHandler("server", server_status_command))
    application.add_handler(telegram.ext.CommandHandler("logs", admin_logs_command))

    # --- NASTAVITEV PERIODIČNEGA OPRAVILA ---
    # Preverjaj vsakih 120 sekund (2 minut)
    # First run after 10 sec with send_notifications=False (startup silent check)
    # Then repeat every 120 sec with default send_notifications=True
    
    async def first_check(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
        """Startup silent check - populate DB without spamming users."""
        await check_for_new_ads(context, send_notifications=False)
        # Schedule regular checks after this
        application.job_queue.run_repeating(check_for_new_ads, interval=120)
    
    application.job_queue.run_once(first_check, when=10)

    # Master crawler (MarketData-only cache warmer)
    if ENABLE_MASTER_CRAWLER:
        async def master_job(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
            await asyncio.to_thread(run_master_crawler_once)

        application.job_queue.run_repeating(master_job, interval=MASTER_CRAWL_INTERVAL, first=15)

    # Čiščenje baze enkrat na dan (npr. vsakih 86400 sekund)
    # Nastavimo čas, ko običajno ni veliko novih oglasov
    # Nastavimo čas na 03:00 zjutraj
    maintenance_time = datetime.time(hour=3, minute=0, second=0, tzinfo=pytz.timezone('Europe/Ljubljana'))
    # Registracija dnevnega opravila
    application.job_queue.run_daily(daily_maintenance, time=maintenance_time)

    # Preverja in obvesti Uporabnika če se njegov paket nasledni dan zaključi
    application.job_queue.run_repeating(check_subscription_expirations, interval=3600, first=60)

    print("MarketPulse Bot je zagnan in čaka na nove oglase...")
    
    # Zaženi bota
    application.run_polling()

if __name__ == "__main__":
    main()

# https://www.nepremicnine.net/oglasi-prodaja/ljubljana-mesto/stanovanje/cena-do-1000000-eur/?s=16
#! Dodati je treba da je vedno najnovejši najprej



# POPRAVI:
# Jan Jurhar, [28. 01. 2026 22:09]
# /add_url https://www.nepremicnine.net/oglasi-prodaja/ljubljana-mesto/stanovanje/cena-do-10000000-eur/?s=16

# MarketPulse, [28. 01. 2026 22:09]
# ✅ Najdeno 1 nepremičnin...

# MarketPulse, [28. 01. 2026 22:09]
# ✅ Iskanje uspešno dodano!

# Sistem si je zapomnil trenutno ponudbo. Obvestim te takoj, ko se pojavi kakšen nov oglas! 🚀

# Jan Jurhar, [28. 01. 2026 22:09]
# /list

# MarketPulse, [28. 01. 2026 22:09]
# 📋 TVOJA ISKANJA
# ━━━━━━━━━━━━━━━━━━

# ✅ ID: 91 - Odpri iskanje na Bolha.com (https://www.bolha.com/racunalnistvo)
# ──────────────────
# ✅ ID: 92 - Odpri iskanje na Avto.net (https://www.avto.net/Ads/results.asp?cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&ccmMin=0&ccmMax=99999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=100000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=101000000&EQ9=100000002&EQ10=100000000&KAT=1060000000&kategorija=61000&zaloga=10&presort=3&tipsort=DESC&subSORT=3&subTIPSORT=DESC&stran=1)
# ──────────────────
# ✅ ID: 93 - Odpri iskanje na Avto.net (https://www.avto.net/Ads/results.asp?znamka=VW&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=10000000&KAT=1010000000&akcija=0&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=3&tipsort=DESC&subSORT=3&subTIPSORT=DESC&stran=1)
# ──────────────────
# ✅ ID: 94 - Odpri iskanje na Avto.net (https://www.avto.net/Ads/results.asp?znamka=BMW&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=10000000&KAT=1010000000&akcija=0&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=3&tipsort=DESC&subSORT=3&subTIPSORT=DESC&stran=1)
# ──────────────────
# ✅ ID: 95 - Odpri iskanje na Avto.net (https://www.avto.net/Ads/results.asp?znamka=Audi&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=10000000&KAT=1010000000&akcija=0&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=3&tipsort=DESC&subSORT=3&subTIPSORT=DESC&stran=1)
# ──────────────────
# ✅ ID: 96 - Odpri iskanje na Avto.net (https://www.avto.net/Ads/results.asp?znamka=MercedesBenz&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=10000000&KAT=1010000000&akcija=0&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=3&tipsort=DESC&subSORT=3&subTIPSORT=DESC&stran=1)
# ──────────────────
# ✅ ID: 97 - Odpri iskanje na Avto.net (https://www.nepremicnine.net/oglasi-prodaja/ljubljana-mesto/stanovanje/cena-do-10000000-eur/)
# ──────────────────

# 📊 Zasedenost: 7 / 15 mest
# 📦 Paket: ULTRA (🟢 Aktiven)


# 🗑️ ODSTRANITEV ISKANJA:
# Za izbris uporabi ukaz /remove_url 91

#! Problem je da ne piše Neprimicnine.net 





