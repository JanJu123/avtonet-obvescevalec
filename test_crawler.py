import time
import os
import json
from database import Database
from scraper import Scraper
import config

config.USE_AI = True 
TEST_DB = "test_deep_crawl.db"

def print_boss(msg):
    print(f"\033[92m[BOSS TEST] {msg}\033[0m")

def main():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    db = Database(TEST_DB)
    db.init_db()
    scraper = Scraper(db)
    
    # Registracija
    db.register_user(8004323652, "Jan_Boss", "JanJu_123")
    db.update_user_subscription(8004323652, "ULTRA", 20, 2, 30)
    
    working_url = "https://www.avto.net/Ads/results.asp?znamka=Audi&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran="
    db.add_search_url(8004323652, working_url)

    # --- KROG 1: INITIAL SYNC ---
    print("\n" + "="*30 + " KROG 1: INITIAL SYNC (SILENT) " + "="*30)
    pending = db.get_pending_urls()
    scraper.run(pending)
    
    sync_count = db.get_connection().execute("SELECT COUNT(*) FROM SentAds").fetchone()[0]
    print_boss(f"Sinhroniziranih oglasov: {sync_count}. AI preskočen (pravilno).")

    # --- KROG 2: DEJANSKI AI TEST ---
    print("\n" + "="*30 + " KROG 2: AI BATCHING TEST " + "="*30)
    
    # 1. Vzamemo en ID iz baze in ga izbrišemo iz SentAds
    res = db.get_connection().execute("SELECT content_id FROM SentAds LIMIT 1").fetchone()
    if res:
        cid = res[0]
        db.get_connection().execute("DELETE FROM SentAds WHERE content_id = ?", (cid,))
        db.get_connection().commit()
        print_boss(f"Izbrisal ID {cid} iz SentAds. Zdaj je za bota 'nov'.")
    
    # 2. POMEMBNO: NE brišemo ScraperLogs! 
    # Namesto tega ročno pripravimo 'pending' listo, da "prevaramo" časovni interval.
    # Ker logi ostanejo, bo 'is_first_scan' vrnil FALSE in AI SE BO SPROŽIL.
    
    forced_pending = [{
        'url_id': 1, 
        'url': working_url, 
        'telegram_name': 'Jan_Boss'
    }]

    print_boss("Zagon prisilnega skeniranja. Zdaj se MORA sprožiti AI.")
    scraper.run(forced_pending)

    # --- KONČNA STATISTIKA ---
    print("\n" + "="*30 + " KONČNA STATISTIKA TESTA " + "="*30)
    market_count = db.get_connection().execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
    if market_count > 0:
        print_boss(f"✅ USPEH! AI je obdelal oglas in ga shranil v MarketData.")
        data = db.get_market_data_by_id(cid)
        print(json.dumps(data, indent=4, ensure_ascii=False))
    else:
        print("\033[91m❌ AI se še vedno ni sprožil. Nekaj je narobe v 'run' logiki.\033[0m")

if __name__ == "__main__":
    main()