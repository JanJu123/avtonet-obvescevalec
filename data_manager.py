from database import Database
import json
import sqlite3
import html

class DataManager():
    def __init__(self, database: Database):
        self.db = database

    def check_new_offers(self, filter_url_ids=None):
        """
        Poišče nove oglase. Če je podan filter_url_ids, gleda samo te URL-je.
        """
        if not filter_url_ids:
            return []

        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Priprava vprašajev za SQL ( ?, ?, ? )
        placeholders = ', '.join(['?'] * len(filter_url_ids))
        
        # Poiščemo oglase, ki so v ScrapedData, a jih uporabnik še nima v SentAds
        # Hkrati upoštevamo last_notified_at in user's scan_interval: pošljemo le, če
        # last_notified_at is NULL ali je čas od zadnjega obvestila >= scan_interval
        query = f"""
            SELECT sd.*, t.telegram_id as target_user_id, t.last_notified_at, us.scan_interval
            FROM ScrapedData sd
            JOIN Tracking t ON sd.url_id = t.url_id
            JOIN Users us ON t.telegram_id = us.telegram_id
            WHERE sd.url_id IN ({placeholders})
            AND us.is_active = 1
            AND NOT EXISTS (
                SELECT 1 FROM SentAds sa 
                WHERE sa.telegram_id = t.telegram_id 
                AND sa.content_id = sd.content_id
            )
            AND EXISTS (
                SELECT 1 FROM MarketData md
                WHERE md.content_id = sd.content_id
            )
            AND (
                t.last_notified_at IS NULL
                OR ( (strftime('%s','now','localtime') - strftime('%s', t.last_notified_at)) / 60.0 ) >= (us.scan_interval - 0.1)
            )
        """

        try:
            print(f"[DEBUG] check_new_offers querying URLs: {filter_url_ids}")
            
            # Debug: Count ads in ScrapedData
            sd_count = c.execute(f"SELECT COUNT(*) FROM ScrapedData WHERE url_id IN ({placeholders})", filter_url_ids).fetchone()[0]
            print(f"[DEBUG] ScrapedData has {sd_count} ads for these URLs")
            
            # Debug: Count after MarketData filter
            md_check = c.execute(f"""
                SELECT COUNT(*) FROM ScrapedData sd
                WHERE sd.url_id IN ({placeholders})
                AND EXISTS (SELECT 1 FROM MarketData md WHERE md.content_id = sd.content_id)
            """, filter_url_ids).fetchone()[0]
            print(f"[DEBUG] After MarketData filter: {md_check} ads")
            
            rows = c.execute(query, filter_url_ids).fetchall()
            print(f"[DEBUG] check_new_offers returned {len(rows)} ads to send")
        except Exception as e:
            print(f"[DEBUG] SQL Error in check_new_offers: {e}")
            print(f"[DEBUG] Query: {query}")
            print(f"[DEBUG] Filter IDs: {filter_url_ids}")
            rows = []
        
        conn.close()
        
        return [dict(row) for row in rows]

    def format_telegram_message(self, oglas):
        # --- PAMETNO ČIŠČENJE ---
        ime = html.escape(str(oglas.get('ime_avta') or 'Neznano'))

        # Cena (če manjka €, ga dodaj) — handle None safely
        cena_raw = oglas.get('cena')
        cena = (str(cena_raw) if cena_raw is not None else 'Po dogovoru')
        cena = cena.replace('\xa0', ' ').strip()
        # Dodaj € samo ako je cijeli broj ali "Po dogovoru" ili "Pokličite"
        if cena != 'Po dogovoru' and cena != 'Pokličite' and any(char.isdigit() for char in cena) and '€' not in cena:
            cena += " €"
        elif cena.count('€') > 1:
            # Ako je duplo €, očisti
            cena = cena.replace('€', '', cena.count('€')-1) + "€"
            

        leto = html.escape(str(oglas.get('leto_1_reg') or 'Neznano'))

        # Kilometri (če manjka km, ga dodaj)
        km_raw = oglas.get('prevozenih')
        km = (str(km_raw) if km_raw is not None else 'Neznano').strip()
        if any(char.isdigit() for char in km) and 'km' not in km.lower() and km != "Neznano":
            km += " km"
        
        gorivo = html.escape(str(oglas.get('gorivo') or 'Neznano')).replace(' motor', '')
        menjalnik = html.escape(str(oglas.get('menjalnik') or 'Neznano'))
        motor = html.escape(str(oglas.get('motor') or 'Neznano'))
        link = oglas.get('link') or 'https://www.avto.net'

        # Sestava sporočila
        msg = (
            f"<b>NOV OGLAS NAJDEN!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{ime}</b>\n\n"
            f"Cena: <b>{cena}</b>\n"
            f"Letnik: <b>{leto}</b>\n"
            f"Kilometri: <b>{km}</b>\n"
            f"Gorivo: <b>{gorivo}</b>\n"
            f"Menjalnik: <b>{menjalnik}</b>\n"
            f"Motor: <b>{motor}</b>\n\n"
            f"🔗 <a href='{link}'>KLIKNI ZA OGLED OGLASA</a>"
        )
        return msg
    


if __name__ == "__main__":
    from scraper import Scraper

    db = Database("test_bot.db")
    db.init_db()

    scraper = Scraper(DataBase=db)
    scraper.run()

    manager = DataManager(db)
    novi_oglasi = manager.check_new_offers()

    for oglas in novi_oglasi:
        tekst = manager.format_telegram_message(oglas)
        print(f"POŠILJAM: {oglas['ime_avta']}")
        # bot.send_message(chat_id, tekst)

