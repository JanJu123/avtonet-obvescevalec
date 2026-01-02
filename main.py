import asyncio
import telegram
import telegram.ext
from database import Database
from scraper import Scraper
from data_manager import DataManager
from telegram.ext import CallbackQueryHandler
from master_crawler import run_master_crawler_once

from telegram_bot import start_command, list_command, add_url_command, remove_url_command, info_command, activate_user, \
    deactivate_user, admin_stats_command, admin_help_command, broadcast_command, list_users_admin, admin_logs_command, \
    health_command, check_user_command, proxy_stats_command, packages_command, help_command, post_init, server_status_command, \
    admin_overview_command, send_dm_command, add_url_user_command, button_callback_handler, admin_errors_command

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
)

async def check_for_new_ads(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    def get_time():
        return datetime.datetime.now().strftime('%H:%M:%S')

    print(f"\n{B_CYAN}--- [ PAMETNI CIKEL PREVERJANJA: {get_time()} ] ---{B_END}")
    
    db = Database(DB_PATH)
    pending_urls = db.get_pending_urls()
    
    if not pending_urls:
        print(f"{B_BLUE}[{get_time()}] 💤 Mirovanje: Noben URL še ni na vrsti.{B_END}")
        return

    pending_ids = [u['url_id'] for u in pending_urls]
    print(f"{B_GREEN}[{get_time()}] 🚀 Skeniram: {len(pending_ids)} URL-jev na vrsti.{B_END}")

    scraper = Scraper(DataBase=db)
    manager = DataManager(db)

    await asyncio.to_thread(scraper.run, pending_urls) 
    
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
            await context.bot.send_message(chat_id=t_id, text=user_msg, parse_mode="HTML")
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 POKVARJEN LINK: {u_name} ({t_id})", parse_mode="HTML")
            db.update_url_fail_count(u_id) 
        except:
            pass

    novi_oglasi = manager.check_new_offers(filter_url_ids=pending_ids)
    
    if not novi_oglasi:
        print(f"{B_BLUE}[{get_time()}] ℹ️ Ni novih oglasov za te skene.{B_END}")
        return

    print(f"{B_YELLOW}[{get_time()}] ✉️ Pošiljam {len(novi_oglasi)} novih obvestil...{B_END}")

    for oglas in novi_oglasi:
        chat_id = oglas['target_user_id']
        tekst = manager.format_telegram_message(oglas)
        slika = oglas.get("slika_url")

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
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=tekst, 
                    parse_mode="HTML", 
                    disable_web_page_preview=False
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
            await context.bot.send_message(chat_id=t_id, text=msg, parse_mode="HTML")
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
            await context.bot.send_message(chat_id=t_id, text=msg, parse_mode="HTML")
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
            await context.bot.send_message(chat_id=t_id, text=msg, parse_mode="HTML")
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
    # Preverjaj vsakih 300 sekund (5 minut), začni čez 10 sekund
    application.job_queue.run_repeating(check_for_new_ads, interval=120, first=10)

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

    print("AvtoNet Tracker Bot je zagnan in čaka na nove oglase...")
    
    # Zaženi bota
    application.run_polling()

if __name__ == "__main__":
    main()