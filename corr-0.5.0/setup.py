from distutils.core import setup, Extension

import os, glob, numpy, sys

__version__ = '0.5.0'

def indir(dir, files): return [dir+f for f in files]
def globdir(dir, files):
    rv = []
    for f in files: rv += glob.glob(dir+f)
    return rv

setup(name = 'corr',
    version = __version__,
    description = 'Interfaces to CASPER correlators',
    long_description = 'Interfaces to CASPER correlators.',
    license = 'GPL',
    author = 'Jason Manley',
    author_email = 'jason_manley at hotmail.com',
    url = '',
    package_dir = {'corr':'src'},
    packages = ['corr'],
    scripts=glob.glob('scripts/*'),
)

