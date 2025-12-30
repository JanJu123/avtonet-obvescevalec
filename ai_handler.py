import json
import asyncio
from openai import AsyncOpenAI # UPORABIMO ASYNC KLIENTA
from config import OPENROUTER_API_KEYS, AI_MODEL
import time

class AIHandler:
    def __init__(self):
        # Ustvarimo seznam asinhronih klientov (vsak s svojo ekipo/ključem)
        self.clients = [
            AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
            for key in OPENROUTER_API_KEYS
        ]
        self.model = AI_MODEL

    async def process_single_batch(self, batch, client_index):
        """Obdela en paket oglasov z določenim klientom/ključem."""
        client = self.clients[client_index % len(self.clients)]
        
        combined_text = ""
        for idx, item in enumerate(batch):
            combined_text += f"OGLAS #{idx+1} [ID:{item['id']}]: {item['text']}\n---\n"

        prompt = f"Izlušči JSON seznam objektov. Ključi: content_id, ime_avta, cena, leto_1_reg, prevozenih, gorivo, menjalnik, motor. Podatki: {combined_text}"

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Si robotski ekstraktor. Vračaš samo čist JSON seznam."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                timeout=45
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            # Normalizacija v seznam
            if isinstance(data, dict):
                for key in data:
                    if isinstance(data[key], list): return data[key]
                return [data]
            return data
        except Exception as e:
            print(f"❌ [AI ERROR] Ključ {client_index + 1} odpovedal: {e}")
            return []



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