from copy import deepcopy
import unittest
from base import TestCarrier
from ..carriers.fedex import FedExApi
from ..carriers.base import Carrier
from ..data import Request, Address, Package, Declaration, Shipment
from money import Money


class TestFedEx(TestCarrier, unittest.TestCase):
    carrier_class = FedExApi

    def test_arbitrary_shipment_000(self):
        package = Package(1, 1, 1, 5, self.carrier.get_package_type('FEDEX_BOX'), carrier_conversion=False, declarations=[
            Declaration('SIM Card', Money(45, 'USD'), 'US', 1, insure=True),
            Declaration('ECM Control Module', Money(319, 'USD'), 'US', 1, insure=True),
            Declaration('Book', Money('12.78', 'USD'), 'US', 1, insure=False),
            Declaration('Book', Money('5.39', 'USD'), 'US', 1, insure=False),
            Declaration('Snaps', Money('3.95', 'USD'), 'US', 1, insure=False)
        ], documents_only=False)

        response = self.carrier.get_service('INTERNATIONAL_ECONOMY').ship(Request(
            Address(
                street_lines=['1321 Upland Dr'], city='Houston',
                subdivision='TX', country='US',
                residential=False, contact_name='US Global Mail',
                phone_number='2815968965',
                postal_code='77043'
            ),
            Address(
                contact_name='TEST',
                phone_number='0000000000',
                street_lines=['DO NOT SHIP'],
                city='Merida',
                subdivision='Yuc',
                postal_code='97117',
                country='MX',  # Mexico
                residential=True
            ),
            [package],
            extra_params={'UPS': {'signature': 'Adult'}}
        ))

        self.assertIsInstance(response, dict)
        self.assertIn('shipment', response)
        self.assertIn('price', response)
        self.assertIn('packages', response)
        self.assertIsInstance(response['shipment'], Shipment)
        self.assertIsInstance(response['price'], Money)
        self.assertIsInstance(response['packages'], dict)
        self.assertEqual(len(response['packages']), 1)
        self.assertIn(package, response['packages'])

        package_data = response['packages'][package]
        self.assertIsInstance(package_data, dict)
        self.assertIn('tracking_number', package_data)
        self.assertIn('label', package_data)
        self.assertIsInstance(package_data['tracking_number'], str)
        self.assertIsInstance(package_data['label'], str)

if __name__ == '__main__':
    unittest.main()