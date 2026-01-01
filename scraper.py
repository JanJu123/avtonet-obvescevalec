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

    def get_latest_offers(self, url: str):
        """Pridobi oglase, očisti URL in vrne (HTML, bytes, status_code)."""
        # --- 1. KORAK: ČIŠČENJE URL-ja ---
        url = url.strip().strip('<>').replace(' ', '%20').replace('\n', '').replace('\r', '')
        
        if not url.startswith("http"):
            return None, 0, 0 # Status 0 pomeni napačen format / CURL ni niti poskusil

        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'sl-SI,sl;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive'
        }

        try:
            # Respect configurable fetch delays
            try:
                smin = float(config.FETCH_SLEEP_MIN)
                smax = float(config.FETCH_SLEEP_MAX)
            except Exception:
                smin, smax = 2.0, 4.0
            time.sleep(random.uniform(smin, smax))
            response = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
            
            status_code = response.status_code
            encoding = response.headers.get('Content-Encoding', '').lower()
            
            if status_code == 200:
                decompressed_size = len(response.content)
                if any(comp in encoding for comp in ['gzip', 'br', 'deflate']):
                    wire_size = int(decompressed_size * 0.20)
                    savings = 80.0
                else:
                    wire_size = decompressed_size
                    savings = 0.0
                
                print(f"OK: Dostop uspešen. Ocenjen promet: {round(wire_size/1024, 1)} KB | Encoding: {encoding}")
                return response.text, wire_size, 200
            else:
                # Vrnemo status kodo (403, 404, 500...), da vemo kaj je narobe
                return None, 0, status_code
                
        except Exception as e:
            # Če curl sploh ne more izvesti ukaza (npr. napačen port v URL)
            print(f"ERROR: Napaka pri skeniranju (CURL): {e}")
            return None, 0, 0 # Status 0 = Network/CURL error
        

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

                print(f"{B_CYAN}[{get_time()}] Skeniram URL ID {u_id} (Uporabnik: {u_name})...{B_END}")
                
                html, bytes_used, status_code = self.get_latest_offers(final_url)
                
                if not html:
                    current_fails = self.db.update_url_fail_count(u_id)
                    actual_error = f"HTTP {status_code}" if status_code != 0 else "CURL Error"
                    print(f"{B_RED}[{get_time()}] ERROR: {actual_error} ({current_fails}/3) za {u_name}{B_END}")
                    self.db.log_scraper_run(u_id, status_code, 0, round(time.time() - start_time, 2), 0, actual_error)
                    continue
                else:
                    self.db.reset_url_fail_count(u_id)

                is_first = self.db.is_first_scan(u_id)
                # Detect marker that indicates regular search results block
                marker_text = "Redna ponudba po kriterijih iskanja:".lower()
                page_has_marker = marker_text in (html or "").lower()
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

                    # NOVA LOGIKA: Vsi oglasi gredo v ScrapedData (unfiltered)
                    # Potem check_new_offers() filtrira po MarketData
                    if not is_first:
                        # Preverimo MarketData za AI reuse
                        existing_ad = self.db.get_market_data_by_id(content_id)
                        
                        if existing_ad:
                            # [REUSE] iz MarketData - takoj dodamo v final_results brez AI
                            print(f"{B_GREEN}[{get_time()}] [REUSE] Oglas {content_id} najden v arhivu.{B_END}")
                            ad_data = dict(existing_ad)  # Convert Row to dict
                            ad_data['content_id'] = content_id
                            ad_data['link'] = "https://www.avto.net" + href.replace("..", "")
                            img_tag = row.find('img')
                            ad_data['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                            final_results.append(ad_data)
                        else:
                            # Nov oglas - potrebuje AI
                            try:
                                self.db.insert_market_placeholder(content_id, "https://www.avto.net" + href.replace("..", ""), self._clean_row_for_ai(row))
                            except Exception:
                                pass

                            try:
                                acquired = self.db.mark_market_processing(content_id)
                            except Exception:
                                acquired = False

                            if acquired:
                                ads_to_ai_batch.append({
                                    "id": content_id,
                                    "row_soup": row,
                                    "text": self._clean_row_for_ai(row),
                                    "link": "https://www.avto.net" + href.replace("..", ""),
                                    "slika_url": None
                                })
                            else:
                                print(f"{B_YELLOW}[{get_time()}] Oglas {content_id} že v obdelavi drugje.{B_END}")

                if is_first:
                    print(f"[{get_time()}] Prvi sken za {u_name}: Sinhroniziram {len(all_ids_on_page)} oglasov.")
                    self.db.bulk_add_sent_ads(u_id, all_ids_on_page)
                    self.db.log_scraper_run(u_id, 200, 0, round(time.time() - start_time, 2), bytes_used, "Initial Sync")
                    continue

                # --- AI PROCESIRANJE (Batching) ---
                # If page contains marker and we found at least one new ad, check subsequent pages up to a limit
                try:
                    if page_has_marker and (len(ads_to_ai_batch) + len(final_results) > 0):
                        
                        max_pages = getattr(config, 'SCRAPER_MAX_PAGINATION_PAGES', 3)
                        # Determine current page number if present
                        m = re.search(r"stran=(\d+)", final_url)
                        cur_page = int(m.group(1)) if m else 1

                        # Fetch pages cur_page+1 .. cur_page+(max_pages-1)
                        for p in range(cur_page + 1, cur_page + 1 + (max_pages - 1)):
                            # build next page url
                            if 'stran=' in final_url:
                                next_url = re.sub(r"stran=\d+", f"stran={p}", final_url)
                            else:
                                sep = '&' if '?' in final_url else '?'
                                next_url = final_url + f"{sep}stran={p}"

                            next_html, next_bytes, next_status = self.get_latest_offers(next_url)
                            if not next_html:
                                # stop on fetch error
                                break

                            next_ads = self._get_new_ads_raw(next_html)
                            if not next_ads:
                                # no new ads on this page; continue to next page (still bounded)
                                continue

                            # process new ads from next page same as current page
                            for ad in next_ads:
                                cid = ad['id']
                                existing = self.db.get_market_data_by_id(cid)
                                if existing and existing.get('processed'):
                                    continue
                                try:
                                    self.db.insert_market_placeholder(cid, ad.get('link'), ad.get('text'))
                                except Exception:
                                    pass
                                try:
                                    acquired = self.db.mark_market_processing(cid)
                                except Exception:
                                    acquired = False
                                if acquired:
                                    ads_to_ai_batch.append({
                                        "id": cid,
                                        "row_soup": None,
                                        "text": ad.get('text'),
                                        "link": ad.get('link'),
                                        "slika_url": ad.get('slika_url')
                                    })
                except Exception:
                    pass
                # --- AI PROCESIRANJE ---
                if ads_to_ai_batch:
                    # Flood Protection (max 5)
                    # Limit per-user AI items using config.MAX_AI_PER_USER
                    try:
                        max_ai = int(config.MAX_AI_PER_USER)
                    except Exception:
                        max_ai = 5
                    if len(ads_to_ai_batch) > max_ai:
                        to_mute_ids = [ad['id'] for ad in ads_to_ai_batch[max_ai:]]
                        self.db.bulk_add_sent_ads(u_id, to_mute_ids)
                        ads_to_ai_batch = ads_to_ai_batch[:max_ai]

                    if config.USE_AI:
                        print(f"{B_YELLOW}[{get_time()}] AI obdeluje {len(ads_to_ai_batch)} oglasov za {u_name}...{B_END}")
                        try:
                            ai_results = self.ai.extract_ads_batch(ads_to_ai_batch)
                        except Exception as e:
                            ai_results = None
                            # Log AI failure for visibility
                            try:
                                for ad in ads_to_ai_batch:
                                    self.db.log_ai_error(ad.get('id'), f"AI exception: {e}")
                            except Exception:
                                pass

                        if ai_results:
                            for ad_data in ai_results:
                                ad_id = str(ad_data.get('content_id') or ad_data.get('id') or ad_data.get('ID'))
                                # Poiščemo pripadajoč originalen snippet
                                orig = next((x for x in ads_to_ai_batch if str(x['id']) == ad_id), None)
                                
                                if orig:
                                    # Pripravimo končne podatke
                                    ad_data['content_id'] = ad_id
                                    ad_data['link'] = orig['link']
                                    # orig['row_soup'] may be None for ads fetched from subsequent pages
                                    row_soup = orig.get('row_soup')
                                    if row_soup:
                                        img_tag = row_soup.find('img')
                                        ad_data['slika_url'] = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                                    else:
                                        # fallback to any slika_url provided by ad placeholder
                                        ad_data['slika_url'] = orig.get('slika_url')

                                    # DODAMO V REZULTATE ZA UPORABNIKA
                                    final_results.append(ad_data)

                                    # TAKOJ SHRANIMO V MARKET DATA (Tukaj je zdaj varno!)
                                    try:
                                        self.db.insert_market_data(ad_data, orig.get('text'))
                                    except Exception:
                                        pass
                        else:
                            print(f"[{get_time()}] AI odpovedal, preklop na manual.")
                            try:
                                for ad in ads_to_ai_batch:
                                    self.db.log_ai_error(ad.get('id'), 'AI returned no result for batch')
                            except Exception:
                                pass

                # --- MANUAL FALLBACK (za tiste, ki še niso v final_results) ---
                # Preverimo, če nam v ads_to_ai_batch manjka kakšen oglas (ker ga AI ni vrnil ali je USE_AI=False)
                for item in ads_to_ai_batch:
                    if not any(str(res.get('content_id')) == str(item['id']) for res in final_results):
                        row_soup = item.get('row_soup')
                        if row_soup:
                            img_tag = row_soup.find('img')
                            img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else None
                            manual_data = self._manual_parse_row(row_soup, item['id'], item['link'], img_url)
                        else:
                            # No soup available (pagination placeholder) — create minimal manual_data
                            manual_data = {
                                'content_id': str(item['id']),
                                'ime_avta': item.get('text', 'Neznano')[:100],
                                'cena': 'Po dogovoru',
                                'leto_1_reg': 'Neznano',
                                'prevozenih': 'Neznano',
                                'gorivo': 'Neznano',
                                'menjalnik': 'Neznano',
                                'motor': 'Neznano',
                                'link': item.get('link'),
                                'slika_url': item.get('slika_url')
                            }

                        final_results.append(manual_data)
                        # Shranimo tudi ročno prebrane podatke v arhiv
                        try:
                            self.db.insert_market_data(manual_data, item.get('text'))
                        except Exception:
                            pass

                # --- VPIS V BAZO ZA TELEGRAM OBVESTILA ---
                for data in final_results:
                    self.db.insert_scraped_data(u_id, data)

                # Logiranje uspeha
                duration = round(time.time() - start_time, 2)
                self.db.log_scraper_run(u_id, 200, len(final_results), duration, bytes_used, "Success")
                if final_results:
                    print(f"OK [{get_time()}] URL {u_id} končan ({len(final_results)} oglasov) v {duration}s.")

            except Exception as e:
                print(f"{B_RED}[{get_time()}] Kritična napaka pri URL {u_id}: {e}{B_END}")
            
            # Pause between URL entries to avoid bursts
            try:
                esmin = float(config.ENTRY_SLEEP_MIN)
                esmax = float(config.ENTRY_SLEEP_MAX)
            except Exception:
                esmin, esmax = 1.5, 3.0
            time.sleep(random.uniform(esmin, esmax))

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
    print("ZAČENJAM BINARNI HYBRID TEST...")
    print("="*50)
    
    scraper = Scraper(DataBase=test_db)
    
    # Zaženemo run metodo z našim testnim seznamom
    scraper.run(pending_test_list)

    print("\n" + "="*50)
    print("TEST ZAKLJUČEN. Preveri loge zgoraj!")
    print("="*50)