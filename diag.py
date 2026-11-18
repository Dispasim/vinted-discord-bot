import asyncio
import ssl
import urllib.request

import aiohttp

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
URL = "https://www.vinted.es/catalog?search_text=ice%20vibe&order=newest_first"
BASIC = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
BROWSER = {
    **BASIC,
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


async def aio(name, headers):
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get(URL) as r:
            print(f"{name}: {r.status}")


def urllib_get(name, headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=20) as r:
            print(f"{name}: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"{name}: {e.code}")


async def main():
    print("openssl:", ssl.OPENSSL_VERSION)
    await aio("aiohttp en-tetes simples", BASIC)
    await aio("aiohttp en-tetes navigateur", BROWSER)
    urllib_get("urllib en-tetes simples", BASIC)
    urllib_get("urllib en-tetes navigateur", BROWSER)


asyncio.run(main())
