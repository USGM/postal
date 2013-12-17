from ..configuration_base import base_postal_configuration

from test_credentials import (
    dhl_credentials, fedex_credentials, ups_credentials, usps_credentials)

config = base_postal_configuration
config['carrier_inits']['UPS'] = ups_credentials
config['carrier_inits']['FedEx'] = fedex_credentials
config['carrier_inits']['DHL'] = dhl_credentials
config['carrier_inits']['USPS'] = usps_credentials