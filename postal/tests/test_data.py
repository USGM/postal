from unittest import TestCase

from postal import Address


class TestData(TestCase):
    def test_address_to_primitive(self):
        address = Address(
            street_lines=['test', 'test2', 'test3'],
            city='Houston',
            contact_name='Jim Bob',
            country='US',
            subdivision='TX',
            postal_code='77092',
            phone_number='555-555-5555',
            email='something@example.com',
            residential=False,
        )
        self.assertEqual(
            address.to_primitive(),
            {
                'street_lines': ['test', 'test2', 'test3'],
                'city': 'Houston',
                'contact_name': 'Jim Bob',
                'country': u'US',
                'subdivision': 'TX',
                'postal_code': '77092',
                'phone_number': '555-555-5555',
                'email': 'something@example.com',
                'residential': False
            }
        )
