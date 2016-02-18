#!/usr/bin/env python

import sys
import os
import re

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

PYTHON2_VERSION = (2, 7)
PYTHON3_VERSION = (3, 0)
PYTHON3_MIN = (3, 2)

LOCAL_FOLDER = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_LOC = "/".join((LOCAL_FOLDER, "requirements.txt"))

python2 = False
if PYTHON2_VERSION <= sys.version_info <= PYTHON3_VERSION:
    python2 = True

if not python2 and (sys.version_info < PYTHON3_MIN or
                    sys.version_info < PYTHON2_VERSION):
    raise ValueError("Unsupported Python Version")

# TODO Do something about installing for Python 2.7


def find_requires(requirements_loc):
    with open(requirements_loc) as f:
        reqs = f.read()
        return re.findall('^([^#><=\s]+)', reqs, flags=re.M)

setup(
    name='therapyst',
    version='0.1',
    description='Distributed Node Automation',
    author='Matt Smith',
    author_email='matthew.smith491@gmail.com',
    url='n/a',
    packages=['therapyst'],
    package_dir={'therapyst': 'therapyst'},
    include_package_data=True,
    install_requires=find_requires(REQUIREMENTS_LOC),
    license='MIT License',
    zip_safe=True,
    classifiers=(
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ),
    extras_require={
    },
)
