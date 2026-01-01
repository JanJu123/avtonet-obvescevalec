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
        query = f"""
            SELECT sd.*, t.telegram_id as target_user_id
            FROM ScrapedData sd
            JOIN Tracking t ON sd.url_id = t.url_id
            WHERE sd.url_id IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM SentAds sa 
                WHERE sa.telegram_id = t.telegram_id 
                AND sa.content_id = sd.content_id
            )
        """
        
        rows = c.execute(query, filter_url_ids).fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def format_telegram_message(self, oglas):
        # --- PAMETNO ČIŠČENJE ---
        ime = html.escape(str(oglas.get('ime_avta', 'Neznano')))
        
        # Cena (če manjka €, ga dodaj) — varovalka za None/številke
        raw_cena = oglas.get('cena')
        if not raw_cena:
            raw_cena = 'Po dogovoru'
        cena = str(raw_cena).replace('\xa0', ' ').strip()
        if any(char.isdigit() for char in cena) and '€' not in cena:
            cena += " €"
            
        leto = html.escape(str(oglas.get('leto_1_reg', 'Neznano')))
        
        # Kilometri (če manjka km, ga dodaj)
        km = str(oglas.get('prevozenih', 'Neznano')).strip()
        if any(char.isdigit() for char in km) and 'km' not in km.lower() and km != "Neznano":
            km += " km"
        
        gorivo = html.escape(str(oglas.get('gorivo', 'Neznano'))).replace(' motor', '')
        menjalnik = html.escape(str(oglas.get('menjalnik', 'Neznano')))
        motor = html.escape(str(oglas.get('motor', 'Neznano')))
        link = oglas.get('link', 'https://www.avto.net')

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

