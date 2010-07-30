#! /usr/bin/env python
""" Resets the 10GbE cores on all X engines through fabric rst port toggle.
"""
import corr, time, sys, numpy, os, logging

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n',lh.printMessages()
    try:
        c.disconnect_all()
    except: pass
    time.sleep(1)
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
    p.set_usage('corr_rst_gbe.py CONFIG_FILE')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.xloggers: logger.setLevel(10)
    print 'done.'

    print('\nResetting GBE cores...'),
    sys.stdout.flush()

    c.xeng_ctrl_set_all(gbe_disable=True) #DO NOT RESET THE 10GBE CORES SYNCHRONOUSLY... Packets will be routed strangely!
    c.xeng_ctrl_set_all(gbe_disable=True, gbe_rst=True)
    c.xeng_ctrl_set_all(gbe_disable=True, gbe_rst=False)
    c.xeng_ctrl_set_all(gbe_disable=False, gbe_rst=False)

    print 'done.'

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
exit()
