# Bot Discord - Alertes Vinted

Ce bot surveille une (ou plusieurs) recherche(s) Vinted et envoie un ping `@role`
dans un salon Discord dès qu'une nouvelle annonce correspondant à tes critères
(marque, taille, prix, mots-clés...) apparaît.

## 1. Créer le bot Discord

1. Va sur https://discord.com/developers/applications et clique sur **New Application**.
2. Onglet **Bot** → **Add Bot**.
3. Copie le **Token** (bouton "Reset Token" si besoin) : tu en auras besoin pour `config.json`.
   Ne le partage jamais publiquement.
4. Onglet **OAuth2 → URL Generator** :
   - Scopes : `bot`
   - Bot Permissions : `Send Messages`, `Embed Links`, `Mention Everyone` (nécessaire
     pour que le bot puisse ping un rôle même s'il n'est pas "mentionnable" par tout le monde)
5. Ouvre l'URL générée, choisis ton serveur et invite le bot.

## 2. Récupérer les IDs Discord

Active le **Mode développeur** (Discord → Paramètres → Avancés → Mode développeur),
puis clic droit sur :
- le salon où tu veux recevoir les alertes → **Copier l'ID du salon**
- le rôle à ping (Paramètres du serveur → Rôles) → **Copier l'ID du rôle**

## 3. Préparer ta recherche Vinted

1. Va sur https://www.vinted.fr et fais une recherche avec tous les filtres voulus
   (mot-clé, marque, taille, prix min/max, état...).
2. Copie l'URL complète dans la barre d'adresse (elle contient tous les filtres).

## 4. Configurer le bot

```bash
cp config.example.json config.json
```

Édite `config.json` :

```json
{
  "discord_token": "TON_TOKEN_BOT",
  "check_interval_seconds": 60,
  "destinations": [
    {
      "name": "Serveur des potes",
      "channel_id": 123456789012345678,
      "role_id": 123456789012345678,
      "searches": [
        {
          "name": "Jordan 4 taille 42",
          "url": "https://www.vinted.fr/catalog?search_text=jordan+4&size_ids[]=207&price_to=150&order=newest_first"
        }
      ]
    },
    {
      "name": "Serveur perso",
      "channel_id": 987654321098765432,
      "role_id": 987654321098765432,
      "searches": [
        {
          "name": "Nike Tech Fleece",
          "url": "https://www.vinted.fr/catalog?search_text=nike+tech+fleece&order=newest_first"
        }
      ]
    }
  ]
}
```

Le bot tourne avec un seul token, mais peut être présent sur plusieurs serveurs :
chaque entrée de `destinations` correspond à un salon + rôle à ping (généralement
sur un serveur différent), avec sa **propre liste de recherches** dans `searches`.
Un même serveur peut avoir plusieurs recherches ; tu peux aussi avoir plusieurs
`destinations` sur le même serveur (des salons différents) si tu veux séparer
les alertes par catégorie.

N'oublie pas d'inviter le bot (même lien d'invitation OAuth2, étape 1) sur
chacun des serveurs concernés.

`check_interval_seconds` : fréquence de vérification (60s est un bon compromis ;
ne descends pas trop bas pour éviter d'être bloqué par Vinted).

## 5. Installer et lancer

### Option A — directement avec Python

```bash
pip install -r requirements.txt
python bot.py
```

### Option B — avec Docker (recommandé sur Raspberry Pi)

1. Installe Docker sur le Pi (si ce n'est pas déjà fait) :

   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   ```

   Déconnecte-toi puis reconnecte-toi (ou redémarre le Pi) pour que le groupe
   `docker` prenne effet sans avoir besoin de `sudo`.

2. Copie le dossier du bot sur le Pi (via `git clone`, `scp`, clé USB...), en
   t'assurant que `config.json` est bien rempli (voir étape 4 ci-dessus).

3. Crée le fichier de suivi des annonces vues (vide au départ) :

   ```bash
   cd vinteddiscordbot
   touch seen_items.json
   echo '{}' > seen_items.json
   ```

   (nécessaire car Docker refuse de monter en volume un fichier qui n'existe pas)

4. Build et lance le conteneur :

   ```bash
   docker compose up -d --build
   ```

5. Vérifie que ça tourne :

   ```bash
   docker compose logs -f
   ```

   (`Ctrl+C` pour quitter les logs sans arrêter le bot)

Le conteneur redémarre automatiquement en cas de plantage ou de redémarrage
du Raspberry Pi (`restart: unless-stopped`).

**Pour mettre à jour le bot** après avoir modifié `bot.py` :

```bash
docker compose up -d --build
```

**Pour l'arrêter :**

```bash
docker compose down
```

L'image `python:3.12-slim` est multi-architecture : la même commande fonctionne
que ton Pi tourne en 32 bits (armv7) ou 64 bits (arm64) — Docker choisit
automatiquement la bonne variante.

Au premier lancement pour une recherche donnée, le bot enregistre les annonces
déjà en ligne sans les notifier (pour éviter un spam massif au démarrage).
Ensuite, seules les **nouvelles** annonces déclenchent un ping.

## Notes

- Vinted n'a pas d'API publique officielle : ce bot utilise l'API interne que le
  site web utilise lui-même. Elle peut changer sans préavis, ou bloquer les
  requêtes trop fréquentes — reste raisonnable sur `check_interval_seconds`.
- Le fichier `seen_items.json` garde en mémoire les annonces déjà vues (par
  recherche) pour ne pas re-notifier après un redémarrage.
- Usage personnel uniquement : respecte les conditions d'utilisation de Vinted.
