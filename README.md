# Twin Eagles Grill for Home Assistant

Unofficial Home Assistant integration for Twin Eagles pellet grills (tested on a 36" built-in, model `TE01V4`).

The official app talks to a cloud service; this integration uses the same API, reverse engineered from the
Android app. It can change the temperature and cooking mode of a grill that is **already running**, but it
deliberately can't start or stop the grill.

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
| Mode | `smoke`, `smoke_plus`, `sear`, `charcoal` |
| Power, Fan, Ignitor, Auger | Binary sensors |
| Alarm | On when the grill reports alarms; list in the `alarms` attribute |
| Online, Last update | Diagnostics |

Status is polled every 20 seconds while the grill is on and every 2 minutes while it is off or offline, so
a grill started from the app or the control panel shows up within 2 minutes. Both intervals can be changed
under the integration's **Configure** button.

### Controls

| Entity | Notes |
|---|---|
| Set temperature (number) | 140–725 °F. Smoke and Smoke Plus only |
| Cooking mode (select) | Smoke, Smoke Plus, Sear. Charcoal is not settable |
| Sear level (select) | Low, Medium, High. Sear mode only |
| Probe 1–3 target (number) | 100–225 °F, the same limits as the app |
| Light (switch) | Works while the grill is off too |

Cooking controls are unavailable while the grill is off or offline, and the client library refuses commands in
that state as well, so nothing can bring an idle grill to life. The light only needs the grill to be online.
There is no start command.

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

See [docs/INVESTIGATION.md](docs/INVESTIGATION.md) for the protocol notes (cloud API, the grill's local
hotspot protocol) and what has been tried toward local-only control.

## Disclaimer

Not affiliated with or endorsed by Twin Eagles or Dometic. Use at your own risk.
