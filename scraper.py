import re
import time
import random
import json
from bs4 import BeautifulSoup
from curl_cffi import requests
from ai_handler import AIHandler
import config
from database import Database

class Scraper:
    def __init__(self, DataBase: Database):
        self.db = DataBase
        self.ai = AIHandler()
        # Master URL za rudarjenje celotnega trga (vsa vozila, najnovejša zgoraj)
        self.master_url = "https://www.avto.net/Ads/results.asp?znamka=&model=&letnikMin=0&presort=3&tipsort=DESC&zaloga=10"

    def get_latest_offers(self, url: str):
        """Pridobi oglase, očisti URL in vrne (HTML, bytes, status_code)."""
        url = url.strip().strip('<>').replace(' ', '%20').replace('\n', '').replace('\r', '')
        
        if not url.startswith("http"):
            return None, 0, 0

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'sl-SI,sl;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive'
        }

        try:
            time.sleep(random.uniform(1, 2.5))
            response = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
            status_code = response.status_code
            encoding = response.headers.get('Content-Encoding', '').lower()
            
            if status_code == 200:
                decompressed_size = len(response.content)
                # Ocenimo promet na žici zaradi Gzipa
                wire_size = int(decompressed_size * 0.20) if any(c in encoding for c in ['gzip', 'br']) else decompressed_size
                print(f"Dostop OK! [Ocenjen promet: {round(wire_size/1024, 1)} KB | Encoding: {encoding}]")
                return response.text, wire_size, 200
            else:
                return None, 0, status_code
                
        except Exception as e:
            print(f"❌ Napaka pri skeniranju (CURL): {e}")
            return None, 0, 0

    def _is_top_ponudba(self, row_soup):
        """Identificira sponzorirane oglase."""
        ribbon = row_soup.find('div', class_='GO-ResultsRibbon')
        if ribbon and "TOP" in ribbon.get_text().upper(): return True
        if "GO-Shadow-Featured" in str(row_soup.get('class', [])): return True
        return False

    def _clean_row_for_ai(self, row_soup):
        """Pobere ključne dele in jih strukturira za AI."""
        naziv = row_soup.find('div', class_='GO-Results-Naziv')
        naziv_txt = naziv.get_text(strip=True) if naziv else "Neznano"
        data_tag = row_soup.find('div', class_=re.compile(r'GO-Results-Data'))
        podatki = data_tag.get_text(separator=' | ', strip=True) if data_tag else ""
        cena_tag = row_soup.find('div', class_=re.compile(r'Price|Cena'))
        cena = cena_tag.get_text(separator=' ', strip=True) if cena_tag else ""

        if not podatki or len(cena) < 2:
            return row_soup.get_text(separator=' ', strip=True)[:500]

        return f"AVTO: {naziv_txt} | PODATKI: {podatki} | CENA: {cena}"

    def _manual_parse_row(self, row, content_id, link, img_url):
        """Hitri ročni parser (zastonj), ki napolni arhiv, če AI odpove."""
        text = row.get_text(separator=" ", strip=True)
        # Regex za ceno in leto
        price_match = re.search(r'(\d+[\.\s]*\d*)\s*€', text)
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        
        return {
            "content_id": content_id,
            "ime_avta": row.find('div', class_='GO-Results-Naziv').get_text(strip=True) if row.find('div', class_='GO-Results-Naziv') else "Neznano",
            "cena": price_match.group(0) if price_match else "Po dogovoru",
            "leto_1_reg": year_match.group(0) if year_match else "Neznano",
            "prevozenih": "Neznano",
            "gorivo": "Neznano",
            "menjalnik": "Neznano",
            "motor": "Neznano",
            "link": link,
            "slika_url": img_url
        }

    def _get_ads_from_html(self, html_content, u_id, is_first_sync):
        """Pobere vse oglase s strani in popravi URL-je slik."""
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('div', class_='GO-Results-Row')
        
        ads_found = []
        all_new_on_page = True
        has_regular_ads = False

        for row in rows:
            if self._is_top_ponudba(row):
                # TOP ponudbo samo utišamo v bazi
                link_tag = row.find('a', class_='stretched-link')
                if link_tag:
                    match = re.search(r'id=(\d+)', link_tag['href'])
                    if match: self.db.bulk_add_sent_ads(u_id, [match.group(1)])
                continue
            
            has_regular_ads = True
            link_tag = row.find('a', class_='stretched-link')
            if not link_tag: continue
            cid = str(re.search(r'id=(\d+)', link_tag['href']).group(1))

            if not self.db.is_ad_new(u_id, cid):
                all_new_on_page = False
                continue

            # Obdelava slike
            img_tag = row.find('img')
            img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
            if img_url:
                if img_url.startswith('//'): img_url = 'https:' + img_url
                elif img_url.startswith('/'): img_url = 'https://www.avto.net' + img_url

            ads_found.append({
                "id": cid,
                "row_soup": row,
                "text": self._clean_row_for_ai(row),
                "link": "https://www.avto.net/Ads/details.asp?id=" + cid,
                "slika_url": img_url
            })

        return ads_found, all_new_on_page, has_regular_ads

    def run(self, urls_to_scrape):
        """Final Boss Scraper: Deep Mining + Shared Brain + Global AI Batching (Max 45 ads)."""
        B_CYAN, B_YELLOW, B_RED, B_GREEN, B_END = "\033[96m", "\033[93m", "\033[91m", "\033[92m", "\033[0m"
        def get_time(): return time.strftime('%H:%M:%S')

        # 1. Normalizacija vhoda (omogoča ročni test s stringom)
        if isinstance(urls_to_scrape, str):
            res = self.db.get_connection().execute("SELECT url_id, url_bin FROM Urls WHERE url = ?", (urls_to_scrape,)).fetchone()
            u_id = res[0] if res else 0
            u_bin = res[1] if res else urls_to_scrape.encode('latin-1', 'ignore')
            urls_to_scrape = [{'url_id': u_id, 'url_bin': u_bin, 'url': urls_to_scrape, 'telegram_name': 'Manual Test'}]

        self.db.clear_scraped_snapshot()
        
        global_new_ads = {}  # {content_id: item_data} - Unikatni oglasi za AI
        user_needs = {}      # {content_id: [url_id1, url_id2]} - Kdo rabi kateri oglas
        total_saved_by_cache = 0

        # --- 1. PRIPRAVA NALOG (Master Crawler se doda samo ENKRAT) ---
        all_tasks = []
        from config import MASTER_URLS
        if MASTER_URLS:
            all_tasks.append({
                'url': MASTER_URLS[0], 
                'url_id': 0, 
                'telegram_name': 'SYSTEM_MASTER'
            })
        all_tasks.extend(urls_to_scrape)

        print(f"\n{B_CYAN}[{get_time()}] 🌀 ZAČENJAM CIKEL GLOBALNEGA RUDARJENJA...{B_END}")

        # --- 2. FAZA: ZBIRANJE IN FILTRIRANJE ---
        for entry in all_tasks:
            try:
                start_time = time.time()
                u_id, u_name = entry['url_id'], entry.get('telegram_name', 'Neznan')
                
                # Priprava URL-ja (tekst ali binarno)
                if 'url_bin' in entry and entry['url_bin']:
                    base_url = entry['url_bin'].decode('latin-1')
                else:
                    base_url = entry['url']
                
                is_first_sync = self.db.is_first_scan(u_id)
                
                print(f"  {B_CYAN}🔍 Pregled: {u_name} (ID: {u_id}) {'[SYNC]' if is_first_sync else ''}{B_END}")

                # Globina: Master Crawler preišče 4 strani, uporabniki le 1.
                current_page, max_pages = 1, (4 if u_id == 0 else 1) 
                
                while current_page <= max_pages:
                    clean_base = base_url.split('&stran=')[0]
                    page_url = f"{clean_base}&stran={current_page}"
                    
                    html, bytes_used, status = self.get_latest_offers(page_url)
                    if not html: break
                    
                    if u_id != 0: self.db.reset_url_fail_count(u_id)

                    ads_on_page, all_new_on_page, has_regular = self._get_ads_from_html(html, u_id, is_first_sync)

                    for ad in ads_on_page:
                        cid = str(ad['id'])
                        
                        # A) Tiha sinhronizacija (Brez AI!)
                        if is_first_sync:
                            self.db.bulk_add_sent_ads(u_id, [cid])
                            if u_id == 0:
                                # Masterju napolnimo arhiv ročno (zastonj)
                                manual_data = self._manual_parse_row(ad['row_soup'], cid, ad['link'], ad['slika_url'])
                                self.db.insert_market_data(manual_data, ad['text'])
                            continue
                        
                        # B) Preverimo arhiv (Shared Brain / Cache)
                        existing = self.db.get_market_data_by_id(cid)
                        if existing:
                            total_saved_by_cache += 1
                            self.db.bulk_add_sent_ads(u_id, [cid])
                            if u_id != 0: 
                                existing['slika_url'] = ad['slika_url'] # Vedno osvežimo sliko
                                self.db.insert_scraped_data(u_id, existing)
                            continue

                        # C) Resnično nov oglas za celoten sistem
                        if cid not in global_new_ads:
                            global_new_ads[cid] = ad
                        
                        if u_id != 0:
                            if cid not in user_needs: user_needs[cid] = []
                            if u_id not in user_needs[cid]: user_needs[cid].append(u_id)

                    if not is_first_sync and not all_new_on_page: break 
                    current_page += 1
                    time.sleep(random.uniform(0.3, 0.7))

                if is_first_sync:
                    self.db.log_scraper_run(u_id, 200, 0, round(time.time() - start_time, 2), bytes_used, "Initial Sync")

            except Exception as e:
                print(f"  {B_RED}❌ Napaka pri URL {u_id}: {e}{B_END}")

        # --- 3. FAZA: GLOBALNA AI OBDELAVA Z LIMITOM ---
        all_new_list = list(global_new_ads.values())
        
        # VAROVALKA: Največ 45 oglasov na cikel (3 paketi po 15)
        if len(all_new_list) > 45:
            print(f"  {B_RED} Flood Protection: Najdenih {len(all_new_list)}, obdelujem le 45.{B_END}")
            all_new_list = all_new_list[:45]

        if all_new_list and config.USE_AI:
            print(f"  {B_YELLOW}  AI: Obdelujem {len(all_new_list)} oglasov. ({total_saved_by_cache} iz arhiva){B_END}")
            
            # Razbijemo na pakete po 15
            for i in range(0, len(all_new_list), 15):
                batch = all_new_list[i:i+15]
                print(f"    Batch {i//15 + 1} ({len(batch)} oglasov)...")
                
                ai_results = self.ai.extract_ads_batch(batch)
                
                if ai_results:
                    for res in ai_results:
                        # Varno preverimo ID
                        cid = str(res.get('content_id') or res.get('id'))
                        orig = global_new_ads.get(cid)
                        if not orig: continue
                        
                        # Prilepimo slike in linke
                        res['slika_url'] = orig['slika_url']
                        res['link'], res['content_id'] = orig['link'], cid

                        # Shranimo v arhiv za prihodnost
                        self.db.insert_market_data(res, orig['text'])
                        self.db.add_to_mining_queue(cid, res['link'])

                        # Razpošljemo vsem uporabnikom, ki so to ulovili
                        if cid in user_needs:
                            for target_u_id in user_needs[cid]:
                                self.db.insert_scraped_data(target_u_id, res)
                                self.db.bulk_add_sent_ads(target_u_id, [cid])
                
                time.sleep(1.5) # Premor med AI klici

        print(f"{B_GREEN}[{get_time()}] ✅ CIKEL KONČAN. Prihranjenih {total_saved_by_cache} AI klicev.{B_END}")

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