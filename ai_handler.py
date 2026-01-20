import json
import time
from openai import OpenAI


from config import OPENROUTER_API_KEYS, AI_MODEL


class AIHandler:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEYS[0],
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
        
        # DEBUG: Show what we're sending
        print(f"\n[AI DEBUG] Sending {len(raw_snippets)} ads to AI:")
        print(f"Combined text length: {len(combined_text)} chars")
        print(f"First 500 chars:\n{combined_text[:500]}\n")

        prompt = f"""
        STREŽNIŠKO NAVODILO: Si robotski ekstraktor podatkov za avtomobilske oglase. 
        Tvoj odgovor mora biti IZKLJUČNO veljaven JSON seznam objektov brez dodatnega besedila.

        NUJNA PRAVILA ZA FORMATIRANJE:
        1. "content_id": Vrni točno številko/ID iz oznake [ID:xxxx].
        2. "ime_avta": Čisto ime (npr. "Audi A4 2.0 TDI"). Odstrani smeti kot so "NOVO", "AKCIJA", "1. LASTNIK".
        3. "cena": Številka s piko in znak €, npr. "12.490 €". Če piše 'Pokličite' ali je neznana, napiši 'Pokličite'.

        AVTONET SPECIFIČNA POLJA (VEDNO vključi, tudi če je null/neznano):
        4. "leto_1_reg": Samo 4-mestna številka leta, npr. "2021". Vrni null če ni.
        5. "prevozenih": Številka s piko in 'km', npr. "145.000 km". Vrni null če ni.
        6. "gorivo": Mala tiskana beseda (diesel, bencin, hibrid, elektro). Vrni null če ni.
        7. "menjalnik": "avtomatski" ali "ročni". Vrni null če ni.
        8. "motor": Prostornina in moč, npr. "1968 ccm, 110 kW / 150 KM". Vrni null če ni.

        DODATNA POLJA (če obstajajo - vrni null če niso):
        9. "lokacija": Mesto prodajnega oglasa.
        10. "objavljen": Datum objave ali čas objave.
        11. "starost": Starost vozila (npr. "5 let") - za motorje/skuterje.
        12. "moč": Moč motorja (npr. "118 kW" ali "50 ccm").
        13. "obseg": Prostornina (npr. "600 ccm").
        14. "teža": Masa (npr. "200 kg").

        KRITIČNO: Vsi ključi morajo biti točno kot zgoraj našteti! Ne spreminjaj imen!

        PODATKI ZA OBDELAVO:
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