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
        """
        Universal message formatter for all sources: Avtonet, Bolha, Nepremičnine.
        Automatically detects and displays relevant fields based on what's available.
        """
        from datetime import datetime
        import html
        
        # --- EXTRACT CORE FIELDS ---
        # Title (works for all sources)
        ime = html.escape(str(oglas.get('ime_avta') or oglas.get('title', 'Neznano')))
        
        # Price (works for all sources)
        raw_cena = oglas.get('cena') or oglas.get('price')
        if not raw_cena:
            raw_cena = 'Po dogovoru'
        cena = str(raw_cena).replace('\xa0', ' ').strip()
        if any(char.isdigit() for char in cena) and '€' not in cena:
            cena += " €"
        
        # Link (works for all sources)
        link = oglas.get('link', 'https://www.avto.net')
        
        # --- EXTRACT SOURCE-SPECIFIC FIELDS ---
        # Avtonet fields (cars)
        leto = oglas.get('leto_1_reg')
        km = oglas.get('prevozenih')
        gorivo = oglas.get('gorivo')
        menjalnik = oglas.get('menjalnik')
        motor = oglas.get('motor')
        
        # Bolha fields (items)
        published_date_raw = oglas.get('published_date')
        
        # Nepremičnine fields (properties)
        m2 = oglas.get('m2')
        land_m2 = oglas.get('land_m2')
        prop_type = oglas.get('type')
        year = oglas.get('year')
        
        # Universal fields (all sources)
        lokacija = oglas.get('lokacija') or oglas.get('location')
        
        # --- FORMAT FIELDS ---
        # Format kilometers
        km_str = None
        if km and str(km) not in ['None', 'null', 'Neznano']:
            km_str = str(km).strip()
            if 'km' not in km_str.lower():
                km_str += " km"
        
        # Format published date (Bolha)
        published_date = None
        if published_date_raw:
            try:
                dt = datetime.fromisoformat(published_date_raw.replace('Z', '+00:00'))
                published_date = dt.strftime('%d.%m.%Y')
            except:
                published_date = published_date_raw
        
        # --- BUILD MESSAGE ---
        source_name = "AVTO.NET"  # Default
        source_emoji = "🚗"

        content_id = str(oglas.get('content_id', ''))
        if content_id.startswith('np_'):
            source_name = "NEPREMIČNINE.NET"
            source_emoji = "🏠"
        elif content_id.startswith('bo_'):
            source_name = "BOLHA.COM"
            source_emoji = "🛒"
        elif link and 'bolha.com' in link.lower():
            source_name = "BOLHA.COM"
            source_emoji = "🛒"
        elif link and 'nepremicnine.net' in link.lower():
            source_name = "NEPREMIČNINE.NET"
            source_emoji = "🏠"

        msg = (
            f"{source_emoji} <b>NOV OGLAS | {source_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>{ime}</b>\n\n"
            f"💰 Cena: <b>{cena}</b>\n"
        )
        # --- SMART FIELD DISPLAY ---
        # Group 1: Car-specific fields (Avtonet)
        car_fields = []
        if leto and str(leto) not in ['None', 'null', 'Neznano', '']:
            car_fields.append(('Letnik', leto))
        if km_str:
            car_fields.append(('Prevozenih', km_str))
        if gorivo and str(gorivo) not in ['None', 'null', 'Neznano', '']:
            car_fields.append(('Gorivo', gorivo))
        if menjalnik and str(menjalnik) not in ['None', 'null', 'Neznano', '']:
            car_fields.append(('Menjalnik', menjalnik))
        if motor and str(motor) not in ['None', 'null', 'Neznano', '']:
            car_fields.append(('🔧 Motor', motor))
        
        if car_fields:
            msg += "\n"
            for label, value in car_fields:
                msg += f"{label}: <b>{html.escape(str(value))}</b>\n"
        
        # Group 2: Property-specific fields (Nepremičnine) - MODIFIED VIA STEP 5
        property_fields = []
        if prop_type and str(prop_type).strip() not in ['None', 'null', 'Neznano', '']:
            property_fields.append(('Tip', prop_type))
        if m2 and str(m2).strip() not in ['None', 'null', 'Neznano', '']:
            property_fields.append(('Velikost', m2))
        if year and str(year).strip() not in ['None', 'null', 'Neznano', '']:
            property_fields.append(('Leto', year))
        if land_m2 and str(land_m2).strip() not in ['None', 'null', 'Neznano', '']:
            property_fields.append(('Zemljišče', land_m2))
        
        if property_fields:
            msg += "\n"
            for label, value in property_fields:
                msg += f"{label}: <b>{html.escape(str(value))}</b>\n"
        
        # Group 3: Universal fields (all sources)
        universal_fields = []
        if lokacija and str(lokacija) not in ['None', 'null', 'Neznano', '']:
            universal_fields.append(('Lokacija', lokacija))
        if published_date and str(published_date) not in ['None', 'null', 'Neznano', '']:
            universal_fields.append(('Objavljeno', published_date))
        
        if universal_fields:
            msg += "\n"
            for label, value in universal_fields:
                msg += f"{label}: <b>{html.escape(str(value))}</b>\n"
        
        # --- FOOTER ---
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

