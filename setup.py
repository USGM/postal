from setuptools import setup

setup(
    name='Postal',
    version='0.0.1',
    author='Jonathan Piacenti and Nathan Everitt at US Global Mail',
    author_email='it@usglobalmail.com',
    url='http://www.usglobalmail.com/',
    download_url='https://github.com/USGM/postal',
    description='A simple unified interface for shipping with '
                'multiple carriers',
    license='None',
    install_requires=[
        'suds>=0.4', 'python-money>=0.5', 'PyPDF2>=1.19', 'Pillow>=2.2.1',
        'requests>=2.0.1'],
    packages=[
        'postal', 'postal.carriers', 'postal.tests'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
        'License :: Other/Proprietary License',
        'Topic :: Office/Business :: Financial :: Point-Of-Sale',
        'Topic :: Internet :: WWW/HTTP'])
