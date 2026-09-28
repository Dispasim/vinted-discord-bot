import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qsl

import aiohttp
import discord
from discord.ext import tasks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vinted-bot")

CONFIG_PATH = Path(__file__).parent / "config.json"
SEEN_PATH = Path(__file__).parent / "seen_items.json"
MAX_SEEN_PER_SEARCH = 300

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"Fichier {CONFIG_PATH.name} introuvable. "
            f"Copie config.example.json vers config.json et remplis-le."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_seen() -> dict:
    if SEEN_PATH.exists():
        try:
            return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_seen(seen: dict) -> None:
    SEEN_PATH.write_text(json.dumps(seen), encoding="utf-8")


def build_search(url: str, _depth: int = 0) -> dict:
    """Extrait le domaine vinted et les paramètres de recherche depuis une URL copiée sur le site."""
    parsed = urlparse(url)
    domain = parsed.netloc or "www.vinted.fr"
    params = dict(parse_qsl(parsed.query))

    # Certains partages (Instagram, Facebook, etc.) enveloppent la vraie URL
    # dans un paramètre "u" (ex: https://l.instagram.com/?u=<url encodée>&e=...).
    if "vinted" not in domain.lower() and "u" in params and _depth < 3:
        log.warning(
            "L'URL configurée pointe vers %s (pas Vinted) — on essaie de déballer "
            "le lien de redirection trouvé dans le paramètre 'u'.",
            domain,
        )
        return build_search(params["u"], _depth + 1)

    if "vinted" not in domain.lower():
        log.error(
            "L'URL configurée pointe vers '%s', qui ne semble pas être un domaine Vinted. "
            "Va sur vinted.fr (ou ton pays), fais ta recherche avec tes filtres, et copie "
            "l'URL directement depuis la barre d'adresse du navigateur (pas un lien partagé).",
            domain,
        )

    params["order"] = "newest_first"
    params["per_page"] = "20"
    return {"domain": domain, "params": params}


class VintedClient:
    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self._cookie_domains: set[str] = set()

    async def start(self):
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
        )

    async def close(self):
        if self._session:
            await self._session.close()

    async def _ensure_cookies(self, domain: str):
        if domain in self._cookie_domains:
            return
        try:
            async with self._session.get(f"https://{domain}/", timeout=aiohttp.ClientTimeout(total=15)) as resp:
                await resp.read()
                self._cookie_domains.add(domain)
        except Exception as exc:
            log.warning("Impossible de récupérer les cookies pour %s: %s", domain, exc)

    async def fetch_items(self, domain: str, params: dict) -> list[dict]:
        await self._ensure_cookies(domain)
        api_url = f"https://{domain}/api/v2/catalog/items"
        for attempt in range(2):
            async with self._session.get(
                api_url, params=params, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("items", [])
                if resp.status in (401, 403) and attempt == 0:
                    log.info("Cookies expirés pour %s, on les rafraîchit...", domain)
                    self._cookie_domains.discard(domain)
                    await self._ensure_cookies(domain)
                    continue
                text = await resp.text()
                log.warning("Vinted a répondu %s pour %s: %s", resp.status, domain, text[:200])
                return []
        return []


def format_price(item: dict) -> str:
    price = item.get("total_item_price") or item.get("price") or {}
    amount = price.get("amount")
    currency = price.get("currency_code", "")
    if amount is None:
        return "?"
    return f"{amount} {currency}"


def build_embed(item: dict, domain: str) -> discord.Embed:
    item_id = item.get("id")
    title = item.get("title") or "Nouvelle annonce"
    url = f"https://{domain}/items/{item_id}"
    embed = discord.Embed(title=title[:256], url=url, color=discord.Color.green())
    embed.add_field(name="Prix", value=format_price(item), inline=True)
    size = item.get("size_title")
    if size:
        embed.add_field(name="Taille", value=size, inline=True)
    brand = item.get("brand_title")
    if brand:
        embed.add_field(name="Marque", value=brand, inline=True)
    photo = item.get("photo") or {}
    photo_url = photo.get("url")
    if photo_url:
        embed.set_thumbnail(url=photo_url)
    user = item.get("user") or {}
    if user.get("login"):
        embed.set_footer(text=f"Vendeur : {user['login']}")
    return embed


class VintedBot(discord.Client):
    def __init__(self, config: dict, **kwargs):
        intents = discord.Intents.default()
        super().__init__(intents=intents, **kwargs)
        self.config = config
        self.destinations = [
            {
                "name": dest.get("name", f"destination-{i}"),
                "channel_id": dest["channel_id"],
                "role_id": dest["role_id"],
                "searches": [
                    {"name": s["name"], **build_search(s["url"])} for s in dest["searches"]
                ],
            }
            for i, dest in enumerate(config["destinations"])
        ]
        self.vinted = VintedClient()
        self.seen = load_seen()

    async def setup_hook(self) -> None:
        await self.vinted.start()
        interval = self.config.get("check_interval_seconds", 60)
        self.poll_searches.change_interval(seconds=interval)
        self.poll_searches.start()

    async def on_ready(self):
        log.info("Connecté en tant que %s", self.user)

    @tasks.loop(seconds=60)
    async def poll_searches(self):
        for dest in self.destinations:
            channel = self.get_channel(dest["channel_id"])
            if channel is None:
                try:
                    channel = await self.fetch_channel(dest["channel_id"])
                except discord.HTTPException as exc:
                    log.error(
                        "Salon Discord introuvable pour la destination '%s' (channel_id incorrect ?): %s",
                        dest["name"], exc,
                    )
                    continue

            for search in dest["searches"]:
                await self._poll_one(dest, search, channel)
                await asyncio.sleep(2)

    async def _poll_one(self, dest: dict, search: dict, channel: discord.abc.Messageable):
        name = search["name"]
        domain = search["domain"]
        seen_key = f"{dest['name']}::{name}"
        items = await self.vinted.fetch_items(domain, dict(search["params"]))
        if not items:
            return

        seen_ids = set(self.seen.get(seen_key, []))
        first_run = seen_key not in self.seen
        new_items = [it for it in items if str(it.get("id")) not in seen_ids]

        # met à jour la liste des IDs vus
        all_ids = [str(it.get("id")) for it in items] + list(seen_ids)
        self.seen[seen_key] = all_ids[:MAX_SEEN_PER_SEARCH]
        save_seen(self.seen)

        if first_run:
            log.info(
                "Première vérification pour '%s' (%s) : %d annonces marquées comme déjà vues.",
                name, dest["name"], len(items),
            )
            return

        for item in reversed(new_items):
            embed = build_embed(item, domain)
            role_id = dest["role_id"]
            try:
                await channel.send(
                    content=f"<@&{role_id}> Nouvelle annonce pour **{name}** !",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
            except discord.HTTPException as exc:
                log.error("Échec de l'envoi du message Discord (%s): %s", dest["name"], exc)
            await asyncio.sleep(1)

        if new_items:
            log.info("%d nouvelle(s) annonce(s) pour '%s' (%s)", len(new_items), name, dest["name"])


async def main():
    config = load_config()
    if not config.get("destinations"):
        raise SystemExit(
            "Ajoute au moins une destination dans config.json (section 'destinations'), "
            "chacune avec son channel_id, role_id et ses propres 'searches'."
        )
    for dest in config["destinations"]:
        if not dest.get("searches"):
            raise SystemExit(f"La destination '{dest.get('name')}' n'a aucune recherche configurée.")

    bot = VintedBot(config)
    try:
        await bot.start(config["discord_token"])
    finally:
        await bot.vinted.close()


if __name__ == "__main__":
    asyncio.run(main())
