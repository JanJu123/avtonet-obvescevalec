from data_manager import DataManager
from database import Database
from scraper import Scraper


class Engine():
    def __init__(self, db: Database):
        self.db = db
        self.manager = DataManager(db)
        self.scraper = Scraper(db)
        



    def run(self, urls_to_scrape):
        """Skenira samo podane URL-je."""
        if not urls_to_scrape:
            print("[SCRAPER] Ni URL-jev na vrsti.")
            return

        for item in urls_to_scrape:
            url = item['url']
            url_id = item['url_id']
            print(f"[SCRAPER] Skeniram: {url[:50]}...")
            

    

    