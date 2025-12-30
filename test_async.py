import asyncio
import time
from database import Database
from scraper import Scraper
import config

# --- KONFIGURACIJA TESTA ---
config.USE_AI = True
TEST_DB_NAME = "test_async_v4.db"

async def main():
    # 1. Iniciacija
    db = Database(TEST_DB_NAME)
    db.init_db()
    
    # 2. Registracija dveh testnih uporabnikov
    db.register_user(123, "Jan_Tester", "jan_vibe")
    db.update_user_subscription(123, "ULTRA", 15, 2, 30)
    
    db.register_user(456, "Nejc_Tester", "nejc_vibe")
    db.update_user_subscription(456, "BASIC", 3, 15, 30)

    # 3. Dodajanje linkov
    # Uporabimo različne znamke, da vidimo, če se skeni prepletajo
    url_vw = "https://www.avto.net/Ads/results.asp?znamka=VW&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran="
    url_audi = "https://www.avto.net/Ads/results.asp?znamka=Audi&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran="
    url_bmw = "https://www.avto.net/Ads/results.asp?znamka=BMW&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran="


        
    db.add_search_url(123, url_vw)
    db.add_search_url(123, url_audi)
    db.add_search_url(456, url_bmw)

    scraper = Scraper(db)

    print("\n" + "="*50)
    print("🚀 START: ASYNC V4 TEST (Semaphore: 3)")
    print("="*50)
    
    # Pridobimo nalogr (tukaj bo bot videl is_first_scan = True)
    pending = db.get_pending_urls()
    
    start_time = time.time()
    
    # ZAGON ASINHRONEGA SKENERJA
    await scraper.run(pending)
    
    duration = time.time() - start_time
    print("\n" + "="*50)
    print(f"🏁 TEST KONČAN v {duration:.2f} sekundah.")
    print("="*50)
    
    # Preverimo, če je arhiv napolnjen (Silent Sync bi moral ročno napolniti MarketData)
    count = db.get_connection().execute("SELECT COUNT(*) FROM MarketData").fetchone()[0]
    print(f"📈 Oglasov v arhivu: {count}")

if __name__ == "__main__":
    asyncio.run(main())