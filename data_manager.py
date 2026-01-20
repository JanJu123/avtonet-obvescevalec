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
            SELECT m.*, t.telegram_id as target_user_id
            FROM MarketData m
            JOIN Tracking t ON m.url_id = t.url_id
            WHERE m.url_id IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM SentAds sa 
                WHERE sa.telegram_id = t.telegram_id 
                AND sa.content_id = m.content_id
            )
            ORDER BY m.created_at DESC
        """
        
        params = filter_url_ids
        rows = c.execute(query, params).fetchall()
        conn.close()
        
        # Merge JSON metadata back into each row
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
        
        # --- PAMETNO ČIŠČENJE ---
        # After merge, all fields from snippet_data are directly available
        # Works for both Avtonet (ime_avta from main field) and Bolha (ime_avta from snippet_data)
        ime = html.escape(str(oglas.get('ime_avta', 'Neznano')))
        
        # Cena (če manjka €, ga dodaj) — varovalka za None/številke
        raw_cena = oglas.get('cena') or oglas.get('price')
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
        
        # For Bolha: location and publish time (from merged snippet_data)
        lokacija = oglas.get('lokacija', '').strip() if oglas.get('lokacija') else None
        
        # Format publish date to Slovenian format (DD.MM.YYYY)
        published_date_raw = oglas.get('published_date', '').strip() if oglas.get('published_date') else None
        published_date = None
        if published_date_raw:
            try:
                # Parse ISO format: 2026-01-20T18:34:59+01:00
                dt = datetime.fromisoformat(published_date_raw.replace('Z', '+00:00'))
                published_date = dt.strftime('%d.%m.%Y')
            except:
                published_date = published_date_raw  # Fallback to raw if parsing fails
        
        link = oglas.get('link', 'https://www.avto.net')

        # Sestava sporočila
        msg = (
            f"<b>NOV OGLAS NAJDEN!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{ime}</b>\n\n"
            f"Cena: <b>{cena}</b>\n"
        )
        
        # Add car-specific fields (Avtonet)
        if leto != 'Neznano' or km != 'Neznano' or gorivo != 'Neznano':
            msg += (
                f"Letnik: <b>{leto}</b>\n"
                f"Kilometri: <b>{km}</b>\n"
                f"Gorivo: <b>{gorivo}</b>\n"
                f"Menjalnik: <b>{menjalnik}</b>\n"
                f"Motor: <b>{motor}</b>\n\n"
            )
        
        # Add Bolha-specific fields (location, publish time)
        if lokacija or published_date:
            if lokacija:
                msg += f"Lokacija: <b>{html.escape(lokacija)}</b>\n"
            if published_date:
                msg += f"Objavljeno: <b>{published_date}</b>\n"
            msg += "\n"
        
        msg += f"🔗 <a href='{link}'>KLIKNI ZA OGLED OGLASA</a>"
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

