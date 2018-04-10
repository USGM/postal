import os

from setuptools import setup, find_packages

def get_requirements():
    """
    To update the requirements, edit requirements.txt
    """
    with open('requirements.txt', 'r') as f:
        req_lines = f.readlines()
    reqs = []
    for line in req_lines:
        # Avoid adding comments.
        line = line.split('#')[0].strip()
        if line:
            reqs.append(line)
    return reqs


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
    version='0.4.12',
    author='US Global Mail with Silicus Technologies',
    author_email='it@usglobalmail.com',
    url='http://www.usglobalmail.com/',
    download_url='https://github.com/USGM/postal',
    description='A simple unified interface for shipping with multiple carriers',
    license='None',
    install_requires=get_requirements(),
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
        'Topic :: Internet :: WWW/HTTP'
    ]
)
