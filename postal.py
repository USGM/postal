"""
Front-end for the Postal Library.
"""


class Postal:
    def __init__(self, configuration_dict):
        self.carriers = {carrier.name: carrier
                         for carrier in configuration_dict['enabled_carriers']}
        carrier_configs = configuration_dict['carrier_inits']
        for key, value in self.carriers.items():
            self.carriers[key] = value(
                postal_configuration=configuration_dict,
                **carrier_configs[key])

    def options(self, package):
        for carrier in self.carriers.values():
            for service in carrier.get_services(package):
                yield service