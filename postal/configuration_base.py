from carriers.dhl import DHLApi
from carriers.fedex import FedExApi
from carriers.ups import UPSApi
from carriers.usps import USPSApi
from carriers.aramex import AramexApi

base_postal_configuration = {
    'timeout': None,

    # Any carriers you don't want to include should be removed from this list.
    # Any extra carriers you create or import should be added to this list.
    'enabled_carriers': [USPSApi, FedExApi, UPSApi, DHLApi, USPSApi, AramexApi],
    # On occasion, Postal will need to tell a carrier what currency to use
    # when getting a rate or other request. Pick the standard abbreviation
    # for the currency you want used as per ISO-4217.
    # http://en.wikipedia.org/wiki/ISO_4217
    'default_currency': 'USD',

    # The Tax ID of your shipping organization.
    'tax_id': '',

    # A bytestring containing the logo of your organization for commercial
    # invoices. Opening a .jpg file and doing a read() on it would get you the
    # desired string here.
    # This can be overwritten on a per-request basis by setting the extra_param
    # ci_shipper_logo.
    'ci_shipper_logo': '',

    # A bytestring containing the default shipper's signature. The manager of
    # your warehouse would be the best person to sign this. You may also
    # override this on a per-request basis by setting the extra_param
    # ci_signature.
    'ci_signature': '',

    # The name of the person whose signature is in ci_signature.
    # You may override this in the same manner as you can ci_shipper_logo and
    # ci_signature.
    'ci_signed_by': '',

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
            'meter_number': 0,
            'test': True},


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
            'shipper_number': '',

            # (Optional) Whether UPS makes a separate web request for delivery
            # datetimes when getting rates via Postal.options() or
            # UPSApi.get_services(). Does not affect calling delivery_datetime
            # directly or via a Service object. Defaults to True when not
            # specified.
            'auto_time_in_transit': False},

        # You can register for a USPS API key at
        # https://secure.shippingapis.com/registration/
        # After registering, email their team at
        # uspstechsupport@esecurecare.net And tell them you are using third
        # party software to be allowed to use real-world transactions.

        'USPS': {
            'account_id': 123456,
            'passphrase': 'password',
            # If you have clearance to use IPA labels through a consolidator,
            # set this to True to automatically convert eligible labels into
            # IPA labels.
            'ipa_convert': False,
            'requester_id': 123456,
            'token': 123456}},
            # Like DHL, USPS uses the same credentials for both production and
            # testing.
            # 'test_mode': True}}

        # If account number is specified for aramex, then account pin, country code
        # and entity fields must also be given in the request.
        'Aramex' : {
            'account_country_code': 'US',
            'account_entity': 'TES',
            'account_number': '123456789',
            'account_pin': '123456',
            'username': 'test@usglobalmail.com',
            'password': 'testPassword',
            'test': True

        }
    }

