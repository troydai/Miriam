#!/usr/bin/env python3

from distutils.core import setup


def get_version():
    with open('miriam/__init__.py', 'r', encoding='utf-8') as f:
        import re

        m = re.search(r'__version__\s*=\s*[\'"](.+?)[\'"]', f.read())
        if not m:
            raise ValueError('Could not find __version__ in miriam/__init__.py')

        if not m.group(1):
            raise ValueError('Failed to parse version from miriam/__init__.py')

        return m.group(1)


VERSION = get_version()

CLASSIFIERS = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.6',
    'License :: OSI Approved :: MIT License',
    'Topic :: Software Development :: Quality Assurance',
    'Topic :: Software Development :: Testing'
]

DEPENDENCIES = [
    'azure-batch>=3.0.0',
    'azure-storage>=0.34.3',
    'pyyaml',
    'requests',
    'tabulate'
    # 'pyodbc==3.1.1',
]

setup(name='Miriam',
      version=VERSION,
      description='Execute test in Azure Batch',
      author='Troy Dai',
      author_email='troy.dai@outlook.com',
      url='https://github.com/troydai/miriam',
      packages=['miriam'],
      classifiers=CLASSIFIERS,
      install_requires=DEPENDENCIES,
      scripts=['mir'])
