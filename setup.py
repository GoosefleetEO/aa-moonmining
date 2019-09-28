# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
from moonplanner import __version__

install_requires = [
    'django-bootstrap-form',    
    'allianceauth-evesde'
]

testing_extras = [

]

setup(
    name='aa-moonplanner',
    version=__version__,
    author='Col Crunch',
    author_email='it-team@serin.space',
    description='An app to deal with moooon!',
    install_requires=install_requires,
    extras_require={
        'testing': testing_extras,
        ':python_version=="3.4"': ['typing'],
    },
    python_requires='~=3.4',
    license='GPLv3',
    packages=find_packages(),
    url='https://gitlab.com/colcrunch/aa-moonplanner',
    zip_safe=False,
    include_package_data=True,
)
