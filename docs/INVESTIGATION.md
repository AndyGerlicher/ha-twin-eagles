# Protocol notes and local control investigation

Everything learned while reverse engineering the Twin Eagles pellet grill (model `TE01V4`, Android app
2.2.1), including approaches to local-only control that were tried and the ones that are left. Nothing in here
is specific to one grill; identifiers are shown as placeholders.

Placeholders used below:

| Placeholder | Meaning | Where to find it |
|---|---|---|
| `<device id>` | Device identifier, `BGX_TE_` + 16 hex chars | `GET account/devices`, or SETTINGS > DEVICE INFO on the grill |
| `<product key>` | 8 hex char local auth key | SETTINGS > DEVICE INFO > Product Key on the grill |
| `<grill ip>` | Grill's address on the home LAN | Router DHCP leases (hostname is not descriptive) |

## Summary

- The only working interfaces are the **cloud API** (used by this integration) and the **grill's own Wi-Fi
  hotspot**, which is only up during setup.
- The grill reaches the cloud by **polling it over HTTPS every ~4 seconds** and verifies the server certificate,
  so the cloud can't be impersonated locally.
- On the home LAN the grill exposes SSH and three custom TCP ports (12345–12347) whose protocol is unknown.

## Hardware and firmware

- Embedded Linux controller with a Murata Wi-Fi module.
- Services seen: OpenSSH 7.1, rpcbind (111), dnsmasq (53, hotspot only), Apache 2.4.20 + PHP 5.6.18 (80,
  hotspot only), unknown TCP 12345/12346/12347.
- The cloud client is `curl/7.47.1` (seen in its User-Agent).
- Firmware images are GPG encrypted (`bgx_te_<timestamp>.tgz.gpg`); uploaded through the hotspot's
  `upd_firmware.php`.

## The app

The Android app is Ionic/Capacitor (Angular). Readable TypeScript sources are embedded in
`assets/public/main.js.map` (`sourcesContent`), so no decompiler is needed:

```
unzip -o app.apk 'assets/public/main.js.map' -d apk
python3 -c "import json;m=json.load(open('apk/assets/public/main.js.map'));..."  # write each sources[i] to disk
```

Useful files: `services/providers/deviceresourcerequest.ts` (local mode), `services/services/chamber/*`,
`services/services/probes/*`, `services/services/devicearea/wifi/wifi.service.ts`, `devices/deviceonlinelist.ts`.

The app has two modes: **API mode** (cloud) and **local/AP mode** (phone joined to the grill's hotspot).

## Cloud API

Base URL `https://te.bonelessgrills.com/app/`. JSON. Temperatures in °F.

### Auth

`POST account/login` with `{"username": ..., "password": ...}` returns `{"id_token": ...}`. Send it as
`Authorization: Bearer <token>`. Expired tokens return 401/403; log in again.

Other account endpoints in the app: `account`, `account/activate`, `account/preferences`, `account/pushToken`,
`account/reset`, `account/reset/confirm`, `account/devices/{deviceId}` (unregister).

### Devices and status

- `GET account/devices` lists registered grills. `technology` is returned as `PELLETS`.
- `GET {technology}/{deviceId}` returns status. **`technology` must be lowercase** (`pellets/<device id>`),
  otherwise 404.

Status shape (see `tests/fixtures/status_online.json`):

| Field | Notes |
|---|---|
| `lastDeviceUpdate` | ms epoch of the grill's last report; 0 if never |
| `chambers[0].onOff` | Grill running |
| `chambers[0].mode` | `SMOKE`, `SMOKE_PLUS`, `SEAR`, `CHARCOAL` |
| `chambers[0].searMode` | `MIN`, `MED`, `MAX`, `NOSEAR` |
| `chambers[0].probes[0]` | Pit. `targetTemperature` is the set temperature |
| `chambers[0].probes[1..3]` | Meat probes. Unplugged reads **32**; no target is **240** |
| `chambers[0].fan / ignitor / motor / light` | Outputs (`motor` = auger) |
| `chambers[0].currentAlarms` | List of strings. `DEVICE_NOT_FOUND` for an offline/unregistered grill |
| `chambers[0].coolMode / charcoalStarter / rotis / runMode` | Not yet used by the integration |
| `chambers[0].onOffTime` | Run time in ms (assumed) |
| `chambers[0].timers[]`, `chronoOnOff*` | Timer and stopwatch state |
| `probes[n].targetReachedTime`, `min/maxTemperatureAlarm`, `recipe`, `recipeName`, `status`, `type` | Per probe |

An old registration (e.g. after a controller swap) stays in the device list, but its status has
`lastDeviceUpdate: 0` and `DEVICE_NOT_FOUND`.

### Commands

All are `PUT` with no body and parameters in the query string, relative to `{technology}/{deviceId}/`.
Verified live: set temperature. The others are taken from the app.

| Endpoint | Notes |
|---|---|
| `chambers/0/probes/{n}/targetTemperature?targetTemperature=X` | n=0 sets pit temp (140–725 °F, Smoke/Smoke Plus only). n=1..3 probe targets (app allows 100–225; 240 clears) |
| `chambers/0/mode?mode=SMOKE\|SMOKE_PLUS\|SEAR` | |
| `chambers/0/searmode?searmode=MIN\|MED\|MAX` | Sear mode only |
| `chambers/0/light/start`, `/light/stop` | |
| `chambers/0/fan/start`, `/fan/stop` | |
| `chambers/0/rotis/start`, `/rotis/stop` | Rotisserie models |
| `chambers/0/charcoalStarter/start`, `/stop` | |
| `chambers/0/coolMode/stop` | |
| `chambers/0/timer/start?timerOnOffValueSeconds=S&numTimer=0`, `/timer/stop?numTimer=0`, `/timer/reset?...` | |
| `chamber/0/probes/{n}/recipe?foodCode=..&doneness=..` | Note `chamber` (singular) in the app |
| `chambers/0/start`, `chambers/0/stop` | Power. **Deliberately not used by this integration** |

### How the grill talks to the cloud (from a packet capture)

- Every few seconds: DNS lookup of `te.bonelessgrills.com` (A and AAAA), then a fresh HTTPS connection.
- Plain HTTP `GET /device/pellets/clock` (no auth) returns the server time in ms epoch. It is fetched before
  each HTTPS attempt.
- HTTPS (TLS 1.2, SNI `te.bonelessgrills.com`, no client certificate requested): roughly every **4.3 seconds**
  the grill uploads ~2 KB (with `Expect: 100-continue`) and receives a reply of a few hundred bytes to ~2 KB.
  This is presumably the status upload, with pending commands in the reply. Paths and payloads weren't seen
  because the traffic is encrypted.
- Nothing connects into the grill; commands must ride on the replies.

## Local protocol (grill hotspot)

Pressing the top-right control button until the display shows **GRILL WIFI** starts a hotspot, SSID
`BGX-TE_<suffix>`, default password `twineagles` (from the app). The grill is `192.168.0.1`.

Pages: `index.php` (lists nearby networks; device id in a hidden input), `indexform.php` (POST `ssid_id`,
`password`, `token`=account username; sets home Wi-Fi), `upd_firmware.php` (firmware upload),
`device_operations.php` (control).

### `device_operations.php`

`POST` multipart form with `operation`, `clave=<product key>`, `sleep_get_all=500`, plus operation-specific
fields. `GET` returns `ERROR_METHOD: GET`; a missing/wrong key returns `ERROR TK`. Responses can start with a
PHP `strtotime()` timezone warning that must be stripped.

Operations used by the app: `get_all`, `start`, `stop`, `cooldown`, `modo_smoke`, `modo_smoke_plus`,
`modo_sear`, `modo_charcoal`, `modo_charcoal_starter_si/_no`, `modo_charcoal_vent_si/_no`, `on_lights`,
`off_lights`, `consignaReceta` (fields `probe` 1-based, `food`, `doneness`, `targetTemperature` in °C),
`timerCronoSet` / `timerCronoPause` / `timerValueReset` (field `cronoSeconds`).

Only `get_all` was tried.

### `get_all` response

Space separated `name value` pairs. **Temperatures in °C.** Field names are Spanish.

| Field | Meaning |
|---|---|
| `temp(1)`, `consigna(1)` | Pit temperature, set temperature |
| `temp(2..4)`, `consigna(2..4)` | Meat probes 1–3 and targets (`consigna` ≈115.56 °C = 240 °F, i.e. no target) |
| `temp(5..9)`, `consigna(5..9)` | Unused channels |
| `activada_Sonda(n)` | Probe enabled `SI`/`NO` |
| `recetaNomIdx(n)`, `recetaAcabadoIdx(n)` | Recipe / doneness index |
| `out(pellets1/2)` | Auger |
| `out(resist1/2)` | Ignitor |
| `out(fan1/2)` | Fan |
| `out(aux1..3)` | Aux outputs; `aux2` is the light |
| `out(puerta)` | Door: `CERRADA` = closed (**not available from the cloud**) |
| `modoBBQ` | `smoke`, `smoke_plus`, `sear`, `charcoal` |
| `estadoBBQ` | Run state. `parada` = stopped, `parando` = stopping (cooling down); other values not seen |
| `modo_Charcoal_StarterActivado`, `modo_Charcoal_VentActivado`, `modo_Charcoal_VentActivado_LowHigh` | Charcoal mode |
| `timerRunningTime`, `timerCronoStartTime`, `timerCronoSeconds` | Timer |
| `alarma_FaltaPellets` | Low pellets `SI`/`NO` (**not seen in the cloud status**) |
| `alarma_Sonda(2..4)` | Probe alarms |
| `alarma_Timer` | Timer alarm |
| `targetReachedTime(2..4)`, `pelletsReachedTime` | |

## Local-only control: what was tried

| Approach | Result |
|---|---|
| Port scan on the home LAN | 22, 111, 12345, 12346, 12347 open. **Port 80 is not served on the LAN**, so `device_operations.php` is hotspot only |
| Hotspot `get_all` with product key | **Works**. Full status, °C |
| TCP 12347 on the LAN, text lines | `<key> get_all`, `<key>` alone, `<key> get_all 500` → `ERROR OPEN`. Key not first (`get_all <key>`, `TK <key> get_all`, form-encoded) → `ERROR TK`. So the key is checked first, then something called "OPEN" fails. A follow-up line on the same connection got no reply |
| TCP 12345 / 12346 on the LAN | Connection reset on any input tried |
| Keeping the hotspot up | Rebooting always returns to home Wi-Fi mode, even with DHCP refused or wrong Wi-Fi credentials. No automatic AP fallback found. No documented factory reset found |
| Redirecting `te.bonelessgrills.com` (router DNS override) to a local pass-through proxy | The grill resolves and connects, and the plain HTTP clock request works, but every HTTPS connection is dropped right after the handshake with a self-signed certificate. **The grill verifies the server certificate**, so the cloud can't be impersonated |

## Local-only control: not tried

- **Leaving the hotspot on for a long time.** Untested whether a button-activated hotspot stays up until the
  next power cycle. If it does, a device with a second Wi-Fi radio (e.g. a Raspberry Pi near the grill) could
  poll `get_all` with no internet involved, at the cost of re-pressing the button after power loss.
- **More work on port 12347.** Find what "OPEN" means, e.g. an open/session operation before `get_all`, or a
  different framing. No source for this protocol was found in the app (the app never uses these ports), so it
  is blind guessing. Best kept to read-only attempts.
- **Other local operations on the hotspot** (`on_lights` etc.). Expected to work like the app's local mode.
- **SSH.** Credentials unknown; brute forcing was ruled out.
- **Hardware access** (serial console on the controller board) to get root, read the firmware key or add a CA.
  Most invasive; risk of bricking the controller.
- **Asking the manufacturer** about a local API or a persistent AP mode.

## Ideas to improve the cloud integration

- **Poll faster.** Done: 20 s while on, 2 min while off, both configurable. The grill reports every ~4 s, so the active interval
  could go lower.
- **Light switch.** Done (`chambers/0/light/start|stop`). Not yet verified live, including whether it works
  while the grill is off.
- **Timers.** The status has timer and stopwatch state, and the app has start/stop/reset endpoints.
- **More sensors** from fields already in the status: run time (`onOffTime`), cool-down (`coolMode`), probe
  target reached (`targetReachedTime`), recipe name, rotisserie and charcoal starter state.
- **Alarm codes.** Only `DEVICE_NOT_FOUND` has been seen; record others as they happen.
- **Untested live:** mode and sear level commands.

## Tools

- `tools/grill_ap_probe.py`: run while connected to the grill's hotspot (no internet needed). Scans the grill,
  reads banners and samples `get_all`. Results go to `results/` (gitignored).
- `tools/cloud_proxy.py`: logging pass-through proxy for `te.bonelessgrills.com`, used for the DNS redirect test.
  Kept in case a future firmware stops verifying certificates.
- `te_status.py`: prints cloud status from the command line.

Capturing the grill's traffic from a router with SSH (e.g. Firewalla):
`sudo tcpdump -i any -nn -s0 -w /tmp/grill.pcap host <grill ip>`, then power-cycle the grill to capture
startup. On a dnsmasq-based router, a domain can be redirected with `address=/te.bonelessgrills.com/<ip>`.
