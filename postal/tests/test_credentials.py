
import os

from .vault_loader import import_vault_secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

carrier_inits = {
    'UPS':
        { 'test' : True },
        
    'Aramex': {
         'test' : True,
         'account_country_code': 'US',
    },
    'FedEx': {
        'test': True,
    },
    'DHL': {
        'test_mode': True,
        'company_name': 'US Global Mail',
    }
}
carrier_inits = import_vault_secrets(carrier_inits,
                                     os.environ.get('VAULT_AUTH_CONF'),
                                     BASE_DIR + '/vault_map.yml')

