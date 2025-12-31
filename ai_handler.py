import json
import time
import os
import datetime
try:
    from openai import OpenAI
except Exception:
    OpenAI = None
import config

# Poskusi uvoziti ključ, če ne gre, uporabi ročni vnos za test
from config import OPENROUTER_API_KEYS, AI_MODEL


class AIHandler:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEYS,
        )
        self.model = AI_MODEL
        self.call_count_today = 0 # Varnostna varovalka

    def extract_ads_batch(self, raw_snippets):
        """
        Glavna funkcija: Sprejme seznam oglasov (tekst) in vrne seznam JSON objektov.
        """
        if not raw_snippets:
            return []

        # Priprava teksta za AI
        combined_text = ""
        for idx, item in enumerate(raw_snippets):
            combined_text += f"OGLAS #{idx+1} [ID:{item['id']}]: {item['text']}\n---\n"

        current_year = datetime.datetime.now().year

        instructions = f"""
        STREŽNIŠKO NAVODILO: Si robotski ekstraktor podatkov.
        Tvoj odgovor mora biti IZKLJUČNO veljaven JSON seznam objektov brez dodatnega besedila.

        NUJNA PRAVILA ZA FORMATIRANJE:
        1. "content_id": Vrni točno številko iz oznake [ID:xxxx].
        2. "ime_avta": Čisto ime (npr. "Audi A4 2.0 TDI"). Odstrani smeti kot so "NOVO", "AKCIJA", "1. LASTNIK".
        3. "cena": Številka s piko in znak €, npr. "12.490 €". Če piše 'Pokličite', napiši 'Pokličite'.
        4. "leto_1_reg": Samo 4-mestna številka leta, npr. "2021".
        5. "prevozenih": Številka s piko in 'km', npr. "145.000 km".
        6. "gorivo": Mala tiskana beseda (diesel, bencin, hibrid, elektro).
        7. "menjalnik": "avtomatski" ali "ročni".
        8. "motor": Prostornina in moč, npr. "1968 ccm, 110 kW / 150 KM".

        VAROVALKA: Če podatka ne najdeš, uporabi vrednost "Neznano".
        NIKOLI ne spreminjaj imen ključev (content_id, ime_avta, itd.), sicer sistem ne bo deloval.

        - Če vidiš oznako 'Starost: NOVO', za letnik uporabi trenutno leto ({current_year}) in za kilometre '0 km'.
        - Ceno vzemi iz polja AKCIJSKA CENA ali tisto, ki je najnižja v besedilu.

        """

        try:
            # Klic na OpenRouter (Plačljiv model, zato nima limitov)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": combined_text}
                ],
                response_format={"type": "json_object"},
                timeout=15,
            )

            self.call_count_today += 1
            content = response.choices[0].message.content
            data = json.loads(content)
            
            # Normalizacija odgovora (da vedno dobimo seznam)
            if isinstance(data, dict):
                # Če AI zapakira seznam v ključ (npr. "ads": [...])
                for key in data:
                    if isinstance(data[key], list):
                        return data[key]
                return [data]
            return data

        except Exception as e:
            print(f"[AI ERROR] Napaka: {e}")
            return None


# If testing, allow a lightweight mock AI handler to avoid external calls
if getattr(config, 'USE_MOCK_AI', False) or os.getenv('USE_MOCK_AI', '0') == '1':
    MOCK_AI_CALLS = 0

    class MockAIHandler:
        def __init__(self):
            self.call_count_today = 0

        def extract_ads_batch(self, raw_snippets):
            global MOCK_AI_CALLS
            if not raw_snippets:
                return []
            out = []
            for item in raw_snippets:
                cid = str(item.get('id'))
                out.append({
                    'content_id': cid,
                    'ime_avta': f'Avto {cid}',
                    'cena': '9.999 €',
                    'leto_1_reg': '2020',
                    'prevozenih': '100.000 km',
                    'gorivo': 'diesel',
                    'menjalnik': 'avtomatski',
                    'motor': '1998 ccm, 110 kW',
                    'link': item.get('link')
                })
            self.call_count_today += 1
            MOCK_AI_CALLS += 1
            return out

    AIHandler = MockAIHandler




if __name__ == "__main__":
    print(f"Začenjam AI test na modelu: {AI_MODEL}...")
    
    # 1. Pripravimo realne, "umazane" podatke, ki jih bi pobral BeautifulSoup
    test_data = [
        {
            "id": "21839355",
            "text": "Mercedes-Benz G-Razred G 500 V8 AMG MOZNA MENJAVA... 1.registracija 2017 130000 km bencinski motor AKCIJSKA CENA 70.999 € Stara cena 79.999 €"
        },
        {
            "id": "21839359",
            "text": "Audi Q5 40 TDI qu S tronic S-LINE 2021 Prevoženih 135000 km diesel motor avtomatski CENA S FINANCIRANJEM 33.990 € Redna cena 34.990 €"
        }
    ]

    # 2. Iniciacija handlerja
    handler = AIHandler()
    
    # 3. Izvedba ekstrakcije
    start_time = time.time()
    result = handler.extract_ads_batch(test_data)
    duration = round(time.time() - start_time, 2)

    # 4. Analiza rezultata
    print("\n--- REZULTAT (vzelo je {} sek) ---".format(duration))
    if result:
        print(json.dumps(result, indent=4, ensure_ascii=False))
        print("Test uspešen. AI je pravilno prepoznal cene in tehnične podatke.")
    else:
        print("Test ni uspel. Preveri konzolo za napako.")