"""
Front-end for the Postal Library.
"""
from copy import copy
from multiprocessing.pool import ThreadPool
import sys
from .exceptions import PostalError, NotSupportedError
from carriers import Carrier
from configuration_base import base_postal_configuration


class Postal:
    def __init__(self, configuration_dict):
        """
        configuration_dict:{
            'enabled_carriers' -> [Carrier, ...],
            'default_currency' -> string:len=3 = currency code, like 'USD',
            'company_name' -> string,
            'carrier_inits' -> {
                string = name of carrier class without trailing 'Api' ->
                    kwargs:dict = arguments for each carrier's constructor,
                ...
            },
            'shipper_address' -> data.Address
        }
        """
        # Give carriers a back reference to the main postal object.
        configuration_dict['postal'] = self

        self.carriers = {carrier.name: carrier
                         for carrier in configuration_dict['enabled_carriers']}
        carrier_configs = configuration_dict['carrier_inits']
        for name, carrier in self.carriers.items():
            try:
                self.carriers[name] = carrier(
                    postal_configuration=configuration_dict,
                    **carrier_configs[name])
            except:
                print 'Error while constructing carrier ' + str(name)
                print 'with these args: ' + str(carrier_configs[name])
                raise

    def options(self, request):
        """
        Gets all service options from all carriers.

        returns:

        {
            carrier:carriers.Carrier -> {
                'services' -> dict|None= result of carrier.get_services()
                                         or None if unsuccessful,
                'error' -> Exception|None= the problem that occurred
                                           or None if successful
            },
            ... = all loaded carriers represented exactly once
        }
        """
        if not request.packages:
            raise NotSupportedError('No packages in shipment.')
        for i, package in enumerate(request.packages, 1):
            if package.length < 0 or package.width < 0 or package.height < 0:
                if len(request.packages) == 1:
                    raise NotSupportedError('The dimensions of that package '
                                            'are invalid.')
                raise NotSupportedError('The dimensions of package #%s are '
                                        'invalid.' % i)

        thread_pool = ThreadPool(processes=len(self.carriers))
        # To Do
        served_carriers = get_served_country(request.destination.country.alpha2)

        result = dict(thread_pool.map(
            _task, [(carrier, request) for carrier in self.carriers.values()]))
        if result:
            thread_pool.terminate()
            thread_pool.join()
            return result

    def get_all_services(self):
        """
        Get all service options from all carriers.
        """
        for carrier in self.carriers.values():
            for service in carrier.get_all_services():
                yield service

    def get_service(self, carrier_name, service_id):
        if carrier_name not in self.carriers:
            raise PostalError(
                "A carrier named '%s' does not exist." % carrier_name)
        return self.carriers[carrier_name].get_service(service_id)

    def get_package_type(self, carrier_name, code):
        if carrier_name:
            return self.carriers[carrier_name].get_package_type(code)
        else:
            return Carrier.generic_packaging_table[code]

    def get_all_package_types(self):
        """
        Returns all types of containers supported by all carriers.
        """
        for package_type in Carrier.get_generic_package_types():
            yield package_type
        for carrier in self.carriers.values():
            for package_type in carrier.get_all_package_types(generics=False):
                yield package_type

    def without(self, *args):
        """
        Creates and returns a shallow copy of this Postal instance except with
        its carriers table missing the carriers named by the specified
        argument list. For example, calling postal_instance.without('UPS')
        creates a new postal object with all previous carriers except UPS.
        """
        result = copy(self)
        result.carriers = copy(self.carriers)
        for arg in args:
            result.carriers.pop(arg, None)
        return result


def _task(arg_list):

    carrier, request = arg_list
    data_dict = {'services': None, 'error': None}
    try:
        data_dict['services'] = carrier.get_services(request)
    except Exception as err:
        if not hasattr(err, 'traceback'):
            err.traceback = sys.exc_info()[2]
        data_dict['error'] = err

    return carrier, data_dict

def get_served_country(country):
    countries = {
        'AF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AX':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AQ':['USPS', 'FedEx', 'UPS', 'DHL', 'Aramex'],
        'AG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BB':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BJ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BQ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CX':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DJ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'EC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'EG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GQ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ER':['USPS', 'FedEx', 'UPS', 'DHL'],
        'EE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ET':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FJ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'DE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GP':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'HU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ID':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IQ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'IT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'JM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'JP':['USPS', 'FedEx', 'UPS', 'DHL'],
        'JE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'JO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KP':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LB':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ML':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MQ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'YT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MX':['USPS', 'FedEx', 'UPS', 'DHL'],
        'FM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ME':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NP':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MP':['USPS', 'FedEx', 'UPS', 'DHL'],
        'NO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'OM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'QA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'RE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'RO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'RU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'RW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'BL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'KN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'MF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'PM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'WS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ST':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'RS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SX':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SB':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ZA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ES':['USPS', 'FedEx', 'UPS', 'DHL'],
        'LK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SD':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SS':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SJ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'CH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'SY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TW':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TJ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TL':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TK':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TO':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TT':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TR':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TC':['USPS', 'FedEx', 'UPS', 'DHL'],
        'TV':['USPS', 'FedEx', 'UPS', 'DHL'],
        'UG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'UA':['USPS', 'FedEx', 'UPS', 'DHL'],
        'AE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'GB':['USPS', 'FedEx', 'UPS', 'DHL'],
        'US':['USPS', 'FedEx', 'UPS', 'DHL'],
        'UM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'UY':['USPS', 'FedEx', 'UPS', 'DHL'],
        'UZ':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VU':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VN':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VG':['USPS', 'FedEx', 'UPS', 'DHL'],
        'VI':['USPS', 'FedEx', 'UPS', 'DHL'],
        'WF':['USPS', 'FedEx', 'UPS', 'DHL'],
        'EH':['USPS', 'FedEx', 'UPS', 'DHL'],
        'YE':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ZM':['USPS', 'FedEx', 'UPS', 'DHL'],
        'ZW':['USPS', 'FedEx', 'UPS', 'DHL']
    }

    return countries[country]