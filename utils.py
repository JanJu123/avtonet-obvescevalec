import re
import json
import urllib.parse

def pocisti_ceno_v_stevilko(raw_cena):
    """Pretvori string cene (npr. '21.980 €oz. 18.016 €') v čisto število (21980)."""
    if not raw_cena or "dogovoru" in raw_cena.lower():
        return 0
    
    # 1. Odrežemo vse, kar pride po 'oz.', '+', 'Export' ali '('
    cist_niz = re.split(r'oz\.|\+|Export|\(', raw_cena)[0].strip()
    
    # 2. Odstranimo vse, kar niso številke
    samo_stevilke = re.sub(r'[^\d]', '', cist_niz)
    
    try:
        return int(samo_stevilke)
    except ValueError:
        return 0

def extrahiraj_podatke(oglas_div):
    podatki = {
        'leto': None,
        'kilometri': None,
        'gorivo': None,
        'menjalnik': None,
        'motor_podatki': None,
        'slika_url': None,
        'cena': 0,
        'ime_avta': "Neznan model",
        'link': None,
        'content_id': None
    }

    # 1. LINK in ID
    # Avto.net včasih uporablja 'stretched-link', včasih pa direktni 'a' v Nazivu
    link_el = oglas_div.select_one("a.stretched-link") or oglas_div.select_one(".GO-Results-Naziv a")
    if link_el and link_el.get('href'):
        raw_href = link_el['href']
        # Odstranimo relativne poti
        cist_href = raw_href.replace("../", "")
        if not cist_href.startswith("http"):
            podatki['link'] = "https://www.avto.net/" + cist_href
        else:
            podatki['link'] = cist_href
        
        # Ekstrakcija ID-ja iz URL-ja
        match = re.search(r'id=(\d+)', raw_href)
        podatki['content_id'] = match.group(1) if match else None

    # 2. IME AVTA
    # Vzamemo celoten tekst naziva in očistimo "NOVO" značke
    naslov_el = oglas_div.select_one(".GO-Results-Naziv")
    if naslov_el:
        podatki['ime_avta'] = naslov_el.get_text(" ", strip=True).replace("NOVO", "").strip()

    # 3. CENA
    # Avto.net ima vsaj 4 različne razrede za cene glede na vrsto oglasa
    selektorji_cen = [
        ".GO-Results-Top-Price-TXT-AkcijaCena",
        ".GO-Results-Top-Price-TXT-StaraCena",
        ".GO-Results-Top-Price-Mid",
        ".GO-Results-Price-Real",
        ".GO-Results-Price-TXT-Regular"
    ]
    
    raw_cena = ""
    for sel in selektorji_cen:
        cena_el = oglas_div.select_one(sel)
        if cena_el:
            raw_cena = cena_el.get_text(strip=True)
            if raw_cena: break # Ustavi se pri prvi najdeni ceni
    
    podatki['cena'] = pocisti_ceno_v_stevilko(raw_cena)

    # 4. SLIKA
    # Iščemo v različnih možnih kontejnerjih (Top-Photo ali samo Photo)
    img_el = oglas_div.select_one(".GO-Results-Top-Photo img, .GO-Results-Photo img, .GO-Results-Photo-Limit img")
    if img_el:
        # Prioriteta: data-src (lazy load), nato src
        url = img_el.get('data-src') or img_el.get('src')
        if url:
            # Popravek za protokole
            if url.startswith('//'):
                url = 'https:' + url
            elif not url.startswith('http'):
                url = "https://www.avto.net" + url
            podatki['slika_url'] = url

    # 5. TEHNIČNI PODATKI (Tabela pod nazivom)
    tabela = oglas_div.select_one("table")
    if tabela:
        for row in tabela.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 2:
                k = cols[0].get_text(strip=True).lower()
                v = cols[1].get_text(strip=True)
                
                if any(x in k for x in ['leto', 'registracija']): 
                    podatki['leto'] = v
                elif 'prevoženih' in k: 
                    podatki['kilometri'] = v
                elif 'gorivo' in k: 
                    podatki['gorivo'] = v
                elif 'menjalnik' in k: 
                    podatki['menjalnik'] = v
                elif 'motor' in k: 
                    podatki['motor_podatki'] = v

    return podatki


def fix_avtonet_url(url):
    """
    Popravi kodiranje (ŠČŽ) z uporabo cp1250, ki ga Avto.net razume.
    Odstrani vse presledke in popravi sortiranje, če obstaja.
    """
    # 1. Osnovno čiščenje smeti in vseh presledkov
    url = url.strip().strip('<>').replace(' ', '').replace('%20', '')

    try:
        # 2. Razstavimo URL
        u = urllib.parse.urlparse(url)
        
        # 3. Dekodiramo query parametre
        # Uporabimo 'cp1250', ker Avto.net uporablja ta standard za ŠČŽ
        query_params = urllib.parse.parse_qs(u.query, encoding='cp1250')

        # 4. Popravimo parametre (če obstajajo), da ostanejo v nujnem formatu
        if 'presort' in query_params:
            query_params['presort'] = ['3']
        if 'tipsort' in query_params:
            query_params['tipsort'] = ['DESC']
        if 'subSORT' in query_params:
            query_params['subSORT'] = ['3']
        if 'subTIPSORT' in query_params:
            query_params['subTIPSORT'] = ['DESC']
        if 'stran' in query_params:
            query_params['stran'] = ['1']

        # 5. ZAKODIRAMO NAZAJ v 'cp1250'
        # To bo spremenilo 'Š' v '%8A', kar je edini način, da Avto.net ne vrne Error 005
        new_query = urllib.parse.urlencode(query_params, doseq=True, encoding='cp1250')

        fixed_url = urllib.parse.urlunparse((
            u.scheme,
            u.netloc,
            u.path,
            u.params,
            new_query,
            u.fragment
        ))
        
        return fixed_url
    except Exception as e:
        # Če gre karkoli narobe, izpišemo in vrnemo original (da se bot ne ustavi)
        print(f"Error fixing URL encoding: {e}")
        return url