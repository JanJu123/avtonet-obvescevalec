import sqlite3
import json
import datetime

class Database:
    def __init__(self, db_name):
        self.db_name = db_name

    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row 
        return conn

    def init_db(self):
        """Ustvari vse tabele za sistem paketov."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. USERS: Shranjuje vse o paketu in omejitvah
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_name TEXT,
            subscription_type TEXT DEFAULT 'TRAIL',
            max_urls INTEGER DEFAULT 1,
            scan_interval INTEGER DEFAULT 15,
            subscription_end DATETIME,
            expiry_reminder_sent INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            joined_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime'))
        )
        """)

        # 2. URLS: Unikatni seznami iskanj
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Urls (
            url_id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL
        )
        """)

        # 3. TRACKING: Povezava uporabnika z URL-ji
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Tracking (
            tracking_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            url_id INTEGER,
            created_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            FOREIGN KEY (telegram_id) REFERENCES Users (telegram_id) ON DELETE CASCADE,
            FOREIGN KEY (url_id) REFERENCES Urls (url_id) ON DELETE CASCADE,
            UNIQUE(telegram_id, url_id) 
        )
        """)

        # 4. SCRAPED_DATA: Zadnji podatki iz Avto.net
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ScrapedData (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER,
            content_id TEXT,           
            ime_avta TEXT,
            cena TEXT,
            leto_1_reg TEXT,     -- Preimenovano
            prevozenih TEXT,
            gorivo TEXT,
            menjalnik TEXT,      -- NOVO
            motor TEXT,           -- NOVO
            link TEXT,
            slika_url TEXT,
            created_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            FOREIGN KEY (url_id) REFERENCES Urls (url_id)
        )
        """)

        # 5. SENT_ADS: Da uporabnik ne dobi istega oglasa večkrat
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS SentAds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            content_id TEXT,
            sent_at DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            UNIQUE(telegram_id, content_id)
        )
        """)

        # 6. SCRAPER_LOGS: Statistika, MB in stroški
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ScraperLogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER,
            status_code INTEGER,
            found_count INTEGER,
            duration REAL,
            bytes_used INTEGER,
            error_msg TEXT,
            timestamp DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            FOREIGN KEY (url_id) REFERENCES Urls (url_id)
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS UserActivity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            command TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')),
            FOREIGN KEY (telegram_id) REFERENCES Users (telegram_id)
        )
        """)

        conn.commit()
        conn.close()
        print("Baza podatkov je uspešno pripravljena.")


    # --- FUNKCIJE ZA SCRAPER ---
    
    def clear_scraped_snapshot(self):
        """Pobriše vse v ScrapedData, da naredi prostor za nov snapshot."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ScrapedData")
        conn.commit()
        conn.close()

    def insert_scraped_data(self, url_id, data):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO ScrapedData (
                    url_id, content_id, ime_avta, cena, 
                    leto_1_reg, prevozenih, gorivo, menjalnik, motor, 
                    link, slika_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url_id, 
                data.get('content_id'), 
                data.get('ime_avta'), 
                data.get('cena'), 
                data.get('leto_1_reg'), # Uporabljamo novo ime ključa
                data.get('prevozenih'), 
                data.get('gorivo'), 
                data.get('menjalnik'),  # NOVO
                data.get('motor'),      # NOVO
                data.get('link'), 
                data.get('slika_url')
            ))
            conn.commit()
        except Exception as e:
            print(f"❌ Napaka pri vstavljanju v ScrapedData: {e}")
        finally:
            conn.close()

    def get_urls(self):
        """Vrne URL-je skupaj s telegram_id uporabnika, ki mu pripadajo."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Uporabimo JOIN, da dobimo telegram_id iz tabele Tracking
        query = """
            SELECT t.telegram_id, u.url_id, u.url 
            FROM Tracking t
            JOIN Urls u ON t.url_id = u.url_id
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def log_request(self, telegram_id, url_id, status_code):
        """Zapiše vsak posamezen klic v tabelo UserRequests."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO UserRequests (telegram_id, url_id, status_code) 
            VALUES (?, ?, ?)
        """, (telegram_id, url_id, status_code))
        conn.commit()
        conn.close()

    # --- FUNKCIJE ZA DATAMANAGER ---

    def get_all_scraped_snapshot(self):
        """Vrne vse trenutne podatke iz snapshot tabele."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ScrapedData")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def update_latest_offer(self, url_id, content_id, ad_name):
        """Posodobi Offers tabelo z najnovejšim ID-jem (brez processed flag-a)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO Offers (url_id, content_id, content, last_updated)
        VALUES (?, ?, ?, (strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime')))
        ON CONFLICT(url_id) DO UPDATE SET
            content_id = excluded.content_id,
            content = excluded.content,
            last_updated = excluded.last_updated
        """, (url_id, content_id, ad_name))
        conn.commit()
        conn.close()

    def get_last_known_id(self, url_id):
        """Vrne content_id zadnjega obdelanega oglasa iz tabele Offers."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT content_id FROM Offers WHERE url_id = ?", (url_id,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None

    def get_snapshot_for_url(self, url_id):
        """Vrne vse oglase iz snapshota za določen URL, sortirane od najnovejšega."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row # Da lahko dostopaš do oglas['ime_avta']
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ScrapedData WHERE url_id = ? ORDER BY id DESC", (url_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows


    def add_user_url(self, telegram_id, url):
        """Doda URL v tabelo Urls (če ga še ni) in ga poveže z uporabnikom v Tracking."""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            # 1. Poskrbimo, da URL obstaja v tabeli Urls
            c.execute("INSERT OR IGNORE INTO Urls (url) VALUES (?)", (url,))
            
            # 2. Dobimo url_id tega URL-ja
            url_id = c.execute("SELECT url_id FROM Urls WHERE url = ?", (url,)).fetchone()[0]
            
            # 3. Preverimo, če uporabnik temu že sledi
            existing = c.execute("SELECT 1 FROM Tracking WHERE telegram_id = ? AND url_id = ?", 
                                (telegram_id, url_id)).fetchone()
            if existing:
                return "exists"

            # 4. Povežemo v tabeli Tracking
            c.execute("INSERT INTO Tracking (telegram_id, url_id) VALUES (?, ?)", 
                    (telegram_id, url_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Napaka pri add_user_url: {e}")
            return False
        finally:
            conn.close()


    def remove_user_subscription(self, telegram_id, url):
        """Odstrani sledenje določenemu URL-ju za določenega uporabnika."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Najprej poiščemo telegram_id in url_id
            cursor.execute("""
                SELECT t.tracking_id FROM Tracking t
                JOIN Users u ON t.telegram_id = u.telegram_id
                JOIN Urls ur ON t.url_id = ur.url_id
                WHERE u.telegram_id = ? AND ur.url = ?
            """, (telegram_id, url))
            
            row = cursor.fetchone()
            if row:
                cursor.execute("DELETE FROM Tracking WHERE tracking_id = ?", (row[0],))
                conn.commit()
                return True
            return False  # URL-ja sploh ni bilo na seznamu
        except Exception as e:
            print(f"DB Error pri brisanju: {e}")
            return False
        finally:
            conn.close()


    def remove_subscription_by_id(self, telegram_id, tracking_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 1. Najprej ugotovimo, kateri url_id sploh brišemo (preden ga pobrišemo)
            cursor.execute("""
                SELECT url_id FROM Tracking 
                WHERE tracking_id = ? AND telegram_id = (SELECT telegram_id FROM Users WHERE telegram_id = ?)
            """, (tracking_id, telegram_id))
            
            result = cursor.fetchone()
            if not result:
                return False
                
            url_id_to_check = result[0]

            # 2. Izbrišemo povezavo iz tabele Tracking
            cursor.execute("DELETE FROM Tracking WHERE tracking_id = ?", (tracking_id,))
            
            # 3. PREVERJANJE: Ali še kdo drug sledi temu URL-ju?
            cursor.execute("SELECT COUNT(*) FROM Tracking WHERE url_id = ?", (url_id_to_check,))
            count = cursor.fetchone()[0]

            if count == 0:
                # Če ni nikogar več, lahko varno pobrišemo URL in njegovo "sidro" (Offers)
                print(f"URL ID {url_id_to_check} nima več sledilcev. Čistim...")
                cursor.execute("DELETE FROM Urls WHERE url_id = ?", (url_id_to_check,))
                cursor.execute("DELETE FROM Offers WHERE url_id = ?", (url_id_to_check,))
            else:
                print(f"URL ID {url_id_to_check} ima še {count} sledilcev. Ne brišem iz tabele Urls.")

            conn.commit()
            return True
        except Exception as e:
            print(f"Napaka pri varnem brisanju: {e}")
            return False
        finally:
            conn.close()


    def check_subscription_status(self, telegram_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        # Preverimo, če je naročnina aktivna (1) in če še ni potekla
        cursor.execute("""
            SELECT subscription_type FROM Users 
            WHERE telegram_id = ? 
            AND is_active = 1 
            AND date(subscription_end) >= date('now')
        """, (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    

    def update_user_status(self, telegram_id, sub_type=None, days=0, is_active=0):
        """
        Posodobi naročnino uporabnika.
        Če je sub_type=None, se naročnina deaktivira.
        """
        conn = self.get_connection()
        c = conn.cursor()
        
        if sub_type:
            # Aktivacija: Nastavimo tip, aktivnost in izračunamo datum poteka
            c.execute("""
                UPDATE Users 
                SET is_active = 1, 
                    subscription_type = ?, 
                    subscription_end = datetime('now', '+' || ? || ' days', 'localtime')
                WHERE telegram_id = ?
            """, (sub_type, days, telegram_id))
        else:
            # Deaktivacija: Vse postavimo na neaktivno/NULL
            c.execute("""
                UPDATE Users 
                SET is_active = 0, 
                    subscription_type = NULL, 
                    subscription_end = NULL 
                WHERE telegram_id = ?
            """, (telegram_id,))
        
        conn.commit()
        conn.close()
    

    def was_ad_sent(self, telegram_id, content_id):
        """Preveri, če je uporabnik ta oglas že kdaj prejel."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM SentAds WHERE telegram_id = ? AND content_id = ?",
            (telegram_id, content_id)
        )
        res = cursor.fetchone()
        conn.close()
        return res is not None

    def mark_as_sent(self, telegram_id, content_id):
        """Zapiše ID oglasa v zgodovino za določenega uporabnika."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO SentAds (telegram_id, content_id) VALUES (?, ?)",
                (telegram_id, content_id)
            )
            conn.commit()
        except Exception as e:
            print(f"[DB ERROR] Napaka pri mark_as_sent: {e}")
        finally:
            conn.close()

    def get_all_user_tasks(self):
        """
        Vrne vse aktivne povezave med uporabniki in URL-ji.
        DataManager to uporablja, da ve, za katerega uporabnika mora preveriti SentAds.
        """
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Povežemo Tracking s tabelo Users, da dobimo samo tiste, ki so aktivni
        query = """
            SELECT t.telegram_id, t.url_id 
            FROM Tracking t
            JOIN Users u ON t.telegram_id = u.telegram_id
            WHERE u.is_active = 1
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_admin_stats(self):
        """Vrne statistiko za DANES (od 00:00) in za tekoči mesec."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        stats = {}

        # --- OSNOVNE ŠTEVILKE ---
        stats['vsi_skenirani'] = c.execute("SELECT COUNT(*) FROM ScrapedData").fetchone()[0]
        stats['aktivni_urlji'] = c.execute("SELECT COUNT(*) FROM Urls").fetchone()[0]
        stats['skupaj_uporabnikov'] = c.execute("SELECT COUNT(*) FROM Users").fetchone()[0]

        # --- STATISTIKA DANES (Od 00:00 dalje) ---
        stats['requesti_danes'] = c.execute("""
            SELECT COUNT(*) FROM ScraperLogs
            WHERE timestamp >= datetime('now', 'start of day')
        """).fetchone()[0]

        bytes_danes = c.execute("""
            SELECT SUM(bytes_used) FROM ScraperLogs
            WHERE timestamp >= datetime('now', 'start of day')
        """).fetchone()[0] or 0
        stats['bytes_danes'] = bytes_danes
        # Strošek izračunan na enak način kot v proxy analizi
        stats['cost_danes'] = (bytes_danes / (1024**3)) * 5.0

        # --- MESEČNA STATISTIKA (Tekoči mesec) ---
        current_month = c.execute("SELECT strftime('%m', 'now')").fetchone()[0]
        current_year = c.execute("SELECT strftime('%Y', 'now')").fetchone()[0]

        query_month_count = """
            SELECT COUNT(*), SUM(bytes_used) FROM ScraperLogs 
            WHERE substr(timestamp, 4, 2) = ? AND substr(timestamp, 7, 4) = ?
        """
        res_month = c.execute(query_month_count, (current_month, current_year)).fetchone()
        stats['requesti_mesec'] = res_month[0] or 0
        bytes_mesec = res_month[1] or 0
        stats['cost_mesec'] = (bytes_mesec / (1024**3)) * 5.0

        # --- PORABA PO UPORABNIKIH (DANES - od 00:00) ---
        query_breakdown_day = """
            SELECT 
                u.telegram_name,
                COUNT(sl.id) as cnt
            FROM Users u
            JOIN Tracking t ON u.telegram_id = t.telegram_id
            JOIN ScraperLogs sl ON sl.url_id = t.url_id
            WHERE sl.timestamp >= datetime('now', 'start of day')
            GROUP BY u.telegram_id
            ORDER BY cnt DESC
        """
        c.execute(query_breakdown_day)
        stats['user_breakdown_day'] = [dict(row) for row in c.fetchall()]

        # --- PORABA PO UPORABNIKIH (MESEC) ---
        query_breakdown_month = """
            SELECT 
                u.telegram_name, 
                COUNT(sl.id) as cnt
            FROM Users u
            JOIN Tracking t ON u.telegram_id = t.telegram_id
            JOIN ScraperLogs sl ON sl.url_id = t.url_id
            WHERE substr(sl.timestamp, 4, 2) = ? AND substr(sl.timestamp, 7, 4) = ?
            GROUP BY u.telegram_id
            ORDER BY cnt DESC
        """
        c.execute(query_breakdown_month, (current_month, current_year))
        stats['user_breakdown_month'] = [dict(row) for row in c.fetchall()]

        conn.close()
        return stats
    

    def get_paid_subscribers_for_url(self, url_id):
        """Vrne seznam telegram_id-jev, ki sledijo url_id in imajo aktivno naročnino."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # SQL poizvedba, ki poveže Tracking in Users
            # Preveri: 1. ali sledijo URL-ju, 2. ali je is_active=1, 3. ali naročnina še velja
            cursor.execute("""
                SELECT u.telegram_id FROM Users u
                JOIN Tracking t ON u.telegram_id = t.telegram_id
                WHERE t.url_id = ? 
                AND u.is_active = 1 
                AND (u.subscription_end IS NULL OR datetime(u.subscription_end) > datetime('now', 'localtime'))
            """, (url_id,))
            
            rows = cursor.fetchall()
            # Vrnemo samo seznam ID-jev (npr. [123456, 876543])
            return [row[0] for row in rows]
        except Exception as e:
            print(f"Napaka pri get_paid_subscribers_for_url: {e}")
            return []
        finally:
            conn.close()

    def get_user_info(self, telegram_id):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subscription_type, subscription_start, subscription_end, joined_at 
            FROM Users 
            WHERE telegram_id = ?
        """, (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def get_all_users_admin(self):
        """Vrne vse uporabnike za admin pregled."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT telegram_id, telegram_name, is_active, subscription_type, subscription_end FROM Users")
        users = c.fetchall()
        conn.close()
        return users

    def get_all_chat_ids(self):
        """Vrne samo seznam vseh ID-jev za broadcast."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT telegram_id FROM Users")
        ids = [row[0] for row in c.fetchall()]
        conn.close()
        return ids

    def cleanup_sent_ads(self, days=14):
        """
        Pobriše staro zgodovino, vendar ne povzroči ponovnega pošiljanja,
        saj brišemo samo tisto, kar je starejše od 'days' dni.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Brišemo samo oglase, ki so starejši od X dni
            cursor.execute("DELETE FROM SentAds WHERE sent_at < datetime('now', ?)", (f'-{days} days',))
            count = cursor.rowcount
            conn.commit()
            print(f"[DB] Čiščenje uspešno: odstranjenih {count} starih zapisov.")
        except Exception as e:
            print(f"[DB] Napaka pri čiščenju: {e}")
        finally:
            conn.close()

    def get_user_urls(self, telegram_id):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        res = c.execute("""
            SELECT u.url_id, u.url 
            FROM Tracking t 
            JOIN Urls u ON t.url_id = u.url_id 
            WHERE t.telegram_id = ?
        """, (telegram_id,)).fetchall()
        conn.close()
        return res

    def register_user(self, telegram_id, telegram_name):
        """
        Registrira novega uporabnika in mu avtomatsko podeli 3 dni TRIAL paketa.
        Vrne True, če je uporabnik nov, sicer False.
        """
        conn = self.get_connection()
        c = conn.cursor()
        
        # Preverimo, če uporabnik že obstaja
        existing = c.execute("SELECT 1 FROM Users WHERE telegram_id = ?", (telegram_id,)).fetchone()

        if not existing:
            # Nastavitve za TRIAL (3 dni, 1 URL, 15 min interval)
            from datetime import datetime, timedelta
            expiry = (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y %H:%M:%S")
            
            c.execute("""
                INSERT INTO Users (
                    telegram_id, telegram_name, subscription_type, 
                    max_urls, scan_interval, subscription_end, 
                    is_active, joined_at
                ) VALUES (?, ?, 'TRIAL', 1, 15, ?, 1, strftime('%d.%m.%Y %H:%M:%S', 'now', 'localtime'))
            """, (telegram_id, telegram_name, expiry))
            
            conn.commit()
            conn.close()
            return True # Uporabnik je bil na novo ustvarjen
            
        conn.close()
        return False # Uporabnik že obstaja

    def get_user_stats_24h(self, telegram_id):
        """Prešteje skene za uporabnika v zadnjih 24 urah."""
        conn = self.get_connection()
        c = conn.cursor()
        # Povežemo ScraperLogs preko Tracking tabele z uporabnikom
        query = """
            SELECT COUNT(sl.id) 
            FROM ScraperLogs sl
            JOIN Tracking t ON sl.url_id = t.url_id
            WHERE t.telegram_id = ? 
            AND sl.timestamp >= datetime('now', '-1 day', 'localtime')
        """
        count = c.execute(query, (telegram_id,)).fetchone()[0]
        conn.close()
        return count or 0

    def get_user(self, telegram_id):
        """Vrne vse podatke o uporabniku za ukaz /info."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 
                    subscription_type, 
                    subscription_end,
                    max_urls,
                    scan_interval,
                    is_active
                FROM Users 
                WHERE telegram_id = ?
            """, (telegram_id,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                # Če datum ne obstaja, vrnemo prijazen tekst
                if not data['subscription_end']:
                    data['subscription_end'] = "Ni nastavljeno"
                return data
            return None
        finally:
            conn.close()


    def seed_test_data(self):
            """Vstavi testne podatke za lažji razvoj."""
            conn = self.get_connection()
            cursor = conn.cursor()

            # 1. Dodajanje testnih uporabnikov
            test_users = [
                (12345678, 'Janez_Novak', 'paid'),
                (87654321, 'Matija_Car', 'trial')
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO Users (telegram_id, telegram_name, subscription_type) 
                VALUES (?, ?, ?)
            """, test_users)

            # 2. Dodajanje testnih URL-jev
            test_urls = [
                (1, 'https://www.avto.net/Ads/results.asp?znamka=Audi&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran='),
                (2, 'https://www.avto.net/Ads/results.asp?znamka=VW&model=&modelID=&tip=&znamka2=&model2=&tip2=&znamka3=&model3=&tip3=&cenaMin=0&cenaMax=999999&letnikMin=0&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=0&mocMax=999999&kmMin=0&kmMax=9999999&kwMin=0&kwMax=999&motortakt=0&motorvalji=0&lokacija=0&sirina=0&dolzina=&dolzinaMIN=0&dolzinaMAX=100&nosilnostMIN=0&nosilnostMAX=999999&sedezevMIN=0&sedezevMAX=9&lezisc=&presek=0&premer=0&col=0&vijakov=0&EToznaka=0&vozilo=&airbag=&barva=&barvaint=&doseg=0&BkType=0&BkOkvir=0&BkOkvirType=0&Bk4=0&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=1000000000&EQ5=1000000000&EQ6=1000000000&EQ7=1110100120&EQ8=100000000&EQ9=1000000020&EQ10=100000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=0&paketgarancije=&broker=0&prikazkategorije=0&kategorija=0&ONLvid=0&ONLnak=0&zaloga=10&arhiv=0&presort=&tipsort=&stran=')
            ]
            cursor.executemany("INSERT OR IGNORE INTO Urls (url_id, url) VALUES (?, ?)", test_urls)

            # 3. Povezovanje uporabnikov z URL-ji (Tracking)
            test_tracking = [
                (12345678, 1), # Janez gleda Audije
                (12345678, 2), # Janez gleda tudi BMW-je
                (87654321, 1)  # Matija gleda samo Audije
            ]
            cursor.executemany("INSERT OR IGNORE INTO Tracking (telegram_id, url_id) VALUES (?, ?)", test_tracking)

            # 4. Dodajanje začetnega stanja v Offers (da scraper ve, kaj je "staro")
            # Recimo, da je bil zadnji Audi ID 21000000
            cursor.execute("""
                INSERT OR IGNORE INTO Offers (url_id, content_id, content) 
                VALUES (1, '21000000', 'Zadnji viden Audi A4')
            """)

            conn.commit()
            conn.close()
            print("Testni podatki so bili uspešno vstavljeni.")


    # --- LOGGING METODE ---

    def log_scraper_run(self, url_id, status, found, duration, bytes_used, error=""):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ScraperLogs (url_id, status_code, found_count, duration, bytes_used, error_msg)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url_id, status, found, duration, bytes_used, error))
        conn.commit()
        conn.close()

    def log_user_activity(self, telegram_id, command, details=""):
        """Zapiše aktivnost uporabnika v bazo."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO UserActivity (telegram_id, command, details)
                VALUES (?, ?, ?)
            """, (telegram_id, command, details))
            conn.commit()
        except Exception as e:
            print(f"Napaka pri logiranju aktivnosti: {e}")
        finally:
            conn.close()

    def get_recent_system_logs(self, limit=5):
        """Vrne zadnje aktivnosti uporabnikov iz tabele UserActivity."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Zamenjali smo SystemLogs z UserActivity
        cursor.execute("""
            SELECT timestamp, command, details 
            FROM UserActivity 
            ORDER BY id DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows
        
    def get_scraper_health(self, limit=10):
        """Vrne zadnjih N zapisov scraperja."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ScraperLogs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    

    def get_admin_health_stats(self):
        """Vrne povzetek delovanja v zadnjih 24 urah."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Izračunamo povprečno trajanje, skupno porabo in število napak (status != 200)
        cursor.execute("""
            SELECT 
                COUNT(*) as total_scans,
                AVG(duration) as avg_time,
                SUM(bytes_used) as total_bytes,
                SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as errors
            FROM ScraperLogs 
            WHERE timestamp >= datetime('now', '-1 day', 'localtime')
        """)
        row = cursor.fetchone()
        conn.close()
        return row

    def get_user_diagnostic(self, t_id):
        """Vrne vse info o uporabniku za diagnozo."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Podatki o naročnini
        cursor.execute("SELECT * FROM Users WHERE telegram_id = ?", (t_id,))
        user = cursor.fetchone()
        
        # Število URL-jev
        cursor.execute("SELECT COUNT(*) FROM Tracking WHERE telegram_id = ?", (t_id,))
        url_count = cursor.fetchone()[0]
        
        # Zadnjih 5 poslanih oglasov
        cursor.execute("SELECT sent_at FROM SentAds WHERE telegram_id = ? ORDER BY id DESC LIMIT 5", (t_id,))
        last_ads = cursor.fetchall()
        
        conn.close()
        return user, url_count, last_ads
    





    def get_proxy_cost_analysis(self, price_per_gb=5.0):
        """Izračuna trenutni strošek in napoved za mesec."""
        conn = self.get_connection()
        cursor = conn.cursor()

        price_per_gb = float(price_per_gb)
        
        # 1. Poraba danas
        cursor.execute("SELECT SUM(bytes_used) FROM ScraperLogs WHERE timestamp >= datetime('now', 'start of day')")
        daily_bytes = cursor.fetchone()[0] or 0
        
        # 2. Poraba zadnjih 7 dni (za povprečje)
        cursor.execute("SELECT SUM(bytes_used) FROM ScraperLogs WHERE timestamp >= datetime('now', '-7 days')")
        weekly_bytes = cursor.fetchone()[0] or 0
        
        conn.close()

        # Izračuni (v GB)
        daily_gb = daily_bytes / (1024**3)
        weekly_avg_gb = (weekly_bytes / (1024**3)) / 7 if weekly_bytes > 0 else daily_gb
        
        daily_cost = daily_gb * price_per_gb
        monthly_projection = weekly_avg_gb * 30 * price_per_gb
        
        return {
            'daily_gb': daily_gb,
            'daily_cost': daily_cost,
            'monthly_projection': monthly_projection,
            'avg_daily_gb': weekly_avg_gb
        }
    
    def add_sent_ad(self, telegram_id, content_id):
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT OR IGNORE INTO SentAds (telegram_id, content_id) VALUES (?, ?)", (telegram_id, content_id))
            conn.commit()
        finally:
            conn.close()

    # 2. Metoda za aktivacijo paketa
    def update_user_subscription(self, telegram_id, pkg_type, max_urls, interval, days_to_add):
        """Podaljša naročnino tako, da prišteje dni k obstoječemu datumu."""
        conn = self.get_connection()
        c = conn.cursor()
        
        # 1. Pridobimo trenutni datum poteka
        user = c.execute("SELECT subscription_end FROM Users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        
        now = datetime.datetime.now()
        if user and user['subscription_end']:
            try:
                # Pretvori string iz baze v objekt
                current_expiry = datetime.datetime.strptime(user['subscription_end'], "%d.%m.%Y %H:%M:%S")
                # Če je naročnina še veljavna, začnemo prištevati od datuma poteka, sicer od danes
                start_date = max(now, current_expiry)
            except:
                start_date = now
        else:
            start_date = now
        
        # Izračun novega datuma
        new_expiry_dt = start_date + datetime.timedelta(days=days_to_add)
        new_expiry_str = new_expiry_dt.strftime("%d.%m.%Y %H:%M:%S")

        # 2. Posodobimo uporabnika (novi limiti stopijo v veljavo TAKOJ)
        c.execute("""
            UPDATE Users 
            SET subscription_type = ?, max_urls = ?, scan_interval = ?, 
                subscription_end = ?, is_active = 1, expiry_reminder_sent = 0
            WHERE telegram_id = ?
        """, (pkg_type, max_urls, interval, new_expiry_str, telegram_id))
        
        conn.commit()
        conn.close()
        return new_expiry_str

    # 3. Metoda za preverjanje števila URL-jev
    def get_user_stats(self, telegram_id):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # Pridobi podatke o uporabniku
        user = c.execute("SELECT * FROM Users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        # Preštej njegove trenutne URL-je
        count = c.execute("SELECT COUNT(*) FROM Tracking WHERE telegram_id = ?", (telegram_id,)).fetchone()[0]
        conn.close()
        return user, count
    

    def get_user_subscription_info(self, telegram_id):
        """Vrne status paketa in trenutno število URL-jev za preverjanje limitov."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 1. Pridobimo podatke o paketu
        user = c.execute("""
            SELECT subscription_type, max_urls, is_active 
            FROM Users WHERE telegram_id = ?
        """, (telegram_id,)).fetchone()

        if not user:
            conn.close()
            return None
            
        # 2. Preštejemo, koliko URL-jev uporabnik dejansko ima
        count = c.execute("""
            SELECT COUNT(*) FROM Tracking WHERE telegram_id = ?
        """, (telegram_id,)).fetchone()[0]

        conn.close()

        # POMEMBNO: Ključ 'current_url_count' mora biti tukaj!
        return {
            'subscription_type': user['subscription_type'],
            'max_urls': user['max_urls'],
            'is_active': user['is_active'],
            'current_url_count': count 
        }


    def get_pending_urls(self):
        """Vrne samo URL-je, ki so znotraj limita uporabnikovega paketa."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Ta SQL magija oštevilči URL-je vsakega uporabnika. 
        # Če ima nekdo 17 URL-jev, paket pa mu dovoljuje le 5, 
        # bo ta poizvedba vrnila le prvih 5 (po datumu dodajanja).
        query = """
            WITH RankedTracking AS (
                SELECT 
                    t.url_id, 
                    u.url, 
                    us.scan_interval,
                    us.subscription_type,
                    us.is_active,
                    ROW_NUMBER() OVER (PARTITION BY us.telegram_id ORDER BY t.created_at ASC) as url_rank,
                    us.max_urls
                FROM Tracking t
                JOIN Urls u ON t.url_id = u.url_id
                JOIN Users us ON t.telegram_id = us.telegram_id
                WHERE us.is_active = 1
            )
            SELECT url_id, url, MIN(scan_interval) as min_interval,
                MAX(CASE WHEN subscription_type = 'ULTRA' THEN 1 ELSE 0 END) as has_ultra
            FROM RankedTracking
            WHERE url_rank <= max_urls
            GROUP BY url_id
        """
        active_urls = c.execute(query).fetchall()
        
        pending = []
        now = datetime.datetime.now()
        is_night = 0 <= now.hour < 7

        for row in active_urls:
            u_id = row['url_id']
            # Nočni način: Ultra na 15 min, ostali na 30 min
            if is_night:
                current_interval = 15 if row['has_ultra'] else 30
            else:
                current_interval = row['min_interval']
                
            last_log = c.execute("SELECT timestamp FROM ScraperLogs WHERE url_id = ? AND status_code = 200 ORDER BY id DESC LIMIT 1", (u_id,)).fetchone()
            
            if not last_log:
                pending.append({'url_id': u_id, 'url': row['url']})
            else:
                try:
                    last_time = datetime.datetime.strptime(last_log['timestamp'], "%d.%m.%Y %H:%M:%S")
                    if (now - last_time).total_seconds() / 60 >= (current_interval - 0.2):
                        pending.append({'url_id': u_id, 'url': row['url']})
                except:
                    pending.append({'url_id': u_id, 'url': row['url']})
                    
        conn.close()
        if pending:
            print(f"[NIGHT-MODE: {'ON' if is_night else 'OFF'}] Na vrsti za skeniranje: {len(pending)} URL-jev.")
            
        return pending
    
    def add_search_url(self, telegram_id, url):
        """Doda URL in vrne (status, url_id)."""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT OR IGNORE INTO Urls (url) VALUES (?)", (url,))
            url_id = c.execute("SELECT url_id FROM Urls WHERE url = ?", (url,)).fetchone()[0]

            existing = c.execute("SELECT 1 FROM Tracking WHERE telegram_id = ? AND url_id = ?", 
                                (telegram_id, url_id)).fetchone()
            if existing:
                return "exists", url_id

            c.execute("INSERT INTO Tracking (telegram_id, url_id) VALUES (?, ?)", (telegram_id, url_id))
            conn.commit()
            return True, url_id
        except Exception as e:
            print(f"Napaka v add_search_url: {e}")
            return False, None
        finally:
            conn.close()


    def remove_subscription_by_id(self, telegram_id, url_id):
        """
        Izbriše povezavo med uporabnikom in URL-jem. 
        Če URL-ja ne uporablja nihče drug, bi ga tehnično lahko pustili ali izbrisali, 
        vendar je ključno, da izbrišemo vnos v Tracking.
        """
        conn = self.get_connection()
        c = conn.cursor()
        try:
            # Preverimo, če ta uporabnik sploh sledi temu ID-ju
            # (Varnostna preverba, da nekdo ne izbriše tujega URL-ja)
            c.execute("SELECT 1 FROM Tracking WHERE telegram_id = ? AND url_id = ?", (telegram_id, url_id))
            if not c.fetchone():
                return False

            # Izbrišemo iz Tracking
            c.execute("DELETE FROM Tracking WHERE telegram_id = ? AND url_id = ?", (telegram_id, url_id))
            
            # Opcijsko: Počistimo tabelo Urls, če tega URL-ja nihče več ne spremlja
            # (To ohranja bazo čisto)
            c.execute("""
                DELETE FROM Urls 
                WHERE url_id = ? AND url_id NOT IN (SELECT url_id FROM Tracking)
            """, (url_id,))

            conn.commit()
            return True
        except Exception as e:
            print(f"Napaka pri remove_subscription_by_id: {e}")
            return False
        finally:
            conn.close()

    def check_new_offers(self, filter_url_ids=None):
        # V SQL poizvedbi, kjer iščeš nove oglase, dodaj:
        # WHERE url_id IN (postaji seznam url_id-jev)
        pass



    def get_users_for_expiry_reminder(self):
        """Vrne uporabnike, ki jim naročnina poteče v naslednjih 24 urah in še niso bili opomnjeni."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Pridobimo vse aktivne uporabnike
        users = c.execute("SELECT telegram_id, subscription_end, subscription_type FROM Users WHERE is_active = 1 AND expiry_reminder_sent = 0").fetchall()
        
        to_remind = []
        now = datetime.datetime.now()
        reminder_window = now + datetime.timedelta(hours=24)

        for u in users:
            if u['subscription_end']:
                try:
                    end_dt = datetime.datetime.strptime(u['subscription_end'], "%d.%m.%Y %H:%M:%S")
                    # Če naročnina poteče v naslednjih 24 urah
                    if now < end_dt <= reminder_window:
                        to_remind.append(dict(u))
                except:
                    continue
        
        conn.close()
        return to_remind

    def set_expiry_reminder_sent(self, telegram_id):
        """Označi, da je bilo opozorilo poslano."""
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE Users SET expiry_reminder_sent = 1 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        conn.close()


    def get_user_urls_with_status(self, telegram_id):
        """Vrne URL-je z oznako, ali so aktivni ali zamrznjeni zaradi limita."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Pridobimo limit uporabnika
        user = c.execute("SELECT max_urls FROM Users WHERE telegram_id = ?", (telegram_id,)).fetchone()
        limit = user['max_urls'] if user else 0
        
        # Pridobimo vse njegove URL-je
        res = c.execute("""
            SELECT u.url_id, u.url, t.created_at
            FROM Tracking t 
            JOIN Urls u ON t.url_id = u.url_id 
            WHERE t.telegram_id = ?
            ORDER BY t.created_at ASC
        """, (telegram_id,)).fetchall()
        
        urls_list = []
        for idx, row in enumerate(res):
            # Če je zaporedna številka večja od limita, je zamrznjen
            is_active = (idx < limit)
            urls_list.append({
                'url_id': row['url_id'],
                'url': row['url'],
                'active': is_active
            })
            
        conn.close()
        return urls_list



    def get_newly_expired_users(self):
        """Vrne uporabnike, ki so še označeni kot aktivni, a jim je čas potekel."""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Pridobimo vse, ki so še is_active = 1
        users = c.execute("SELECT telegram_id, subscription_end FROM Users WHERE is_active = 1").fetchall()
        
        expired = []
        now = datetime.datetime.now()

        for u in users:
            if u['subscription_end']:
                try:
                    end_dt = datetime.datetime.strptime(u['subscription_end'], "%d.%m.%Y %H:%M:%S")
                    if now >= end_dt:
                        expired.append(u['telegram_id'])
                except:
                    continue
        
        conn.close()
        return expired

    def deactivate_user_after_expiry(self, telegram_id):
        """Deaktivira uporabnika v bazi, ko mu poteče naročnina."""
        conn = self.get_connection()
        c = conn.cursor()
        # Nastavimo is_active na 0 in počistimo paket, da vemo, da je potekel
        c.execute("UPDATE Users SET is_active = 0 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        conn.close()

    
    def is_ad_new(self, content_id):
        conn = self.get_connection()
        # Preverimo, če oglas že obstaja v tabeli SentAds (zgodovina vseh poslanih)
        res = conn.execute("SELECT 1 FROM SentAds WHERE content_id = ? LIMIT 1", (content_id,)).fetchone()
        conn.close()
        return res is None
    
    def is_first_scan(self, url_id):
        """Preveri, če je bil ta URL že kdaj uspešno poskeniran."""
        conn = self.get_connection()
        # Preverimo, če v ScraperLogs že obstaja uspešen zapis (status 200)
        res = conn.execute("SELECT 1 FROM ScraperLogs WHERE url_id = ? AND status_code = 200 LIMIT 1", (url_id,)).fetchone()
        conn.close()
        return res is None

    def bulk_add_sent_ads(self, url_id, content_ids):
        """Označi oglase kot že poslane za vse uporabnike, ki sledijo temu URL-ju."""
        conn = self.get_connection()
        c = conn.cursor()
        
        # 1. Poiščemo vse uporabnike, ki dejansko sledijo temu URL-ju
        users = c.execute("SELECT telegram_id FROM Tracking WHERE url_id = ?", (url_id,)).fetchall()
        
        if not users:
            # Če ni uporabnikov (npr. pri ročnem testu), oglase označimo 
            # vsaj za ADMIN_ID, da se test ne ponavlja neskončno
            from config import ADMIN_ID
            users = [{'telegram_id': ADMIN_ID}]

        for user in users:
            t_id = user['telegram_id']
            # Masovni vpis v SentAds
            data = [(t_id, cid) for cid in content_ids]
            c.executemany("INSERT OR IGNORE INTO SentAds (telegram_id, content_id) VALUES (?, ?)", data)
        
        conn.commit()
        conn.close()





if __name__ == "__main__":
    db = Database(db_name="test_bot.db")
    db.init_db()
    db.seed_test_data()


    