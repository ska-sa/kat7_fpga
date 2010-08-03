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
    author = 'Aaron Parsons and Jason Manley',
    author_email = 'aparsons at astron.berkeley.edu, jason_manley at hotmail.com',
    url = '',
    package_dir = {'corr':'src'},
    packages = ['corr'],
    ext_modules = [
        Extension('corr.rx',
            globdir('src/rx/',
                ['*.cpp','*.c']),
            include_dirs = [numpy.get_include(), 'src/rx/include'],
            libraries=['rt'],
        )
    ],
    scripts=glob.glob('scripts/*'),
)

