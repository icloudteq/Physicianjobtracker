import httpx
from bs4 import BeautifulSoup

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"}
client = httpx.Client(headers=headers, timeout=15, follow_redirects=True)

r = client.get("https://www.doccafe.com/physician-jobs/specialty/internal-medicine/us/state/north-carolina")
soup = BeautifulSoup(r.text, "lxml")
links = soup.select("a[href*='/job/physician']")

# Look at first 3 jobs
for lnk in links[:3]:
    title = lnk.get_text(strip=True)
    href = "https://www.doccafe.com" + lnk.get("href","")

    # Go up to find container (card)
    card = lnk.parent
    for _ in range(4):
        if card and card.name == "div" and len(card.get_text(strip=True)) > len(title) + 10:
            break
        if card:
            card = card.parent

    # Extract all text from card children
    if card:
        children_text = [c.get_text(strip=True) for c in card.children if hasattr(c,'get_text') and c.get_text(strip=True)]
        print(f"Title: {title}")
        print(f"URL: {href}")
        print(f"Card children: {children_text[:8]}")
        print("---")
