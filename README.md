# Twin Eagles Grill for Home Assistant

Unofficial Home Assistant integration for Twin Eagles pellet grills (tested on a 36" built-in, model `TE01V4`).

The official app talks to a cloud service; this integration uses the same API, reverse engineered from the
Android app. It is **read-only** for now: it can't start, stop or change the temperature of your grill.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/AndyGerlicher/ha-twin-eagles`, category **Integration**.
2. Install **Twin Eagles Grill**, then restart Home Assistant.
3. Settings → Devices & services → **Add integration** → Twin Eagles Grill.
4. Sign in with your Twin Eagles app account and pick your grill. Online grills are listed first; old
   registrations (e.g. after a controller swap) show as offline.

## Entities

| Entity | Notes |
|---|---|
| Pit temperature, Set temperature | °F from the grill, converted to your unit system |
| Probe 1–3 temperature | `unknown` when the probe is unplugged |
| Probe 1–3 target | Disabled by default |
| Mode | `smoke`, `smoke_plus`, `sear`, `charcoal` |
| Power, Fan, Ignitor, Auger, Light | Binary sensors |
| Alarm | On when the grill reports alarms; list in the `alarms` attribute |
| Online, Last update | Diagnostics |

Status is polled every 30 seconds.

## Design

`custom_components/twin_eagles/api/` is a Home Assistant independent client library. `GrillClient` defines the
interface and `CloudClient` implements it; everything above that layer only sees `GrillStatus`. A local
polling client can be added later by implementing `GrillClient` and wiring it up in `create_client()` in
`__init__.py`.

## Development

```
pip install pytest-homeassistant-custom-component
pytest
```

`te_status.py` is a standalone CLI that prints the current status. Put `TE_USER` and `TE_PASS` in `.env`.

## Disclaimer

Not affiliated with or endorsed by Twin Eagles or Dometic. Use at your own risk.
