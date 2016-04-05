import os

from setuptools import setup, find_packages


install_requires = open('requirements.txt').read().strip().split()


def get_data_files():
    paths = [
        ['postal', 'carriers', 'templates'],
        ['postal', 'carriers', 'wsdl']]
    file_set = []
    for path in paths:
        path = os.path.join(*path)
        for root, dirs, files in os.walk(path):
            for f in files:
                file_name = os.path.join(root, f)
                file_set.append((root, [file_name]))
    return dict(file_set)

setup(
    name='Postal',
    version='0.0.1',
    author='Jonathan Piacenti and Nathan Everitt at US Global Mail',
    author_email='it@usglobalmail.com',
    url='http://www.usglobalmail.com/',
    download_url='https://github.com/USGM/postal',
    description='A simple unified interface for shipping with '
                'multiple carriers',
    use_2to3=True,
    license='None',
    install_requires=install_requires,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
        'License :: Other/Proprietary License',
        'Topic :: Office/Business :: Financial :: Point-Of-Sale',
        'Topic :: Internet :: WWW/HTTP'])
