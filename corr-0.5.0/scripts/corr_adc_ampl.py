#!/usr/bin/env python

'''
Reads the values of the RMS amplitude accumulators on the ibob through the X engine's XAUI connection.\n

Revisions:
1.21 PVP Fix filename in OptionParser section.
1.20 JRM Support any number of antennas together with F engine 305 and X engine rev 322 and later.\n
1.10 JRM Requires F engine rev 302 or later and X engine rev 308 or later.\n

'''
import corr, time, numpy, struct, sys, logging


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
    p.set_usage('corr_adc_ampl.py [options] CONFIG FILE')
    p.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Print raw output.')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file!\nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting to F-engines using config file %s...'%args[0],
    c=corr.corr_functions.Correlator(args[0],lh)
    for s, server in enumerate(c.fsrvs): c.floggers[s].setLevel(10)
    print 'done.'

    while(True):
        amps=c.adc_amplitudes_get()
        stats=c.feng_status_get_all()
        c.rst_cnt()
        time.sleep(1)
        #Move cursor home:
        print '%c[H'%chr(27)
        #clear the screen:
        print '%c[2J'%chr(27)
        print 'IBOB: ADC0 is bottom (furthest from power port), ADC1 is top (closest to power port).\n\rROACH: ADC0 is right, ADC1 is left (when viewed from front).'
        print 'ADC input amplitudes averaged %i times.'%c.config['adc_levels_acc_len']
        print '------------------------------------------------'
        for ant,pol in sorted(amps):
            ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = c.get_ant_location(ant,pol)
            print 'Ant %i pol %s (%s input %i): '%(ant,pol,c.fsrvs[ffpga_n],feng_input),

            if stats[(ant,pol)]['adc_overrange']: print 'ADC OVERRANGE.'
            else: print '%.3f (%2.2f bits used)'%(amps[(ant,pol)]['rms'],amps[(ant,pol)]['bits'])
            
    print '--------------------'

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

print 'Done with all'
exit_clean()
