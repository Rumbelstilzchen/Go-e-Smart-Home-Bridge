# Go-e Smart Home Bridge

This project is a smart home MQTT bridge that controls a Go-e electric vehicle charger based on real-time data from (multiple) PV inverters and battery systems. It subscribes to MQTT topics for grid consumption, battery state-of-charge (SOC), and PV power, calculates optimal charging parameters with configurable offsets, and publishes commands to the charger via MQTT or HTTP API.

## Architecture Overview

## 🎨 Features

### Web-Oberfläche

✅ **Live-Werte** (aktualisiert alle 10 Sekunden)
- Ladeleistung in Watt
- Phasenmodus (1-phasig / 3-phasig)
- Energiequelle (Hausakku / Grid)

✅ **Betriebsmodus**
- BASIC: Normales Laden
- ECO: Sparmodus

✅ **Temporäre Ladepriorität**
- Datum + Endzeit wählen
- 15-Minuten-Schritte
- Auto-Aufhebung nach Ablauf
- Status-Anzeige mit Countdown

✅ **Sicherheit**
- Benutzername/Passwort-Authentifizierung
- Session-Management
- Protected API-Endpoints

✅ **REverse Proxy**
empfohlen für sichere Bereitstellung (z.B. Nginx mit TLS)
```
location / {
    proxy_pass http://docker_container:8080;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Host $host;
}
```

### MQTT-Integration

- Bidirektionale Kommunikation mit MQTT-Broker
- Status-Abonnement für Live-Werte
- Command-Publishing für Charger-Befehle
- TLS/SSL Support für sichere Übertragung

---

## 📂 Projektstruktur

Load config via `load_config()` from `config/config.yaml` (or `config_docker/` for containerized runs).

API selection: Defaults to MQTT if `output_topic` set, falls back to HTTP if `charger.ip` provided.

Battery SOC offsets: Sorted dict applies highest offset for SOC below limit.

Scaling factors: Adjust battery power for charging/discharging losses.

**Note**: The cache keys (e.g., "AktHomeConsumptionGrid", "BatPowerEntLaden") in the calculation logic must be adapted to match the JSON keys in your MQTT topic payloads. The provided code is tailored to specific MQTT data structures (e.g., from Kostal Piko BA and Elgris systems). Modify the `periodic_sender` method in `mqtt_runner.py` to use the correct keys for your setup.

Example config snippet:
```yaml
charger:
  bat_SOC_charge_offset:
    50: 4000  # Reserve 4kW until SOC 50%
    99: 1000  # Reserve 1kW until SOC 99%
  general_charge_offset: 50
  bat_scaling_factor:
    charging: 0.9
    discharging: 0.9
```

## Usage

- **Run locally**: `python mqtt_runner.py` (uses `config/config.yaml`).
- **Docker run**: `docker run` with volume mounts for `config_docker/` and `logs/`, CMD defaults to `mqtt_runner.py`.
- **Debugging**: Check `logs/logfile_Go-e.log` for INFO-level logs; no console output by default.
- **Charger restart**: Enabled via `restart_charger_on_reconnect: true` for MQTT disconnections.
- **Non-async version**: Use `mqtt_runner_wo_asyncio.py` for environments without asyncio support.

## Key Files

- `mqtt_runner.py`: Core logic and async handling.
- `config/config.yaml`: All runtime settings.
- `base_logging/base_logging.py`: Logging setup (RotatingFileHandler, no console).
- `requirements.txt`: paho-mqtt, PyYAML, urllib3.

## Disclaimer

This software is provided "as is" without any warranties or guarantees. The authors and contributors are not responsible for any damages, losses, or issues arising from the use of this software. Use at your own risk. Ensure compliance with local laws and regulations regarding smart home devices and energy management.
