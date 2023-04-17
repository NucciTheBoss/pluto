#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from setuptools import setup, find_packages


setup(
    name="pluto",
    version="0.1.0",
    description="A swiss-army knife for managing HPC clusters built with Ubuntu.",
    author="Jason C. Nucciarone",
    author_email="jason.nucciarone@canonical.com",
    license="GPL-3.0",
    python_requires=">=3.8",
    packages=find_packages(
        where="src",
        include=["pluto"],
    ),
    package_dir={"": "src"},
    entry_points={"console_scripts": ["pluto=pluto.main:pluto"]},
    install_requires=[
        "craft-cli==1.2.0",
        "juju==3.1.0.1"
    ],
    keywords=[
        "hpc",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Environment :: Console",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
