import re
import time
import random
from bs4 import BeautifulSoup
from curl_cffi import requests
from ai_handler import AIHandler
import config
from database import Database
from scraper.base_scraper import get_latest_offers

class Scraper:
    def __init__(self, DataBase: Database):
        self.db = DataBase
        self.ai = AIHandler()

    def get_latest_offers(self, url: str):
        """Pridobi oglase, očisti URL in vrne (HTML, bytes, status_code)."""
        # Delegate to base scraper function
        return get_latest_offers(url)
        

    def _is_top_ponudba(self, row_soup):
        """Agresivna detekcija TOP ponudb, da ne trošimo AI tokenov."""
        
        # PRIMARY DETECTION: Check for GO-Results-Top-Photo/Price/Data layout
        # Top ponudbe have special layout with GO-Results-Top-Photo, GO-Results-Top-Price, etc.
        top_layout_indicators = row_soup.find_all('div', class_=lambda x: x and any(
            cls.startswith('GO-Results-Top-') and cls not in ['GO-Results-Top', 'GO-Results-Data-Top']
            for cls in (x if isinstance(x, list) else [x])
        ))
        if len(top_layout_indicators) >= 3:  # Top ponudbe have many such divs
            return True
        
        # Check for specific top ponudbe layout classes
        if row_soup.find('div', class_=lambda x: x and 'GO-Results-Top-Photo' in (x if isinstance(x, list) else [x])):
            return True
        if row_soup.find('div', class_=lambda x: x and 'GO-Results-Top-Price' in (x if isinstance(x, list) else [x])):
            return True
        
        # SECONDARY: Check for explicit TOP/PREMIUM/SUPER ribbons (not NOVO)
        ribbon = row_soup.find('div', class_='GO-ResultsRibbon')
        if ribbon:
            r_text = ribbon.get_text().upper()
            # Only skip if ribbon says TOP, PREMIUM, SUPER (not NOVO)
            if any(keyword in r_text for keyword in ['TOP', 'IZPOSTAVLJENO', 'SUPER', 'PREMIUM', 'OGLAS']):
                return True
        
        # Other feature class checks
        row_classes = row_soup.get('class', [])
        featured_indicators = ['GO-Shadow-Featured', 'GO-Results-Featured', 'GO-Results-Row-TOP', 'Featured', 'Premium', 'Highlighted']
        if any(indicator in row_classes for indicator in featured_indicators):
            return True
        
        # Check for data attributes
        if row_soup.get('data-premium') or row_soup.get('data-featured') or row_soup.get('data-top'):
            return True
        
        # Check for special styling
        style = row_soup.get('style', '')
        if 'background' in style.lower() and any(color in style.lower() for color in ['yellow', 'gold', 'highlight']):
            return True
            
        return False

    def _manual_parse_row(self, row, content_id, link, img_url):
        """Fallback: Parse HTML + raw_snippet text to extract fields."""
        import re
        
        naziv_tag = row.find('div', class_='GO-Results-Naziv')
        price_tag = row.find('div', class_=re.compile(r'Price|Cena'))
        
        # Get text from row as fallback
        row_text = row.get_text(separator=' ', strip=True)
        
        # Try to extract from text using regex patterns
        cena = self._extract_price_from_text(row_text)
        leto = self._extract_year_from_text(row_text)
        km = self._extract_mileage_from_text(row_text)
        gorivo = self._extract_fuel_from_text(row_text)
        menjalnik = self._extract_transmission_from_text(row_text)
        motor = self._extract_engine_from_text(row_text)
        
        return {
            "content_id": content_id,
            "ime_avta": naziv_tag.get_text(strip=True) if naziv_tag else "Neznano",
            "cena": cena or (price_tag.get_text(strip=True) if price_tag else "Po dogovoru"),
            "leto_1_reg": leto or "Neznano",
            "prevozenih": km or "Neznano",
            "gorivo": gorivo or "Neznano",
            "menjalnik": menjalnik or "Neznano",
            "motor": motor or "Neznano",
            "link": link,
            "slika_url": img_url
        }
    
    def _extract_price_from_text(self, text):
        """Extract price from text like '12.490 €' or '12490EUR'"""
        match = re.search(r'(\d+[.,]\d+)\s*[€EUR]', text, re.IGNORECASE)
        return match.group(1) + " €" if match else None
    
    def _extract_year_from_text(self, text):
        """Extract year like '2021' or '2020'"""
        match = re.search(r'\b(19|20)\d{2}\b', text)
        return match.group(0) if match else None
    
    def _extract_mileage_from_text(self, text):
        """Extract mileage like '71000 km' or '71.000km'"""
        match = re.search(r'(\d+[.,]?\d*)\s*km', text, re.IGNORECASE)
        return match.group(0) if match else None
    
    def _extract_fuel_from_text(self, text):
        """Extract fuel type"""
        text_lower = text.lower()
        fuels = {
            'diesel': ['diesel'],
            'bencin': ['bencin', 'benzin', 'gasoline'],
            'hibrid': ['hibrid', 'hybrid'],
            'elektro': ['elektro', 'electric', 'ev'],
            'plin': ['plin', 'lpg', 'cng']
        }
        for fuel_type, keywords in fuels.items():
            if any(kw in text_lower for kw in keywords):
                return fuel_type
        return None
    
    def _extract_transmission_from_text(self, text):
        """Extract transmission type"""
        text_lower = text.lower()
        if 'avtomatski' in text_lower or 'automatic' in text_lower:
            return 'avtomatski'
        elif 'ročni' in text_lower or 'manual' in text_lower:
            return 'ročni'
        return None
    
    def _extract_engine_from_text(self, text):
        """Extract engine cc and power like '1968 ccm, 110 kW / 150 KM'"""
        match = re.search(r'(\d+)\s*ccm[^0-9]*(\d+)\s*kW\s*[/\\]\s*(\d+)\s*KM', text, re.IGNORECASE)
        if match:
            return f"{match.group(1)} ccm, {match.group(2)} kW / {match.group(3)} KM"
        return None

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
        """Glavni proces skeniranja z uporabo arhiva (Shared Brain) in AI batchinga."""
        # Barve za lepši izpis na VPS
        B_CYAN = "\033[96m"
        B_YELLOW = "\033[93m"
        B_RED = "\033[91m"
        B_GREEN = "\033[92m"
        B_END = "\033[0m"

        def get_time():
            return time.strftime('%H:%M:%S')

        # Normalizacija vhoda
        if isinstance(urls_to_scrape, str):
            res = self.db.get_connection().execute("SELECT url_id, url_bin FROM Urls WHERE url = ?", (urls_to_scrape,)).fetchone()
            u_id = res[0] if res else 0
            u_bin = res[1] if res else urls_to_scrape.encode('latin-1', 'ignore')
            urls_to_scrape = [{'url_id': u_id, 'url_bin': u_bin, 'url': urls_to_scrape, 'telegram_name': 'Manual Test'}]

        self.db.clear_scraped_snapshot()

        for entry in urls_to_scrape:
            try:
                start_time = time.time()
                u_id = entry['url_id']
                u_name = entry.get('telegram_name', 'Neznan')
                
                # Priprava binarnega URL-ja
                if 'url_bin' in entry and entry['url_bin']:
                    final_url = entry['url_bin'].decode('latin-1')
                else:
                    final_url = entry['url']

                print(f"{B_CYAN}[{get_time()}] AVTONET SCAN - URL ID {u_id} ({u_name})...{B_END}")
                
                html, bytes_used, status_code = self.get_latest_offers(final_url)
                
                if not html:
                    current_fails = self.db.update_url_fail_count(u_id)
                    actual_error = f"HTTP {status_code}" if status_code != 0 else "CURL Error"
                    print(f"{B_RED}[{get_time()}] ❌ {actual_error} ({current_fails}/3) za {u_name}{B_END}")
                    self.db.log_scraper_run(u_id, status_code, 0, round(time.time() - start_time, 2), 0, actual_error)
                    continue
                else:
                    self.db.reset_url_fail_count(u_id)

                is_first = self.db.is_first_scan(u_id)
                soup = BeautifulSoup(html, 'html.parser')
                rows = soup.find_all('div', class_='GO-Results-Row')
                
                all_ids_on_page = []
                ads_to_ai_batch = [] # Seznam tistih, ki jih mora AI dejansko obdelati
                final_results = []   # Končni podatki za vpis v ScrapedData (AI + Arhiv)

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

                    # Če je oglas nov za tega uporabnika...
                    if not is_first and self.db.is_ad_new(content_id):
                        
                        # --- NOVO: PREVERIMO ARHIV (MarketData) ---
                        # Če je nekdo drug ta avto že ulovil, ne trošimo AI-ja!
                        existing_ad = self.db.get_market_data_by_id(content_id)
                        
                        if existing_ad:
                            # Already in archive, reuse data (skip AI processing)
                            # Pripravimo sliko in link iz trenutnega row-a (da sta vedno sveža)
                            img_tag = row.find('img')
                            existing_ad['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                            existing_ad['link'] = "https://www.avto.net" + href.replace("..", "")
                            final_results.append(existing_ad)
                        else:
                            # Popolnoma nov oglas, ki gre v AI batch
                            ads_to_ai_batch.append({
                                "id": content_id,
                                "row_soup": row,
                                "text": self._clean_row_for_ai(row),
                                "link": "https://www.avto.net" + href.replace("..", ""),
                                "slika_url": None
                            })

                if is_first:
                    print(f"[{get_time()}] 📥 Prvi sken za {u_name}: Sinhroniziram {len(all_ids_on_page)} oglasov.")
                    self.db.bulk_add_sent_ads(u_id, all_ids_on_page)
                    self.db.log_scraper_run(u_id, 200, 0, round(time.time() - start_time, 2), bytes_used, "Initial Sync")
                    continue

                # --- AI PROCESIRANJE ---
                if ads_to_ai_batch:
                    # Flood Protection (max 5)
                    if len(ads_to_ai_batch) > 5:
                        to_mute_ids = [ad['id'] for ad in ads_to_ai_batch[5:]]
                        self.db.bulk_add_sent_ads(u_id, to_mute_ids)
                        ads_to_ai_batch = ads_to_ai_batch[:5]

                    if config.USE_AI:
                        print(f"{B_YELLOW}[{get_time()}] 🤖 AI - Sending {len(ads_to_ai_batch)} ads for processing...{B_END}")
                        ai_results = self.ai.extract_ads_batch(ads_to_ai_batch)
                        
                        if ai_results:
                            for ad_data in ai_results:
                                ad_id = str(ad_data.get('content_id') or ad_data.get('id') or ad_data.get('ID'))
                                # Poiščemo pripadajoč originalen snippet
                                orig = next((x for x in ads_to_ai_batch if str(x['id']) == ad_id), None)
                                
                                if orig:
                                    # Pripravimo končne podatke
                                    ad_data['content_id'] = ad_id
                                    ad_data['link'] = orig['link']
                                    img_tag = orig['row_soup'].find('img')
                                    ad_data['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                                    
                                    # DODAMO V REZULTATE ZA UPORABNIKA
                                    final_results.append(ad_data)
                                    
                                    # Save to MarketData archive
                                    self.db.insert_market_data(ad_data, orig['text'])
                        else:
                            print(f"[{get_time()}] ⚠️ AI odpovedal, preklop na manual.")

                # --- MANUAL FALLBACK (za tiste, ki še niso v final_results) ---
                # Preverimo, če nam v ads_to_ai_batch manjka kakšen oglas (ker ga AI ni vrnil ali je USE_AI=False)
                for item in ads_to_ai_batch:
                    if not any(str(res.get('content_id')) == str(item['id']) for res in final_results):
                        img_tag = item['row_soup'].find('img')
                        img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                        manual_data = self._manual_parse_row(item['row_soup'], item['id'], item['link'], img_url)
                        
                        final_results.append(manual_data)
                        # Save to MarketData archive
                        self.db.insert_market_data(manual_data, item['text'])

                # --- VPIS V BAZO ZA TELEGRAM OBVESTILA ---
                for data in final_results:
                    self.db.insert_scraped_data(u_id, data)

                # Logiranje uspeha
                duration = round(time.time() - start_time, 2)
                self.db.log_scraper_run(u_id, 200, len(final_results), duration, bytes_used, "Success")
                if final_results:
                    print(f"   [DONE] URL {u_id} - {len(final_results)} oglasov v {duration}s")

            except Exception as e:
                print(f"{B_RED}[{get_time()}] ❌ Kritična napaka pri URL {u_id}: {e}{B_END}")
            
            time.sleep(random.uniform(1.5, 3))

# --- TEST ---
if __name__ == "__main__":
    # 1. Priprava testne baze
    # Uporabimo ločeno datoteko, da ne pacamo prave baze
    test_db = Database("test_binary.db")
    test_db.init_db()

    # 2. Testni URL (vzamemo tvoj dolg Audi link)
    raw_url = "https://www.avto.net/Ads/results.asp?znamka=Audi&model=&modelID=&tip=katerikolitip&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=2008&letnikMax=2015&bencin=201&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=250000&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=100000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=101000000&EQ9=1000000020&EQ10=1000000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=3&tipsort=DESC&stran=1&subtip=0"
    # 3. Simulacija baze: URL spremenimo v surove bajte (latin-1)
    # To je ključni del nove tehnologije!
    url_bin = raw_url.encode('latin-1', 'ignore')

    # Pripravimo seznam, kot bi ga vrnil db.get_pending_urls()
    pending_test_list = [{
        'url_id': 999,
        'url_text': raw_url, # Za loge
        'url_bin': url_bin,  # Za dejansko delo
        'telegram_name': 'Jan TEST'
    }]

    # 4. Zagon scraperja
    print("\n" + "="*50)
    print("🚀 ZAČENJAM BINARNI HYBRID TEST...")
    print("="*50)
    
    scraper = Scraper(DataBase=test_db)
    
    # Zaženemo run metodo z našim testnim seznamom
    scraper.run(pending_test_list)

    print("\n" + "="*50)
    print("🏁 TEST ZAKLJUČEN. Preveri loge zgoraj!")
    print("="*50)