#! /usr/bin/env python
"""(Re)Issues SPEAD metadata and data descriptors so that receivers will be able to interpret the data.
"""
import corr, time, sys, numpy, os, logging

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n',lh.printMessages()
    print "Unexpected error:", sys.exc_info()
    try:
        c.disconnect_all()
    except: pass
    raise
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
    p.add_option('-v', '--verbose', dest='verbose',action='store_true', default=False,
        help='Be verbose about errors.')

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.floggers: logger.setLevel(10)
    print 'done.'

    print ''' Issuing static metadata...''',
    sys.stdout.flush()
    c.spead_static_meta_issue()
    print 'SPEAD packet sent.'

    print ''' Issuing timing metadata...''',
    sys.stdout.flush()
    c.spead_time_meta_issue()
    print 'SPEAD packet sent.'

    print ''' Issuing eq metadata...''',
    sys.stdout.flush()
    c.spead_eq_meta_issue()
    print 'SPEAD packet sent.'

    print ''' Issuing data descriptors...''',
    sys.stdout.flush()
    c.spead_data_descriptor_issue()
    print 'SPEAD packet sent.'

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
exit()
