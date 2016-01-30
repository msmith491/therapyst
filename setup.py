#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

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
    install_requires=['pyzmq', 'simplejson'],
    license='MIT License',
    zip_safe=True,
    use_3to2=True,
    classifiers=(
        'Development Status :: 1 - Planning',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ),
    extras_require={
    },
)
