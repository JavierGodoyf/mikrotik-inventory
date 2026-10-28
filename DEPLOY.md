# Despliegue

Tres formas de montarlo en otro equipo. La app es la misma; cambia cómo se arranca
y dónde vive `data/`.

| Opción | Cuándo | Arranque |
|---|---|---|
| Docker (Linux, Windows, macOS) | Cualquier equipo con Docker; la opción más portable | `docker compose up -d` |
| Nativo + systemd | Servidor Linux sin Docker | `systemctl start mikrotik-inventory` |
| Nativo en macOS | Tu Mac u otro Mac | `./run.sh` desde Terminal |
| Nativo en Windows | Windows sin Docker | `.\run.ps1` |

En todas, el panel escucha en `127.0.0.1:8000` y no se expone a internet.

---

## 1. Docker (recomendada)

Requisitos: Docker con Compose v2.

```sh
# copia el proyecto al equipo destino (sin .venv ni data)
rsync -a --exclude .venv --exclude data --exclude backups \
  ~/mikrotik-inventory/ usuario@servidor:/opt/mikrotik-inventory/

cd /opt/mikrotik-inventory
docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:8000/healthz
```

- La base de datos y la clave de cifrado viven en el volumen `mtik-data`.
- El contenedor corre como usuario sin privilegios (uid 1000) y con
  `no-new-privileges`.
- `TZ` se define en `docker-compose.yml` (`Europe/Madrid` por defecto).
- Uvicorn escucha `0.0.0.0` **dentro** del contenedor, pero el puerto del host
  está atado a `127.0.0.1`, así que no queda expuesto.

Ver desde tu portátil sin abrir puertos:

```sh
ssh -N -L 8000:127.0.0.1:8000 usuario@servidor
# y abre http://127.0.0.1:8000
```

Actualizar:

```sh
rsync -a --exclude .venv --exclude data --exclude backups ./ usuario@servidor:/opt/mikrotik-inventory/
ssh usuario@servidor 'cd /opt/mikrotik-inventory && docker compose up -d --build'
```

Backup y restauración:

```sh
mkdir -p backups
docker compose cp panel:/app/data/. backups/
# restaurar
docker compose cp backups/devices.db panel:/app/data/devices.db
docker compose cp backups/secret.key panel:/app/data/secret.key
docker compose restart panel
```

---

## 2. Nativo en Linux + systemd

```sh
sudo useradd --system --home /opt/mikrotik-inventory --shell /usr/sbin/nologin mtik
sudo mkdir -p /opt/mikrotik-inventory
sudo rsync -a --exclude .venv --exclude data --exclude backups \
  ~/mikrotik-inventory/ /opt/mikrotik-inventory/
sudo chown -R mtik:mtik /opt/mikrotik-inventory

sudo -u mtik /opt/mikrotik-inventory/install.sh

sudo cp /opt/mikrotik-inventory/deploy/mikrotik-inventory.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mikrotik-inventory
sudo systemctl status mikrotik-inventory --no-pager
```

La unidad ya fija `MTIK_BASE_DIR`, `WorkingDirectory` y permisos de escritura
solo sobre `data/`. Si instalas en otra ruta, edita las tres referencias a
`/opt/mikrotik-inventory`.

Logs: `journalctl -u mikrotik-inventory -f`.

---

## 3. Nativo en macOS

```sh
./install.sh
./run.sh
```

`run.sh` arranca el panel en primer plano. **Hazlo desde Terminal.app** y acepta el
permiso de *Red local*; si lo lanzas desde otro proceso sin permiso, los routers
de la LAN darán `No route to host` (errno 65). Comprobación rápida:

```sh
./.venv/bin/mikrotik-inventory doctor --host 192.168.1.1 --port 8728
```

Un LaunchAgent de macOS hereda el mismo problema de permisos, así que para uso
desatendido en un Mac es más fiable Docker Desktop (el contenedor corre en una VM
Linux y no pasa por TCC).

---

## 4. Windows

### Docker Desktop (recomendado)

1. Instala Docker Desktop con backend WSL2.
2. Copia el proyecto (sin `.venv` ni `data`) y ejecuta:

   ```powershell
   docker compose up -d --build
   ```

3. Abre <http://127.0.0.1:8000>.
4. No hay que tocar el Firewall de Windows: el puerto está atado a `127.0.0.1` y el
   tráfico hacia los routers es saliente.

Dos avisos:

- Si el equipo usa VPN (WireGuard, OpenVPN, Tailscale), el contenedor sale por la ruta
  de WSL2. Si un router de la LAN deja de responder, prueba a desactivar la VPN o usa
  la IP pública del equipo.
- Backup: `docker compose cp panel:/app/data/. backups\`.

### Nativo con PowerShell

Requisitos: Python 3.10+ desde python.org, marcando *Add python.exe to PATH*.

```powershell
.\install.ps1
.\run.ps1
```

Windows Defender Firewall solo pregunta por tráfico entrante; el panel no lo necesita.
No existe el problema de permisos de red local de macOS.

### Permisos de `data/` en Linux

Si cambias el volumen nombrado por un bind mount (`./data:/app/data`), el contenedor
corre con uid 1000 y necesitarás `sudo chown -R 1000:1000 data`. Con el volumen
nombrado no hay que hacer nada.

---

## Migrar datos entre equipos

La base de datos guarda las contraseñas **cifradas** con `data/secret.key`.
Copia siempre los dos juntos:

```sh
tar czf mikrotik-backup.tgz data/devices.db data/secret.key
```

En el destino, déjalos en `data/` y con permisos restringidos:

```sh
mkdir -p data
tar xzf mikrotik-backup.tgz
chmod 700 data
chmod 600 data/secret.key data/devices.db
```

Si pierdes `secret.key`, el panel sigue funcionando pero no puede descifrar las
contraseñas: hay que volver a introducirlas (Editar → contraseña).

Con Docker, el equivalente es `docker compose cp panel:/app/data ./backups/` y
luego copiar esos dos archivos al volumen del equipo nuevo.

---

## Configuración

Se lee de variables de entorno con prefijo `MTIK_` y del archivo `.env` que esté en
el directorio de trabajo (`MTIK_BASE_DIR`). Lo más habitual:

| Variable | Por defecto | Nota |
|---|---|---|
| `MTIK_DB_URL` | `sqlite:///<cwd>/data/devices.db` | |
| `MTIK_KEY_FILE` | `<cwd>/data/secret.key` | |
| `MTIK_CHECK_INTERVAL_HOURS` | `6` | |
| `MTIK_LAN_TIMEOUT` / `MTIK_PUBLIC_TIMEOUT` | `8` / `15` | segundos |
| `MTIK_MAX_CONCURRENCY` | `8` | chequeos en paralelo |
| `MTIK_SCHEDULER_ENABLED` | `true` | |
| `MTIK_HOST` / `MTIK_PORT` | `127.0.0.1` / `8000` | |

No uses `--workers > 1`: el scheduler vive en el proceso y se duplicaría.

---

## Checklist tras instalar

```sh
curl -s http://127.0.0.1:8000/healthz
./.venv/bin/mikrotik-inventory latest
./.venv/bin/mikrotik-inventory doctor --host <router> --port 8728
```

1. Usuario de solo lectura creado en el router (`policy=read,api`).
2. `doctor` devuelve OK para el router.
3. Equipo añadido y primera comprobación con estado distinto de "Inalcanzable".
4. Backup de `devices.db` + `secret.key` guardado fuera del equipo.
