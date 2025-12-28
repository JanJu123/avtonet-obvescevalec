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
    Popravi kodiranje in odstrani presledke, strukturo pa pusti 100% isto.
    Namenjeno reševanju napake 005 brez brisanja parametrov.
    """
    # 1. Osnovno čiščenje zunanjih znakov in vseh presledkov v linku
    # Avto.net v URL-ju ne sme imeti nobenega presledka!
    url = url.strip().strip('<>').replace(' ', '').replace('%20', '')

    try:
        # 2. Najprej dekodiramo vse, da dobimo čiste slovenske znake (ŠČŽ)
        # Poskusimo najprej z latin-1 (Avto.net standard)
        decoded = urllib.parse.unquote(url, encoding='latin-1')
        
        # 3. Ročni popravek, če je 'Škoda' slučajno postala 'koda' ali 'koda'
        if 'koda' in decoded and 'Škoda' not in decoded:
            decoded = decoded.replace('koda', 'Škoda')

        # 4. Ponovno zakodiramo v latin-1 (Windows-1250)
        # To je tisto, kar Avto.net dejansko pričakuje za ŠČŽ
        u = urllib.parse.urlparse(decoded)
        query_dict = urllib.parse.parse_qs(u.query)
        
        # Ponovno sestavimo query string z latin-1 kodiranjem
        # safe=':/?&=,' prepreči kodiranje nujnih znakov
        new_query = urllib.parse.urlencode(query_dict, doseq=True, encoding='latin-1')
        
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
        print(f"Error fixing URL encoding: {e}")
        return url