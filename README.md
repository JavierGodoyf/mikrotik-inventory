# mikrotik.inventory

Panel local para saber si tus MikroTik están en la última versión que **realmente**
pueden ejecutar. Solo lee: no instala nada, no reinicia nada y no cambia configuración.

- Inventario de equipos (LAN e IP pública).
- Comprobación de `/system resource`, `/system package update` y `/system routerboard`.
- Comparación con la última versión publicada por MikroTik para la rama y el canal.
- Aviso separado de **RouterBOOT** desfasado (eso no lo actualiza el paquete de RouterOS).
- Detección de equipos v6 sin ruta a v7 y de saltos que requieren revisión manual.
- Histórico de comprobaciones, export CSV y JSON.
- Descubrimiento en LAN por MNDP (sin credenciales).
- Scheduler propio cada N horas.

## Requisitos

- Python 3.10+ si lo instalas en nativo (`brew install python@3.12` en macOS).
- O Docker, que es la vía más portable (Linux, Windows y macOS).
- Acceso de red a los routers: 8728 (api) en LAN o 8729 (api-ssl) en públicos.

## Puesta en marcha

```sh
cd ~/mikrotik-inventory
./install.sh     # crea .venv, instala el paquete y la base de datos
./run.sh         # arranca en http://127.0.0.1:8000
```

Para montarlo en otro equipo (Docker, systemd, macOS, Windows) y para migrar los
datos, mira **[DEPLOY.md](DEPLOY.md)** o el resumen de abajo.

### Si sale `No route to host` (errno 65)

No es el router ni las credenciales: es macOS bloqueando el acceso a la red local para
el proceso que ejecuta el panel. Al proceso padre de OpenCode no se le puede pedir el
permiso, así que arranca el servidor desde Terminal.app:

```sh
cd ~/mikrotik-inventory
./run.sh
```

macOS pedirá permiso para *encontrar dispositivos en la red local*; acéptalo. Si no
aparece el aviso, actívalo en *Ajustes → Privacidad y seguridad → Red local*.

Para comprobarlo antes de nada:

```sh
.venv/bin/python -m app.cli doctor --host 192.168.1.1 --port 8728
```

Debe decir `Internet: OK` y `192.168.1.1:8728: OK`. Si el segundo falla con
`No route to host`, sigue siendo el permiso.

## Docker, Linux y Windows

La app es la misma en todas partes; cambia cómo se arranca y dónde vive `data/`.
El panel escucha siempre en `127.0.0.1:8000` (nunca en `0.0.0.0` del host).

| Sistema | Cómo | Arranque |
|---|---|---|
| Linux (servidor/NAS) | Docker | `docker compose up -d --build` |
| Windows 10/11 | Docker Desktop (WSL2) | `docker compose up -d --build` |
| macOS | Docker Desktop, o nativo | `docker compose up -d --build` / `./run.sh` |
| Linux sin Docker | Nativo + systemd | `systemctl start mikrotik-inventory` |
| Windows sin Docker | Nativo + PowerShell | `.\install.ps1` y `.\run.ps1` |

### Docker (recomendado)

```sh
rsync -a --exclude .venv --exclude data --exclude backups \
  ~/mikrotik-inventory/ usuario@servidor:/opt/mikrotik-inventory/

cd /opt/mikrotik-inventory
docker compose up -d --build
docker compose ps
curl -s http://127.0.0.1:8000/healthz
```

La imagen es Linux (`python:3.12-slim`) y por tanto funciona igual en Linux, en
Windows con Docker Desktop/WSL2 y en macOS. Detalles:

- Usuario no-root (uid 1000), `no-new-privileges` y healthcheck contra `/healthz`.
- `devices.db` y `secret.key` viven en el volumen nombrado `mtik-data`.
- `MTIK_HOST=0.0.0.0` solo **dentro** del contenedor; el puerto del host está atado
  a `127.0.0.1`, así que no queda expuesto.
- Actualizar: `docker compose up -d --build`. Logs: `docker compose logs -f`.
- Backup: `mkdir -p backups && docker compose cp panel:/app/data/. backups/`.

Si prefieres bind mount (`./data:/app/data`) en vez del volumen nombrado, el
contenedor escribe como uid 1000: `sudo chown -R 1000:1000 data`.

### Windows nativo

Requiere Python 3.10+ desde python.org, marcando *Add python.exe to PATH*:

```powershell
.\install.ps1
.\run.ps1
```

No existe el problema de permiso de *Red local* de macOS, y el Firewall de Windows
solo pregunta por tráfico entrante, que el panel no necesita.

### Avisos que solo aparecen fuera de tu Mac

- **Descubrimiento MNDP**: usa broadcast de capa 2 y **no funciona dentro de un
  contenedor** (red bridge). Añade los equipos por IP; el chequeo normal sí va.
- **VPN en el host**: con WireGuard/OpenVPN/Tailscale el contenedor sale por la ruta
  de WSL2/Docker y puede perder la LAN. Si un router deja de responder, desactiva la
  VPN o usa su IP pública.
- **Un solo worker**: el scheduler vive en el proceso, así que no uses
  `--workers > 1` ni escales la réplica del contenedor.

## Usuario en el router

En cada MikroTik, crea un usuario de solo lectura. No hace falta `write`:

```routeros
/user group add name=monitor policy=read,api
/user add name=panel group=monitor password=<aleatoria> address=<tu IP>
```

Restringe el servicio a tu origen:

```routeros
# LAN
/ip service set api address=192.168.1.0/24

# IP pública: mejor api-ssl y solo tu IP
/ip service set api disabled=yes
/ip service set api-ssl address=<tu.ip.publica>/32
```

El panel nunca lanza `check-for-updates` por defecto (puede requerir más permisos);
la versión objetivo la calcula desde `upgrade.mikrotik.com` y, si el router ya la
reporta, la usa como confirmación.

### TLS en api-ssl

RouterOS suele usar un certificado autofirmado. En el formulario del equipo deja
**Verificar certificado TLS** desmarcado salvo que hayas instalado un certificado
válido. En LAN usa `api` (8728); en públicos, `api-ssl` (8729), porque el login
de la API viaja en claro.

## Uso

Interfaz web: añadir, editar, comprobar uno o todos, histórico y CSV.

CLI:

```sh
.venv/bin/python -m app.cli add --name "hAP oficina" --host 192.168.1.1 --username panel
.venv/bin/python -m app.cli list
.venv/bin/python -m app.cli check              # todos
.venv/bin/python -m app.cli check --id 1
.venv/bin/python -m app.cli latest             # lo que publica MikroTik
.venv/bin/python -m app.cli discover           # MNDP en la LAN
.venv/bin/python -m app.cli doctor             # red local + internet
```

## Estados

| Estado | Significado |
|---|---|
| `Actualizado` | Instalada = objetivo del canal. |
| `Actualizable` | Hay una versión más nueva en la rama actual. |
| `Revisión manual` | Salto v6 → v7 (o poco flash): ventana de mantenimiento / netinstall. |
| `Sin ruta a v7` | La arquitectura no tiene paquete 7.x; 6.49.x es su techo. |
| `Adelantado` | Tiene algo más nuevo que el canal (rc/beta/testing). |
| `Inalcanzable` | No se pudo conectar o autenticar. |
| `Desconocido` | No se pudo determinar el objetivo (sin caché ni respuesta). |

La versión objetivo se calcula así: si el equipo es v7, contra el canal elegido
(`stable` o `long-term`); si es v6 y su arquitectura tiene paquete 7.x, contra v7;
si no, contra 6.49.x. Una versión más nueva reportada por el propio router gana
sobre la de `upgrade.mikrotik.com`.

## Endpoints

- `GET /` dashboard
- `GET /devices/{id}` detalle e histórico
- `GET /discover` MNDP
- `GET /api/devices` JSON
- `GET /report.csv` export
- `GET /healthz` estado + versiones en caché

## Seguridad

- Credenciales cifradas con Fernet; clave en `data/secret.key` (chmod 600) o `MTIK_KEY_FILE`.
- El panel no tiene autenticación propia porque solo escucha en `127.0.0.1`.
  No lo expongas a internet; si lo necesitas, ponlo detrás de Tailscale o un proxy con auth.
- Un solo proceso: el scheduler vive dentro de la app (no uses `--workers > 1`).
- Los logs no incluyen contraseñas.

## Tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## Estructura

```
app/
  main.py        FastAPI + vistas
  server.py      entrypoint (mikrotik-panel)
  cli.py         alta, listado, chequeo, descubrimiento
  checker.py     orquesta lectura + evaluación y guarda snapshots
  evaluate.py    reglas de estado
  upstream.py    upgrade.mikrotik.com + caché
  compat.py      arquitecturas v7 y umbral de flash
  versions.py    parseo/comparación de versiones
  mikrotik/      cliente API, collector y MNDP
  templates/     Jinja (empaquetado con el paquete)
  static/        CSS
deploy/          unidad systemd
```

## Limitaciones conocidas

- MNDP no da RouterBOOT ni el canal: para eso hace falta la API.
- Los equipos con 16 MB o menos pueden necesitar netinstall para v7; el panel lo marca
  como revisión manual, no lo automatiza.
- `upgrade.mikrotik.com` no distingue arquitectura; el filtrado fino lo hace el propio
  equipo cuando se le pregunta con `check-for-updates`.
- El panel no actualiza nada. Es intencionado.
