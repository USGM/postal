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
config['carrier_country'] = {'Aramex': ['BH', 'CY', 'EG', 'IR', 'IQ', 'IL', 'JO', 'KW', 'LB', 'OM', 'QA', 'SA', 'SY',
                                        'TR', 'AE', 'YE', 'DZ', 'AO', 'BJ', 'BW', 'BF', 'BI', 'CM', 'CF', 'TD', 'KM',
                                        'CG', 'CD', 'CI', 'DJ', 'GQ', 'ER', 'ET', 'GA', 'GM', 'GH', 'GN', 'GW', 'CV',
                                        'KE', 'LS', 'LR', 'LY', 'MG', 'MW', 'ML', 'MR', 'MU', 'MA', 'MZ', 'NA', 'NE',
                                        'NG', 'RW', 'ST', 'SN', 'SC', 'SL', 'SO', 'ZA', 'SS', 'SD', 'SZ', 'TZ', 'TG',
                                        'TN', 'UG', 'ZM', 'ZW']}

base_path = os.path.split(os.path.abspath(
    inspect.getfile(inspect.currentframe())))[0]
config['ci_shipper_logo'] = open(os.path.join(
    base_path, 'logo.jpg'), 'rb').read()
config['ci_signature'] = open(os.path.join(
    base_path, 'signature.jpg'), 'rb').read()
config['ci_signed_by'] = 'John Smith'