#!/usr/bin/env python

from setuptools import setup
setup(name='koreana-bot',
      version='1.1.2',
      author='Ian Naval',
      author_email='ian@everquote.com',
      description='Koreana bot',
      include_package_data=True,
      zip_safe=False,
      packages=['koreana_bot'],
      license='Proprietary',
      install_requires=[
          'slacker',
          'slacksocket',
          'arrow',
          'pandas',
          'fuzzywuzzy',
          'python-levenshtein',
          'pyyaml',
      ])
