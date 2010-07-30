#! /usr/bin/env python
""" 
Script for loading the casper_n correlator's FPGAs. 

Author: Jason Manley
Revs:
2010-07-28  JRM Port to corr-0.5.0
2009-07-01  JRM First release
"""
import corr, time, sys, numpy, os, logging

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n',lh.printMessages()
    print "Unexpected error:", sys.exc_info()
    try:
        c.disconnect_all()
    except: pass
    #raise
    exit()

def exit_clean():
    try:
        c.disconnect_all()
    except: pass
    exit()

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('init_corr.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-x', '--xeng', dest='xeng', type='int', default=-1, 
        help='Program this X engine fpga (X engine board, ordering as defined in config file, zero-indexed). Set to -1 for all (default).')
    p.add_option('-f', '--feng', dest='feng', type='int', default=-1, 
        help='Program this F engine fpga (F engine board, ordering as defined in config file, zero-indexed). Set to -1 for all (default).')

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

try:
    lh=corr.log_handlers.DebugLogHandler()
    print 'Loading the configuration file %s...'%args[0],
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.floggers+c.xloggers: logger.setLevel(10)
    print 'done.'

    print ''' Programming the Fengines with %s '''%c.config['bitstream_f']
    print '''      ...and the Xengines with %s.'''%c.config['bitstream_x']


    if (opts.xeng < 0) and (opts.feng<0):
        print('\nProgramming all FPGAs...'),
        sys.stdout.flush()
        c.prog_all()
        print 'done.'

    if opts.xeng>0:
        print('\nProgramming X engine %i (%s)...'%(opts.xeng,c.xsrvs[opts.xeng])),
        sys.stdout.flush()
        c.xfpgas[opts.xeng].progdev(c.config['bitstream_x'])
        print 'done.'

    if opts.feng>0:
        print('\nProgramming F engine %i (%s)...'%(opts.feng,c.fsrvs[opts.feng])),
        sys.stdout.flush()
        c.ffpgas[opts.feng].progdev(c.config['bitstream_f'])
        print 'done.'

    
except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

exit_clean()


