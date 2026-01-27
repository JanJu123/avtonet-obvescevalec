from database import Database
import json
import sqlite3
import html

class DataManager():
    def __init__(self, database: Database):
        self.db = database

    def check_new_offers(self, filter_url_ids=None):
        """
        Queries MarketData (source of truth) for unsent ads.
        MarketData is the permanent archive - single source of truth.
        Dedup via SentAds prevents respamming to users.
        
        For Bolha ads: all relevant data (ime_avta, lokacija, published_date, image_url)
        is in snippet_data JSON - this method merges it into the result.
        """
        if not filter_url_ids:
            return []

        conn = self.db.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Prepare SQL placeholders
        placeholders = ', '.join(['?'] * len(filter_url_ids))
        
        # Query MarketData (source of truth) for unsent ads
        query = f"""
        SELECT s.*, t.telegram_id as target_user_id
        FROM ScrapedData s
        JOIN Tracking t ON s.url_id = t.url_id
        WHERE s.url_id IN ({placeholders})
        AND NOT EXISTS (
            SELECT 1 FROM SentAds sa 
            WHERE sa.telegram_id = t.telegram_id 
            AND sa.content_id = s.content_id
        )
        ORDER BY s.created_at DESC
    """
        
        params = filter_url_ids
        rows = c.execute(query, params).fetchall()
        conn.close()
        
        # Merge JSON snippet_data back into each row
        result = []
        for row in rows:
            row_dict = dict(row)
            # Parse snippet_data JSON and merge ALL fields into row
            # This ensures Bolha ads have ime_avta, lokacija, published_date available
            if row_dict.get('snippet_data'):
                try:
                    snippet = json.loads(row_dict['snippet_data'])
                    # Merge all snippet_data fields into row_dict
                    # This overwrites None values with actual data from snippet
                    for key, value in snippet.items():
                        if value is not None:  # Only add non-None values
                            row_dict[key] = value
                except:
                    pass  # If JSON parse fails, continue with what we have
            result.append(row_dict)
        
        return result

    def format_telegram_message(self, oglas):
        from datetime import datetime
        import html
        
        # --- EXTRACT FIELDS ---
        ime = html.escape(str(oglas.get('ime_avta') or oglas.get('title', 'Neznano')))
        
        # Cena
        raw_cena = oglas.get('cena') or oglas.get('price')
        if not raw_cena:
            raw_cena = 'Po dogovoru'
        cena = str(raw_cena).replace('\xa0', ' ').strip()
        if any(char.isdigit() for char in cena) and '€' not in cena:
            cena += " €"
        
        # All other fields
        leto = oglas.get('leto_1_reg')
        km = oglas.get('prevozenih')
        gorivo = oglas.get('gorivo')
        menjalnik = oglas.get('menjalnik')
        motor = oglas.get('motor')
        lokacija = oglas.get('lokacija')
        published_date_raw = oglas.get('published_date')
        link = oglas.get('link', 'https://www.avto.net')
        
        # Format km
        if km and str(km) not in ['None', 'null', 'Neznano']:
            km_str = str(km).strip()
            if 'km' not in km_str.lower():
                km_str += " km"
        else:
            km_str = None
        
        # Format published date
        published_date = None
        if published_date_raw:
            try:
                dt = datetime.fromisoformat(published_date_raw.replace('Z', '+00:00'))
                published_date = dt.strftime('%d.%m.%Y')
            except:
                published_date = published_date_raw
        
        # --- BUILD MESSAGE ---
        msg = (
            f"<b>NOV OGLAS NAJDEN!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{ime}</b>\n\n"
            f"Cena: <b>{cena}</b>\n"
        )
        
        # Add all available fields (smart filtering - only show non-empty)
        fields = [
            ('Letnik', leto),
            ('Prevozenih', km_str),
            ('Gorivo', gorivo),
            ('Menjalnik', menjalnik),
            ('Motor', motor),
            ('Lokacija', lokacija),
            ('Objavljeno', published_date),
        ]
        
        # Only show fields that have actual values
        shown_any = False
        for label, value in fields:
            if value and str(value) not in ['None', 'null', 'Neznano', '']:
                msg += f"\n{label}: <b>{html.escape(str(value))}</b>"
                shown_any = True
        
        if shown_any:
            msg += "\n"
        
        msg += f"\n🔗 <a href='{link}'>KLIKNI ZA OGLED OGLASA</a>"
        return msg
    
    


if __name__ == "__main__":
    from scraper.avtonet.scraper import Scraper

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

