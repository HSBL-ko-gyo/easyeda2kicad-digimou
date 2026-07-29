from __future__ import annotations

import re

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

# Read version from single source of truth
with open("easyeda2kicad/_version.py", encoding="utf-8") as fh:
    _match = re.search(r'^__version__ = "([^"]+)"', fh.read(), re.MULTILINE)
    if _match is None:
        raise RuntimeError("Cannot find __version__ in _version.py")
    _version = _match.group(1)

setup(
    name="easyeda2kicad",
    description=(
        "Unofficial EasyEDA-to-KiCad converter with exact-MPN LCSC, DigiKey, and"
        " Mouser metadata"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=_version,
    author="uPesy",
    author_email="contact@upesy.com",
    maintainer="Modified-work contributors (see NOTICE)",
    url="https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou",
    project_urls={
        "Code": "https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou",
        "Upstream": "https://github.com/uPesy/easyeda2kicad.py",
        "Issues": "https://github.com/HSBL-ko-gyo/easyeda2kicad-digimou/issues",
    },
    license="AGPL-3.0",
    license_files=["LICENSE", "NOTICE"],
    platforms="any",
    packages=find_packages(exclude=["tests", "utils"]),
    package_dir={"easyeda2kicad": "easyeda2kicad"},
    package_data={"easyeda2kicad": ["schemas/*.json"]},
    entry_points={"console_scripts": ["easyeda2kicad = easyeda2kicad.__main__:main"]},
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "dev": [
            "jsonschema>=4.18,<5",
            "pre-commit>=3.0.0",
        ]
    },
    zip_safe=False,
    keywords="easyeda kicad library conversion lcsc digikey mouser metadata",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
)
