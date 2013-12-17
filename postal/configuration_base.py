from carriers.dhl import DHLApi
from carriers.fedex import FedExApi
from carriers.ups import UPSApi
from carriers.usps import USPSApi


base_postal_configuration = {
    'timeout': None,

    # Any carriers you don't want to include should be removed from this list.
    # Any extra carriers you create or import should be added to this list.
    'enabled_carriers': [USPSApi, FedExApi, UPSApi, DHLApi, USPSApi],
    # On occasion, Postal will need to tell a carrier what currency to use
    # when getting a rate or other request. Pick the standard abbreviation
    # for the currency you want used as per ISO-4217.
    # http://en.wikipedia.org/wiki/ISO_4217
    'default_currency': 'USD',

    # The following are options for setting up the default carriers. Each
    # carrier's options are paired with their key, which is their name
    # property.
    'carrier_inits': {
        # You can sign up for a FedEx API key here:
        # https://www.fedex.com/us/developer/web-services/process.html?tab=tab2
        # From there, you will need to contact FedEx about getting a production
        # key to use this software to make real shipments and rate quotes at
        # your account rate.
        'FedEx': {
            # Your FedEx API Key.
            'key': '',
            # Your FedEx Account Number
            'account_number': 0,
            'password': '',
            # Every device using FedEx's API is expected to have its own meter
            # number. You should have received one when signing up to use the
            # API, and can ask for an additional one if needed.
            'meter_number': 0},


        # You can request an API key from DHL at:
        # http://www.dhl-usa.com/en/express/resource_center/
        # integrated_shipping_solutions/request_xml_toolkit.html
        'DHL': {
            'account_number': 0,
            # The site_id is what DHL calls your username.
            'site_id': '',
            'password': '',
            # Set this to False in order to use DHL in production. DHL uses the
            # same credentials for both production and test.
            'test_mode': True,
            # DHL has several region codes. 'AM' is for the Americas.
            # 'AP-EM' supports countries in Asia, Africa, Australia and
            # Pacific. 'EU' handles European countries. You must use the
            # region code you're running Postal from.
            'region_code': 'AM',
            'company_name': ''},

        # You can find instructions for getting an account with UPS and an API
        # key at https://www.ups.com/upsdeveloperkit
        'UPS': {
            # The username and password should be the same as for your website
            # login for UPS.
            'username': '',
            'password': '',
            # The access licence number is given when you sign up to use UPS's
            # API.
            'access_license_number': '',
            # Your account number with UPS. You should be able to find this by
            # logging into their website.
            'shipper_number': ''},

        # You can register for a USPS API key at
        # https://secure.shippingapis.com/registration/
        # After registering, email their team at
        # uspstechsupport@esecurecare.net And tell them you are using third
        # party software to be allowed to use real-world transactions.
        'USPS': {
            'user_id': '',
            'password': '',
            # Like DHL, USPS uses the same credentials for both production and
            # testing.
            'test_mode': True}}}