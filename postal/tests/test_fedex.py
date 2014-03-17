import unittest
from base import TestCarrier, test_from, test_to
from ..carriers.fedex import FedExApi
from ..carriers.base import Carrier
from ..data import Request, Address, Package, Declaration, Shipment
from money import Money


class TestFedEx(TestCarrier, unittest.TestCase):
    carrier_class = FedExApi

    def test_arbitrary_shipment_000(self):
        # A more complex shipment for this service to test.
        package_type = self.carrier.get_package_type('FEDEX_BOX')
        declarations = [
            Declaration('SIM Card', Money(45, 'USD'), 'US', 1, insure=True),
            Declaration('ECM Control Module', Money(319, 'USD'), 'US', 1,
                        insure=True),
            Declaration('Book', Money('12.78', 'USD'), 'US', 1, insure=False),
            Declaration('Book', Money('5.39', 'USD'), 'US', 1, insure=False),
            Declaration('Snaps', Money('3.95', 'USD'), 'US', 1, insure=False)]

        package = Package(
            1, 1, 1, 5,
            package_type, declarations=declarations,
            carrier_conversion=False, documents_only=False)

        service = self.carrier.get_service('INTERNATIONAL_ECONOMY')

        test_to_special = Address(
            contact_name='TEST',
            phone_number='0000000000',
            street_lines=['DO NOT SHIP'],
            city='Merida',
            subdivision='Yuc',
            postal_code='97117',
            country='MX',  # Mexico
            residential=True)

        request = Request(Address(**test_from), test_to_special, [package])

        response = service.ship(request)

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

    def test_unicode_characters(self):
        package = Package(
            11, 15, 3, 4, Carrier.GENERIC_PACKAGE, carrier_conversion=False,
            declarations=[
                Declaration('book', Money(45, 'USD'), 'US', 1, insure=False)],
            documents_only=False)

        test_to_special = Address(
            contact_name=u'Commission construction Qu\xe9bec',
            phone_number='0000000000',
            street_lines=['DO NOT SHIP'],
            city='Montreal',
            subdivision='PQ',  # the other abbreviation is QC
            postal_code='H2M0A7',
            country='CA'  # Canada
        )

        request = Request(Address(**test_from), test_to_special, [package])

        self.carrier.get_services(request)

    def test_heavy_domestic_envelope(self):
        package_type = self.carrier.get_package_type('FEDEX_ENVELOPE')
        package = Package(1, 1, 1, 3, package_type=package_type)
        request = Request(Address(**test_from), Address(**test_to), [package])
        response = self.carrier.get_services(request)
        self.assertTrue(response)
        response.keys()[0].ship(request)

if __name__ == '__main__':
    unittest.main()