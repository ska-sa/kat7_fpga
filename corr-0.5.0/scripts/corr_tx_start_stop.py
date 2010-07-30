#! /usr/bin/env python
"""
Starts UDP packet output on the X engine. Does not do any configuration of the output cores.

Author: Jason Manley\n
Revisions:\n
2010-07-29 PVP Cleanup as part of the move to ROACH F-Engines.\n
2009------ JRM Initial revision.\n
"""
import corr, time, sys, numpy, os, logging

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n', lh.printMessages()
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
    p.set_usage('corr_tx_start.py [options] CONFIG_FILE')
    p.add_option('', '--start', dest='txStart', action='store_true', help='Start UDP packet transmission from the X-engines.')
    p.add_option('', '--stop', dest='txStop', action='store_true', help='Stop UDP packet transmission from the X-engines.')
    p.add_option('-v', '--verbose', dest='verbose',action='store_true', default=False, help='Be verbose about stuff.')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! Exiting.'
        exit()

    if (opts.txStart and opts.txStop):
        print 'Epic fail! --stop or --start, not both.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Creating correlator connections using config file \'%s\'...'%args[0],
    c=corr.corr_functions.Correlator(args[0], lh)
    for s, server in enumerate(c.xsrvs): c.loggers[s].setLevel(10)
    print 'done.'
        
    if opts.txStart:
        print 'Starting TX...',
        sys.stdout.flush()
        c.enable_udp_output()
        print 'done.'
    if opts.txStop:
        print 'Stopping TX...',
        sys.stdout.flush()
        c.disable_udp_output()
        print 'done.'

    print "Current settings:"
    regValues = c.xeng_ctrl_get_all()
    for value in regValues:
        print "\t" + value['fpgaHost'] + ": tx " + ("enabled" if value['gbe_out_enable'] else "disabled")

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
exit()
