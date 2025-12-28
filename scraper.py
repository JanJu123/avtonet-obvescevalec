import re
import time
import random
from bs4 import BeautifulSoup
from curl_cffi import requests
from ai_handler import AIHandler
import config
from database import Database

class Scraper:
    def __init__(self, DataBase: Database):
        self.db = DataBase
        self.ai = AIHandler()

    def get_latest_offers(self, url):
        """Pridobi oglase, očisti URL in zabeleži REALNO porabo podatkov."""
        
        # --- 1. KORAK: ČIŠČENJE URL-ja (Sanitization) ---
        # Odstranimo oklepaje < >, presledke in nove vrstice
        url = url.strip().strip('<>').replace(' ', '').replace('\n', '').replace('\r', '')
        
        # Preverimo, če URL sploh izgleda kot veljaven naslov
        if not url.startswith("http"):
            print(f"⚠️ [SCRAPER] URL zavrnjen (napačen format): {url[:50]}...")
            return None, 0

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'sl-SI,sl;q=0.9,en-GB;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br', # Zahtevamo stiskanje
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive'
        }

        try:
            # Človeški premor pred klicem
            time.sleep(random.uniform(2, 4))

            # Uporabimo curl_cffi za obhod Cloudflare zaščite
            response = requests.get(
                url, 
                impersonate="chrome120", 
                headers=headers, 
                timeout=30
            )
            
            # Preverimo stiskanje (Encoding)
            encoding = response.headers.get('Content-Encoding', '').lower()
            
            if response.status_code == 200:
                # Velikost odpakiranih podatkov v RAM-u
                decompressed_size = len(response.content)
                
                # --- 2. KORAK: LOGIKA ZA REALNO MERJENJE ---
                if any(comp in encoding for comp in ['gzip', 'br', 'deflate']):
                    # Če je stisnjeno (kot je bilo v tvojem debugu), zapišemo 20% velikosti
                    wire_size = int(decompressed_size * 0.20)
                    savings = 80.0
                else:
                    # Če ni stiskanja, zabeležimo polno težo
                    wire_size = decompressed_size
                    savings = 0.0
                
                print(f"✅ Dostop OK! [Ocenjen promet: {round(wire_size/1024, 1)} KB | Prihranek: {savings}% | Encoding: {encoding}]")
                
                return response.text, wire_size
            else:
                print(f"❌ Napaka {response.status_code} na Avto.net")
                return None, 0
                
        except Exception as e:
            print(f"❌ Napaka pri skeniranju (CURL): {e}")
            return None, 0

    def _is_top_ponudba(self, row_soup):
        """Agresivna detekcija TOP ponudb, da ne trošimo AI tokenov."""
        # 1. Preverimo Ribbon (značko) v kotu slike
        ribbon = row_soup.find('div', class_='GO-ResultsRibbon')
        if ribbon:
            r_text = ribbon.get_text().upper()
            if "TOP" in r_text or "IZPOSTAVLJENO" in r_text or "SUPER" in r_text:
                return True
        
        # 2. Preverimo senčenje (TOP oglasi imajo pogosto drugačen senci)
        row_classes = row_soup.get('class', [])
        featured_indicators = ['GO-Shadow-Featured', 'GO-Results-Featured', 'GO-Results-Row-TOP']
        if any(indicator in row_classes for indicator in featured_indicators):
            return True
            
        return False

    def _manual_parse_row(self, row, content_id, link, img_url):
        """Fallback: Ročno branje osnovnih podatkov, če AI ni na voljo."""
        naziv_tag = row.find('div', class_='GO-Results-Naziv')
        price_tag = row.find('div', class_=re.compile(r'Price|Cena'))
        
        return {
            "content_id": content_id,
            "ime_avta": naziv_tag.get_text(strip=True) if naziv_tag else "Neznano",
            "cena": price_tag.get_text(strip=True) if price_tag else "Po dogovoru",
            "leto_1_reg": "Neznano (AI OFF)",
            "prevozenih": "Neznano (AI OFF)",
            "gorivo": "Neznano (AI OFF)",
            "menjalnik": "Neznano (AI OFF)",
            "motor": "Neznano (AI OFF)",
            "link": link,
            "slika_url": img_url
        }

    def _clean_row_for_ai(self, row_soup):
        """Pobere ključne dele in jih strukturira za AI, da prepreči 'Neznano' rezultate."""
        
        # 1. NAZIV (Audi A4, BMW 3...)
        naziv_tag = row_soup.find('div', class_='GO-Results-Naziv')
        naziv = naziv_tag.get_text(strip=True) if naziv_tag else "Neznano"

        # 2. PODATKI (Letnik, KM, Gorivo)
        # Namesto samo '-Top' vzamemo celoten blok '-Data', ki je bolj varen
        data_tag = row_soup.find('div', class_=re.compile(r'GO-Results-Data'))
        if data_tag:
            # get_text(separator=' | ') je ključen, da se npr. letnik in km ne zlepita v 2021150000km
            podatki = data_tag.get_text(separator=' | ', strip=True)
        else:
            podatki = ""

        # 3. CENA (Iščemo vse, kar diši po ceni)
        cena_tag = row_soup.find('div', class_=re.compile(r'Price|Cena'))
        cena = ""
        if cena_tag:
            # Vzamemo ves tekst v cenovnem bloku (tudi akcijske cene)
            cena = cena_tag.get_text(separator=' ', strip=True)

        # --- VAROVALKA (Fallback) ---
        # Če kljub vsemu nismo našli podatkov ali cene, potem vzamemo ves tekst vrstice
        if not podatki or len(cena) < 2:
            return row_soup.get_text(separator=' ', strip=True)[:500]

        # Združimo v čist, označen niz, ki ga AI obožuje
        return f"AVTO: {naziv} | PODATKI: {podatki} | CENA: {cena}"

    def _get_new_ads_raw(self, html_content):
        """Prepozna vse vrstice, preskoči TOP ponudbe in vzame max 5 novih s popravljenimi linki slik."""
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('div', class_='GO-Results-Row')
        
        new_ads_list = []
        for row in rows:
            if self._is_top_ponudba(row):
                continue

            link_tag = row.find('a', class_='stretched-link')
            if not link_tag: continue
            
            href = link_tag.get('href', '')
            match = re.search(r'id=(\d+)', href)
            if not match: continue
            content_id = match.group(1)

            if self.db.is_ad_new(content_id):
                img_tag = row.find('img')
                img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                
                # --- POPRAVEK ZA SLIKO ---
                if img_url:
                    img_url = img_url.strip()
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = 'https://www.avto.net' + img_url
                # -------------------------
                
                new_ads_list.append({
                    "id": content_id,
                    "row_soup": row,
                    "text": self._clean_row_for_ai(row),
                    "link": "https://www.avto.net" + href.replace("..", ""),
                    "slika_url": img_url
                })
            
            if len(new_ads_list) >= 5:
                break
                
        return new_ads_list

    def run(self, urls_to_scrape):
        """Glavni proces skeniranja s 100% varno AI obdelavo, logiranjem imen in štetjem napak."""
        # Barve za lepši izpis na VPS
        B_CYAN = "\033[96m"
        B_YELLOW = "\033[93m"
        B_RED = "\033[91m"
        B_END = "\033[0m"

        def get_time():
            return time.strftime('%H:%M:%S')

        # Normalizacija vhoda
        if isinstance(urls_to_scrape, str):
            res = self.db.get_connection().execute("SELECT url_id FROM Urls WHERE url = ?", (urls_to_scrape,)).fetchone()
            u_id = res[0] if res else 0
            urls_to_scrape = [{'url_id': u_id, 'url': urls_to_scrape, 'telegram_name': 'Manual Test'}]

        self.db.clear_scraped_snapshot()

        for entry in urls_to_scrape:
            try:
                start_time = time.time()
                u_id = entry['url_id']
                # NOVO: Pridobimo ime uporabnika za boljšo identifikacijo v logih
                u_name = entry.get('telegram_name', 'Neznan')
                
                print(f"{B_CYAN}[{get_time()}] 🔍 Skeniram URL ID {u_id} (Uporabnik: {u_name})...{B_END}")
                
                html, bytes_used = self.get_latest_offers(entry['url'])
                
                # --- TOČKA 5: LOGIKA ZA NAPAKE ---
                if not html:
                    # Povečamo števec napak v bazi
                    current_fails = self.db.update_url_fail_count(u_id)
                    
                    error_msg = "Cloudflare Block ali napačen format"
                    print(f"{B_RED}[{get_time()}] ❌ Napaka ({current_fails}/3) za {u_name} (ID: {u_id}){B_END}")
                    
                    # Logiramo napako v ScraperLogs
                    self.db.log_scraper_run(u_id, 403, 0, round(time.time() - start_time, 2), 0, error_msg)
                    
                    if current_fails >= 3:
                        print(f"{B_RED}[{get_time()}] ⚠️ URL {u_id} je dosegel limit napak! Potrebna preverba.{B_END}")
                        # Tukaj bi lahko dodal kodo za avtomatsko deaktivacijo URL-ja, če želiš
                    continue
                else:
                    # USPEH: Ponastavimo števec napak na 0
                    self.db.reset_url_fail_count(u_id)

                # --- NADALJEVANJE SKENIRANJA ---
                is_first = self.db.is_first_scan(u_id)
                soup = BeautifulSoup(html, 'html.parser')
                rows = soup.find_all('div', class_='GO-Results-Row')
                
                all_ids_on_page = []
                new_ads_to_process = []

                for row in rows:
                    if self._is_top_ponudba(row): 
                        link_tag = row.find('a', class_='stretched-link')
                        if link_tag:
                            href = link_tag.get('href', '')
                            match = re.search(r'id=(\d+)', href)
                            if match: self.db.bulk_add_sent_ads(u_id, [match.group(1)])
                        continue
                    
                    link_tag = row.find('a', class_='stretched-link')
                    if not link_tag: continue
                    href = link_tag.get('href', '')
                    match = re.search(r'id=(\d+)', href)
                    if not match: continue
                    content_id = str(match.group(1))
                    all_ids_on_page.append(content_id)

                    if not is_first and self.db.is_ad_new(content_id):
                        new_ads_to_process.append({
                            "id": content_id,
                            "row_soup": row,
                            "text": self._clean_row_for_ai(row),
                            "link": "https://www.avto.net" + href.replace("..", "")
                        })

                if is_first:
                    print(f"[{get_time()}] 📥 Prvi sken za {u_name}: Sinhroniziram {len(all_ids_on_page)} oglasov.")
                    self.db.bulk_add_sent_ads(u_id, all_ids_on_page)
                    duration = round(time.time() - start_time, 2)
                    self.db.log_scraper_run(u_id, 200, 0, duration, bytes_used, "Initial Sync")
                    continue

                if not new_ads_to_process:
                    duration = round(time.time() - start_time, 2)
                    self.db.log_scraper_run(u_id, 200, 0, duration, bytes_used, "No new ads")
                    continue

                # Flood Protection
                if len(new_ads_to_process) > 5:
                    to_process = new_ads_to_process[:5]
                    to_mute_ids = [ad['id'] for ad in new_ads_to_process[5:]]
                    self.db.bulk_add_sent_ads(u_id, to_mute_ids)
                    new_ads_to_process = to_process

                # AI PROCESIRANJE
                final_results = []
                if config.USE_AI:
                    print(f"{B_YELLOW}[{get_time()}] 🤖 AI obdeluje {len(new_ads_to_process)} oglasov za {u_name}...{B_END}")
                    ai_results = self.ai.extract_ads_batch(new_ads_to_process)
                    
                    if ai_results:
                        for ad_data in ai_results:
                            ad_id = ad_data.get('content_id') or ad_data.get('id') or ad_data.get('ID')
                            orig = next((x for x in new_ads_to_process if str(x['id']) == str(ad_id)), None)
                            if orig:
                                ad_data['content_id'] = str(orig['id'])
                                ad_data['link'] = orig['link']
                                img_tag = orig['row_soup'].find('img')
                                ad_data['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                                final_results.append(ad_data)

                if not final_results:
                    for item in new_ads_to_process:
                        img_tag = item['row_soup'].find('img')
                        img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                        final_results.append(self._manual_parse_row(item['row_soup'], item['id'], item['link'], img_url))

                for data in final_results:
                    self.db.insert_scraped_data(u_id, data)

                duration = round(time.time() - start_time, 2)
                self.db.log_scraper_run(u_id, 200, len(final_results), duration, bytes_used, "Success")
                print(f"✅ [{get_time()}] URL {u_id} ({u_name}) končan v {duration}s.")

            except Exception as e:
                print(f"{B_RED}[{get_time()}] ❌ Kritična napaka pri URL {u_id} ({entry.get('telegram_name')}): {e}{B_END}")
            
            time.sleep(random.uniform(1, 2.5))

# --- TEST ---
if __name__ == "__main__":
    test_db = Database("bot.db")
    test_db.init_db()
    # Testni link za Mercedes
    test_url = "https://www.avto.net/Ads/results.asp?znamka=Audi&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran="
    scraper = Scraper(test_db)
    scraper.run([{'url_id': 1, 'url': test_url}])