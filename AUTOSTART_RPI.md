# Autostart au boot (Raspberry Pi + Docker Compose)

Ce guide lance automatiquement le bot au demarrage du Raspberry Pi.

## 1) Pre-requis

- Docker et Docker Compose plugin installes.
- Projet present sur le Pi, par exemple dans `/home/pi/crypto.py`.
- Fichier `.env` configure (Telegram, API token, etc.).

## 2) Tester manuellement

Depuis le dossier du projet:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

Verifier la sonde:

```bash
curl -s http://127.0.0.1:8000/health
```

## 3) Activer Docker au boot

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

## 4) Service systemd pour Compose

Creer le fichier `/etc/systemd/system/crypto-bot.service`:

```ini
[Unit]
Description=Crypto Bot Docker Compose
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/pi/crypto.py
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Adapter `WorkingDirectory` si ton chemin est different.

## 5) Activer l'autostart

```bash
sudo systemctl daemon-reload
sudo systemctl enable crypto-bot.service
sudo systemctl start crypto-bot.service
```

## 6) Verification

```bash
systemctl status crypto-bot.service
sudo journalctl -u crypto-bot.service -n 100 --no-pager
docker compose ps
```

## 7) Mises a jour

Apres pull Git:

```bash
cd /home/pi/crypto.py
docker compose up -d --build
```

## Notes production

- Les limites CPU/RAM sont dans `.env` via `BOT_CPU_LIMIT`, `BOT_MEM_LIMIT`, `BOT_MEM_RESERVATION`.
- Les donnees persistantes sont conservees dans le dossier `data/`.
- La timezone locale est `Europe/Paris` (variables `TZ` et `LOCAL_TIMEZONE`).
