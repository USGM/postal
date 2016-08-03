import inspect
import os

from postal.configuration_base import base_postal_configuration
from test_credentials import (
    dhl_credentials, fedex_credentials, ups_credentials, usps_credentials, aramex_credentials
)


config = base_postal_configuration
config['carrier_inits']['UPS'] = ups_credentials
config['carrier_inits']['FedEx'] = fedex_credentials
config['carrier_inits']['DHL'] = dhl_credentials
config['carrier_inits']['USPS'] = usps_credentials
config['carrier_inits']['Aramex'] = aramex_credentials

base_path = os.path.split(os.path.abspath(
    inspect.getfile(inspect.currentframe())))[0]
config['ci_shipper_logo'] = open(os.path.join(
    base_path, 'logo.jpg'), 'rb').read()
config['ci_signature'] = open(os.path.join(
    base_path, 'signature.jpg'), 'rb').read()
config['ci_signed_by'] = 'John Smith'