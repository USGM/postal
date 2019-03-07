
import os

#from .vault_loader import import_vault_secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

carrier_inits = {
    'UPS':{
        "access_license_number": "ECEE84C37A0D2EA6",
        "auto_time_in_transit": False,
        "password": "Usgm6425",
        "shipper_number": "X5925Y",
        "test": True,
        "username": "usglobalmail"
     },
        
    'Aramex': {
        "account_country_code": "US",
        "account_entity": "ZZZ",
        "account_number": 160922834,
        "account_pin": 216316,
        "password": "Aramex@123",
        "test": True,
        "username": "ashwini.kaklij@silicus.com"
    },
    'FedEx': {
        "account_number": 510087860, 
        "key": "HAEgRZuMszS1yE86", 
        "meter_number":  119095705, 
        "password": "jiEv098STtcf86WpvZJEe2Sup", 
        "test": True
    },
    'DHL': {
        "account_number": 846124225,
        "company_name": "US Global Mail",
        "password": "bH8UcIYuGZ",
        "region_code": "AM", 
        "site_id": "v62_rI2vJGyVD9",
        "test_mode": True
    },
    "USPS": {
        "account_id": 2505571,
        "ipa_convert": True,
        "passphrase": "Lucy in the sky",
        "requester_id": "lusg",
        "test": True
    }, 

}
#carrier_inits = import_vault_secrets(carrier_inits,
#                                     os.environ.get('VAULT_AUTH_CONF'),
#                                     BASE_DIR + '/vault_map.yml')
