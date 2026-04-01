# AGENTS.md

## Architecture Overview
This project is a smart home MQTT bridge that controls a Go-e electric vehicle charger based on real-time data from (multiple) PV inverters and battery systems. It subscribes to MQTT topics for grid consumption, battery state-of-charge (SOC), and PV power, calculates optimal charging parameters with configurable offsets, and publishes commands to the charger via MQTT or HTTP API.

Key components:
- **mqtt_runner.py**: Async main script handling MQTT communication and periodic charger updates.
- **R_W_mqtt_client class**: Manages MQTT client, caches incoming data, computes outputs (pGrid, pAkku, pPv), and publishes to charger.
- **base_logging/**: Centralized logging to rotating files in `logs/` directory.
- **config/config.yaml**: YAML configuration for MQTT broker, charger IP, offsets, and scaling factors.

Data flow: MQTT input topics → cache → periodic calculation (every `send_interval` seconds) → publish to charger API.

## Configuration Patterns
- Load config via `load_config()` from `config/config.yaml` (or `config_docker/` for containerized runs).
- API selection: Defaults to MQTT if `output_topic` set, falls back to HTTP if `charger.ip` provided.
- Battery SOC offsets: Sorted dict (e.g., `{50: 4000, 99: 1000}`) applies highest offset for SOC below limit.
- Scaling factors: Adjust battery power for charging/discharging losses (e.g., `charging: 0.9`).

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

## Communication Patterns
- MQTT: TLS-enabled (port 8883, cert from `config/ca.crt`), subscribes to `input_topics`, publishes JSON to `output_topic`.
- HTTP: Direct API calls to charger IP (e.g., `http://192.168.33.49/api/set?ids={"pGrid": 5000}`).
- Periodic sending: Async loop in `periodic_sender()` using `asyncio.sleep(send_interval)`.

## Developer Workflows
- **Run locally**: `python mqtt_runner.py` (uses `config/config.yaml`).
- **Docker run**: `docker run` with volume mounts for `config_docker/` and `logs/`, CMD defaults to `mqtt_runner.py`.
- **Debugging**: Check `logs/logfile_Go-e.log` for INFO-level logs; no console output by default.
- **Charger restart**: Enabled via `restart_charger_on_reconnect: true` for MQTT disconnections.
- **Non-async version**: Use `mqtt_runner_wo_asyncio.py` for environments without asyncio support.

## Key Files
- `mqtt_runner.py`: Core logic and async handling.
- `config/config.yaml`: All runtime settings.
- `base_logging/base_logging.py`: Logging setup (RotatingFileHandler, no console).
- `requirements.txt`: paho-mqtt, PyYAML, urllib3.</content>

