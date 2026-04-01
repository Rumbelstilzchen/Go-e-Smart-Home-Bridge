# Go-e Smart Home Bridge

This project is a smart home MQTT bridge that controls a Go-e electric vehicle charger based on real-time data from (multiple) PV inverters and battery systems. It subscribes to MQTT topics for grid consumption, battery state-of-charge (SOC), and PV power, calculates optimal charging parameters with configurable offsets, and publishes commands to the charger via MQTT or HTTP API.

## Architecture Overview

Key components:
- **mqtt_runner.py**: Async main script handling MQTT communication and periodic charger updates.
- **R_W_mqtt_client class**: Manages MQTT client, caches incoming data, computes outputs (pGrid, pAkku, pPv), and publishes to charger.
- **base_logging/**: Centralized logging to rotating files in `logs/` directory.
- **config/config.yaml**: YAML configuration for MQTT broker, charger IP, offsets, and scaling factors.

Data flow: MQTT input topics → cache → periodic calculation (every `send_interval` seconds) → publish to charger API.

## Installation

1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt`
3. Configure the settings in `config/config.yaml` (see Configuration section).

For Docker:
- Build the image: `docker build -t go-e-bridge .`
- Run with volumes: `docker run -v /path/to/config_docker:/app/config_docker -v /path/to/logs:/app/logs go-e-bridge`

**Data Sources**: For collecting and publishing MQTT data from devices like Kostal Piko BA and Elgris systems, use the companion repository: [https://github.com/Rumbelstilzchen/Monitoring](https://github.com/Rumbelstilzchen/Monitoring).

## Configuration

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
