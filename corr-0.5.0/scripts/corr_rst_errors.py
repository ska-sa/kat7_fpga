#! /usr/bin/env python
"""Resets the cumulative error counters on all connected servers.

Author: Jason Manley
Revs:
2010-07-26: JRM Port for corr-0.5.0
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
    p.set_usage('rst_errors.py CONFIG_FILE')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.loggers: logger.setLevel(10)
    print 'done.'

    print('\nResetting error counters...'),
    sys.stdout.flush()
    c.rst_cnt()
    print 'done.'

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
exit()
