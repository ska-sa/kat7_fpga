#! /usr/bin/env python
""" 
Script for unloading the casper_n correlator's FPGAs. 

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
    p.set_usage('corr_deprog_all.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-m', '--monitor_only', dest='monitor_only', action='store_true', default=False, 
        help='Skip the initialision. ie Only monitor.')
    p.add_option('-r', '--n_retries', dest='n_retries', type='int', default=-1, 
        help='Number of times to try and sync the system before giving up. Set to -1 for infinity. Default: -1')

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()
try:
    print 'Loading the configuration file %s...'%args[0],
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in (c.floggers + c.xloggers): logger.setLevel(10)
    print 'done.'

    print('\nDeprogramming all FPGAs...'),
    sys.stdout.flush()
    c.deprog_all()
    print 'done.'

#    lh.printMessages()

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

exit_clean()


