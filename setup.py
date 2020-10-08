import os
from setuptools import find_packages, setup

from moonplanner import __version__


# read the contents of your README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="aa-moonplanner",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    license="GPLv3",
    description="App for planning moon mining with Auth",
    long_description=long_description,
    url="https://gitlab.com/ErikKalkoken/aa-moonplanner",
    author="Erik Kalkoken",
    author_email="kaloken87@gmail.com",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.0",
        "Framework :: Django :: 3.1",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    python_requires="~=3.6",
    install_requires=[
        "allianceauth",
        "django-bootstrap-form",
        "django-navhelper",
        "allianceauth-evesde",
    ],
    extras_require={"testing": []},
)
