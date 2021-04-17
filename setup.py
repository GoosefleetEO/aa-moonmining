import os

from setuptools import find_packages, setup

from moonmining import __version__

# read the contents of your README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="aa-moonmining",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    license="MIT",
    description="Alliance Auth app for tracking moon extractions and scouting new moons.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.com/ErikKalkoken/aa-moonmining",
    author="Erik Kalkoken",
    author_email="kaloken87@gmail.com",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
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
        "allianceauth>=2.8.2",
        "django-bootstrap-form",
        "django-navhelper",
        "allianceauth-app-utils>=1.2",
        "django-eveuniverse>=0.8.0",
        "dataclasses>='0.7';python_version<'3.7'",
    ],
)
