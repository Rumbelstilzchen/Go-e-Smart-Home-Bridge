import asyncio
import logging
from base_logging.base_logging import set_logger
import json
import os
import paho.mqtt.client as mqtt
import signal
from datetime import datetime
import urllib3
import yaml
import time


set_logger('logfile_Go-e.log')
logger = logging.getLogger(__name__)
logger.info('First Log')

class R_W_mqtt_client:
    def __init__(self, configuration):
        self.config = configuration
        self.mqtt_client = self.setup_mqtt_client(self.config['MQTT'])
        self.cache = {}
        self.output = {}
        self.mqtt_client.loop_start()
        self.running = True
        self.shutdown_event = asyncio.Event()
        self.goe_restart_needed = False
        #self.bat_SOC_charge_offset = self.config['charger'].get('bat_SOC_charge_offset', {})
        self.bat_SOC_charge_offset = {key: abs(value) for key, value in sorted(self.config['charger'].get('bat_SOC_charge_offset', {}).items())}
        self.general_charge_offset = self.config['charger'].get('general_charge_offset', 0)
        self.bat_scaling_factor = {
            'charging': 1.0,
            'discharging': 1.0
        }
        self.charger_ip = self.config['charger'].get('ip', None)
        self.send_interval = self.config['charger'].get("send_interval", 5)
        self.output_topic = self.config['MQTT'].get("output_topic", None)
        API = self.config['charger'].get('API', 'http').lower()

        if self.charger_ip is None and self.output_topic is None:
            logger.error("Neither charger IP nor MQTT output topic provided in config. Both APIs will not work. Exiting.")
            raise ValueError("Invalid configuration: No API can be used.")

        if API not in ['http', 'mqtt']:
            logger.warning(f"Unsupported API type: {API}. Defaulting to HTTP.")
            API = 'http'
        if self.charger_ip is None and API == 'http':
            logger.warning("Charger IP not provided in config. HTTP API will not work. Fallback to mqtt")
            API = 'mqtt'
        if self.output_topic is None and API == 'mqtt':
            logger.warning("Outgoing topic not provided in mqtt config. MQTT will not work. Fallback to http")
            API = 'http'
        self.bat_scaling_factor.update(self.config['charger'].get('bat_scaling_factor', {}))
        self.restart_charger_on_reconnect=self.config['charger'].get('restart_charger_on_reconnect', False)

        publish_methods={
            'mqtt': self.publish_mqtt,
            'http': self.publish_http
        }
        self.http_pool = None
        if API=='http':
            self.http_pool = urllib3.PoolManager()
            if self.restart_charger_on_reconnect:
                self.restart_charger_on_reconnect = False
                logger.info('In case of http api a restart of charger after restart of mqtt broker is not needed and deactivated')
        self.publish_method = publish_methods[API]


    def setup_mqtt_client(self, mqtt_conf):
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_conf["client_id"],
                             protocol=mqtt.MQTTv311, clean_session=False)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        client.reconnect_delay_set(min_delay=1, max_delay=32)
        client.username_pw_set(mqtt_conf["user"], mqtt_conf["password"])
        if "cert_file" in mqtt_conf:
            client.tls_set(os.path.join(os.path.dirname(__file__), "config", mqtt_conf["cert_file"]))
        client.connect(mqtt_conf["broker_ip"], mqtt_conf["broker_port"], 60)

        return client

    def _on_connect(self, client, userdata, flags, rc, properties):
        logger.info(f"Connected: {rc}")
        if self.goe_restart_needed and self.restart_charger_on_reconnect and self.charger_ip is not None:
            logger.info('restarting goe charger')
            url = rf'http://{self.charger_ip}/api/set?rst=1'
            # call url
            response = json.loads(
                urllib3.PoolManager().request(
                    "GET",
                    url,
                ).data.decode("utf-8")
            )
            time.sleep(30)
            if response['rst']:
                self.goe_restart_needed = False
                logger.info('restarting goe charger - finished')
        for topic in self.config['MQTT']["input_topics"]:
            client.subscribe(topic, 0)
            logger.info(f"Subscribed to {topic}")

    def _on_message(self, client, userdata, msg):
        try:
            current_data = json.loads(msg.payload.decode("utf-8"))
            self.cache.update(current_data)
            # print(current_data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in message handler: {e}")

    def _on_disconnect(self, client, userdata, flags, rc,properties):
        if rc != 0:
            logger.warning(f"Unexpected disconnection: {rc}")
            self.goe_restart_needed = True
            # Automatischer Reconnect durch paho-mqtt

    def shutdown(self, signum=None, frame=None):
        self.running = False
        self.mqtt_client.loop_stop()
        # time.sleep(self.config['MQTT']['send_interval'] + 1)  # Warten, bis der Sender-Task sicher beendet ist
        self.mqtt_client.disconnect()
        self.shutdown_event.set()

    def publish_mqtt(self, data):
        self.mqtt_client.publish(self.output_topic, json.dumps(data))

    def publish_http(self, data):
        url = rf'http://{self.charger_ip}/api/set?ids={json.dumps(data)}'
        # call url
        response = json.loads(
            self.http_pool.request(
                "GET",
                url,
            ).data.decode("utf-8")
        )
        if not response.get('ids', False):
            logger.error(f"Failed to publish data via HTTP")

    async def periodic_sender(self, ):
        """Sendet alle 5 Sekunden die letzten Werte aus dem Cache."""
        await asyncio.sleep(20)
        while self.running:
            # calculate offset by BatSOC
            soc = self.cache.get("BatStateOfCharge", 0)
            bat_offset = 0
            offset =self.general_charge_offset
            for soc_limit in self.bat_SOC_charge_offset:
                if soc < soc_limit:
                    bat_offset = self.bat_SOC_charge_offset[soc_limit]
                    break
            #print(datetime.now())
            self.output["pGrid"] = offset + self.cache.get("AktHomeConsumptionGrid", 5000) - self.cache.get("EinspeisenPower", 0)
            self.output["pAkku"] = (self.cache.get("BatPowerEntLaden", 0) * self.bat_scaling_factor['discharging']) + bat_offset - (self.cache.get("BatPowerLaden", 0) * self.bat_scaling_factor['charging'] )
            self.output["pPv"] = self.cache.get("dcPowerPV", 0)

            self.publish_method(self.output)

            #print(self.output)
            # for topic, value in output.items():
            #     client.publish(f"{base_topic}/{topic}", value)
            #     print(f"\t[SEND] {topic}: {value}")
            await asyncio.sleep(self.send_interval)
        logger.info('sender finished')


# ------------------------------
# MAIN
# ------------------------------

async def main():
    configuration = load_config()
    mqtt_class = R_W_mqtt_client(configuration)
    signal.signal(signal.SIGTERM, mqtt_class.shutdown)
    signal.signal(signal.SIGINT, mqtt_class.shutdown)

    # Tasks starten
    sender_task = asyncio.create_task(mqtt_class.periodic_sender())
    shutdown_task = asyncio.create_task(mqtt_class.shutdown_event.wait())
    # Warten auf Shutdown oder Task-Ende
    await asyncio.wait([sender_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)
    logger.info("Shutting down gracefully")

    # # Async Tasks starten
    # await asyncio.gather(
    #     mqtt_class.periodic_sender()
    # )

def load_config(config_filename="config.yaml"):
    """
    Load YAML configuration from the config directory.

    Args:
        config_filename (str): Name of the configuration file (default: config.yaml)

    Returns:
        dict: Configuration dictionary
    """
    config_dir = os.path.join(os.path.dirname(__file__), "config")
    config_path = os.path.join(config_dir, config_filename)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config

if __name__ == "__main__":

    # signal.signal(signal.SIGTERM, self.exit_monitoring)
    asyncio.run(main())
