import time
import random
from curl_cffi import requests


def get_latest_offers(url: str):
    """
    Fetch page content using curl_cffi.
    Universal function - works for any website.
    
    Args:
        url: URL to fetch
        
    Returns:
        Tuple of (html_content, bytes_used, status_code)
        - html_content: Page HTML as string, or None if failed
        - bytes_used: Estimated network traffic in bytes
        - status_code: HTTP status (0 = network error, 200 = success, etc)
    """
    # Clean URL
    url = url.strip().strip('<>').replace(' ', '%20').replace('\n', '').replace('\r', '')
    
    if not url.startswith("http"):
        return None, 0, 0  # Invalid URL format

    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'sl-SI,sl;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/',
        'Connection': 'keep-alive'
    }

    try:
        time.sleep(random.uniform(2, 4))
        response = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
        
        status_code = response.status_code
        encoding = response.headers.get('Content-Encoding', '').lower()
        
        if status_code == 200:
            decompressed_size = len(response.content)
            if any(comp in encoding for comp in ['gzip', 'br', 'deflate']):
                wire_size = int(decompressed_size * 0.20)
            else:
                wire_size = decompressed_size
            
            print(f"   [OK] Dostop OK! [Ocenjen promet: {round(wire_size/1024, 1)} KB | Encoding: {encoding}]")
            return response.text, wire_size, 200
        else:
            return None, 0, status_code
                
    except Exception as e:
        print(f"❌ Napaka pri skeniranju (CURL): {e}")
        return None, 0, 0 
