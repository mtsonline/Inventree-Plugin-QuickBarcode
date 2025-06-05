import os
import requests
import logging
import urllib3

#from common.models import InvenTreeSetting
from plugin import InvenTreePlugin
from plugin.mixins import EventMixin, SettingsMixin
from django.apps import apps

logger = logging.getLogger('inventree')

class QuickBarcode(SettingsMixin, EventMixin, InvenTreePlugin):
    NAME = "Quick Barcode"
    SLUG = "quickbarcode"
    TITLE = "Quick Barcode Linker"
    DESCRIPTION = "Automatically links IPN and serial as external barcode to parts and stockitems"
    VERSION = "2.2"
    AUTHOR = "Martin Thomas Schrott <www.mtsonline.at>"

    SETTINGS = {
        'ENABLE_PARTS': {
            'name': 'Enable for Parts',
            'description': 'Enable barcode linking for parts (uses IPN)',
            'validator': bool,
            'default': True,
        },
        'ENABLE_STOCK': {
            'name': 'Enable for StockItems',
            'description': 'Enable barcode linking for stock items (uses serial number)',
            'validator': bool,
            'default': True,
        },
        'VALIDATE_SSL': {
            'name': 'Validate SSL certs',
            'description': 'Enable SSL cert validation (only disable for local secure connections e.g. selfsigned certs on the same host)',
            'validator': bool,
            'default': True,
        },
        'UNLINK_OTHERS': {
            'name': 'unlink other barcodes',
            'description': 'unlink other barcodes from this part',
            'validator': bool,
            'default': False,
        },
        'LOG_LEVEL': {
            'name': 'log level',
            'description': 'Select log level',
            'choices': [('info','Info (only shows informational messages, warnings and errors)'),('warning', 'Warn (only shows warnings and errors)'),('debug','Debug (show all debugging messages)')],
            'default': 'warning',
            'validator': str,
        },
        'API_KEY': {
            'name': 'Your API key',
            'description': 'Your Inventree API key to link barcodes (may also be set in .env for docker setups. restart needed!)',
            'validator': str,
        },
        'API_URL': {
            'name': 'Your Inventree site url',
            'description': 'Your Inventree site url to link barcodes (may also be set in .env for docker setups. restart needed!)',
            'validator': str,
        }
    }

    def get_event_handlers(self):
        return {
            "plugins_loaded": self.load_settings,
            "part_part.saved": self.process_part_part_saved,
            "part_part.deleted": self.process_part_part_deleted,
            "stock_stockitem.created": self.process_stock_stockitem_saved,
            "stock_stockitem.saved": self.process_stock_stockitem_saved,
        }

#    # not available in 0.17.13 can be used instead of event in future
#    def plugin_ready(self):
#        self.load_settings()
#        logger.debug(f"plugin is ready - loading settings...")

    def load_settings(self, event):
        level = self.get_setting("LOG_LEVEL")
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.debug(f"logging started with level {level}")

        if self.get_setting("API_KEY"):
            API_KEY = self.get_setting("API_KEY")
            os.environ["INVENTREE_API_TOKEN"] = API_KEY
            logger.debug(f"api token found in settings: {API_KEY}")
        if self.get_setting("API_URL"):
            API_URL = self.get_setting("API_URL")
            os.environ["INVENTREE_SITE_URL"] = API_URL
            logger.debug(f"site url found in settings: {API_URL}")

    def process_event(self, event, *args, **kwargs):
        logger.debug(f"📦 Event empfangen: {event}, kwargs={kwargs}")

        handler = self.get_event_handlers().get(event)
        if handler:
            try:
                handler(event, *args, **kwargs)
                logger.debug(f"📦 verarbeite event: {event}, kwargs={kwargs} in function {handler}")
            except Exception as e:
                logger.error(f"Fehler beim Verarbeiten von Event '{event}': {e}")

    def process_part_part_saved(self, event, *args, **kwargs):
        if not self.get_setting("ENABLE_PARTS"):
            return
        Part = apps.get_model("part", "Part")
        part_id = kwargs.get("id")
        if not part_id:
            return

        try:
            part = Part.objects.get(id=part_id)
        except Part.DoesNotExist:
            logger.warning(f"⚠️ Part mit ID {part_id} existiert nicht mehr.")
            return

        ipn = getattr(part, "IPN", None)
        if not ipn:
            logger.warning(f"⚠️ Kein IPN für Part {part_id} vorhanden – keine Verlinkung.")
            return

        api_token = os.getenv("INVENTREE_API_TOKEN")
        logger.debug(f"API-TOKEN: {api_token}")
        logger.warning(f"API-TOKEN: {api_token}")

        site_url = os.getenv("INVENTREE_SITE_URL")
        if not api_token or not site_url:
            logger.error("❌ API-TOKEN oder SITE-URL nicht gesetzt.")
            return

        headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
        }
        verify_cert = self.get_setting("VALIDATE_SSL")
        if not self.get_setting("VALIDATE_SSL"):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.debug("insecure warnings disabled") 

        # Aktuelle Barcodes abrufen
        lookup_url = f"{site_url}/api/barcode/?part={part_id}"
        response = requests.get(lookup_url, headers=headers, verify=verify_cert)
        current_barcodes = response.json() if response.ok else []

        existing = [b for b in current_barcodes if b.get("barcode_data") == ipn]
        others = [b for b in current_barcodes if b.get("barcode_data") != ipn]

        if existing:
            logger.debug(f"🔁 Barcode '{ipn}' ist bereits mit Part {part_id} verlinkt.")
            return

        # Andere Barcodes entfernen
        if self.get_setting("UNLINK_OTHERS"):
            for barcode in others:
                unlink_url = f"{site_url}/api/barcode/unlink/"
                payload = {"barcode": barcode["barcode_data"]}
                resp = requests.post(unlink_url, headers=headers, json=payload, verify=verify_cert)
                if resp.status_code in [200, 201]:
                    logger.info(f"🧹 Entfernt alten Barcode '{barcode['barcode_data']}' von Part {part_id}.")
                else:
                    logger.warning(f"⚠️ Fehler beim Entfernen von Barcode '{barcode['barcode_data']}': {resp.status_code}")

        # IPN als neuen Barcode verlinken
        link_url = f"{site_url}/api/barcode/link/"
        payload = {"barcode": ipn, "part": part.pk}
        resp = requests.post(link_url, headers=headers, json=payload, verify=verify_cert)

        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code in [200, 201] and "success" in data:
            logger.info(f"✅ Barcode '{ipn}' erfolgreich mit Part {part.pk} verlinkt.")
        else:
            logger.error(f"❌ Fehler beim Verlinken: Status {resp.status_code} - {resp.text}")

    def process_part_part_deleted(self, event, *args, **kwargs):
        if not self.get_setting("ENABLE_PARTS"):
            return
        part_id = kwargs.get("id")
        if not part_id:
            return

        api_token = os.getenv("INVENTREE_API_TOKEN")
        logger.debug(f"API-TOKEN: {api_token}")
        site_url = os.getenv("INVENTREE_SITE_URL")
        if not api_token or not site_url:
            logger.error("❌ API-TOKEN oder SITE-URL nicht gesetzt.")
            return

        headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
        }
        verify_cert = self.get_setting("VALIDATE_SSL")
        if not self.get_setting("VALIDATE_SSL"):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.debug("insecure warnings disabled") 

        lookup_url = f"{site_url}/api/barcode/?part={part_id}"
        response = requests.get(lookup_url, headers=headers, verify=verify_cert)
        if not response.ok:
            logger.warning(f"⚠️ Barcode-Lookup fehlgeschlagen: {response.status_code}")
            return

        barcodes = response.json()
        for barcode in barcodes:
            payload = {"barcode": barcode["barcode_data"]}
            unlink_url = f"{site_url}/api/barcode/unlink/"
            resp = requests.post(unlink_url, headers=headers, json=payload, verify=verify_cert)
            if resp.status_code in [200, 201]:
                logger.info(f"🗑️ Barcode '{barcode['barcode_data']}' erfolgreich entfernt (Part {part_id} gelöscht).")
            else:
                logger.warning(f"⚠️ Fehler beim Entfernen von Barcode '{barcode['barcode_data']}': {resp.status_code}")

    def process_stock_stockitem_saved(self, event, *args, **kwargs):
        if not self.get_setting("ENABLE_STOCK"):
            return

        StockItem = apps.get_model("stock", "StockItem")
        item_id = kwargs.get("id")
        if not item_id:
            return

        try:
            item = StockItem.objects.get(id=item_id)
        except StockItem.DoesNotExist:
            logger.warning(f"⚠️ StockItem mit ID {item_id} existiert nicht mehr.")
            return

        serial = getattr(item, "serial", None)
        if not serial:
            logger.warning(f"⚠️ Keine Seriennummer für StockItem {item_id} vorhanden – keine Verlinkung.")
            return

        api_token = os.getenv("INVENTREE_API_TOKEN")
        logger.debug(f"API-TOKEN: {api_token}")
        site_url = os.getenv("INVENTREE_SITE_URL")
        if not api_token or not site_url:
            logger.error("❌ API-TOKEN oder SITE-URL nicht gesetzt.")
            return

        headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
        }
        verify_cert = self.get_setting("VALIDATE_SSL")
        if not self.get_setting("VALIDATE_SSL"):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.debug("insecure warnings disabled") 

        # Aktuelle Barcodes abrufen
        lookup_url = f"{site_url}/api/barcode/?stockitem={item_id}"
        response = requests.get(lookup_url, headers=headers, verify=verify_cert)
        current_barcodes = response.json() if response.ok else []

        existing = [b for b in current_barcodes if b.get("barcode_data") == serial]
        others = [b for b in current_barcodes if b.get("barcode_data") != serial]

        if existing:
            logger.debug(f"🔁 Barcode '{serial}' ist bereits mit StockItem {item_id} verlinkt.")
            return

        # Andere Barcodes entfernen
        if self.get_setting("UNLINK_OTHERS"):
            for barcode in others:
                unlink_url = f"{site_url}/api/barcode/unlink/"
                payload = {"barcode": barcode["barcode_data"]}
                resp = requests.post(unlink_url, headers=headers, json=payload, verify=verify_cert)
                if resp.status_code in [200, 201]:
                    logger.info(f"🧹 Entfernt alten Barcode '{barcode['barcode_data']}' von StockItem {item_id}.")
                else:
                    logger.warning(f"⚠️ Fehler beim Entfernen von Barcode '{barcode['barcode_data']}': {resp.status_code}")

        # Seriennummer als neuen Barcode verlinken
        link_url = f"{site_url}/api/barcode/link/"
        payload = {"barcode": serial, "stockitem": item.pk}
        resp = requests.post(link_url, headers=headers, json=payload, verify=verify_cert)

        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code in [200, 201] and "success" in data:
            logger.info(f"✅ Barcode '{serial}' erfolgreich mit StockItem {item.pk} verlinkt.")
        else:
            logger.error(f"❌ Fehler beim Verlinken von StockItem: Status {resp.status_code} - {resp.text}")
