import json
import time
from openai import OpenAI

# Poskusi uvoziti ključ, če ne gre, uporabi ročni vnos za test
try:
    from config import OPENROUTER_API_KEY, AI_MODEL
except ImportError:
    OPENROUTER_API_KEY = "sk-or-v1-..." # Tvoj ključ tukaj, če ne uporabljaš config.py
    AI_MODEL = "google/gemini-flash-1.5-8b"

class AIHandler:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
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

        prompt = f"""
        Iz spodnjih oglasov izlušči podatke za VSAK avto posebej.
        Vrni IZKLJUČNO JSON seznam objektov.

        Zahtevan format:
        {{
            "content_id": "ID",
            "ime_avta": "polno ime",
            "cena": "cena v €",
            "leto_1_reg": "le leto prve registracije",
            "prevozenih": "kilometri",
            "gorivo": "vrsta motorja",
            "menjalnik": "ročni ali avtomatski",
            "motor": "npr. 1968 ccm, 110 kW / 150 KM"
        }}

        PODATKI:
        {combined_text}
        """

        try:
            # Klic na OpenRouter (Plačljiv model, zato nima limitov)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Si precizen ekstraktor podatkov iz avtomobilskih oglasov. Vračaš samo čist JSON seznam."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                timeout=15
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
            print(f"❌ [AI ERROR] Napaka: {e}")
            return None




if __name__ == "__main__":
    print(f"🚀 Začenjam AI test na modelu: {AI_MODEL}...")
    
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
        print("\n✅ Test uspešen! AI je pravilno prepoznal cene in tehnične podatke.")
    else:
        print("❌ Test ni uspel. Preveri konzolo za napako.")