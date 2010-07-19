#!/usr/bin/env python

'''
Reads the values of the RMS amplitude accumulators on the ibob through the X engine's XAUI connection.\n

Revisions:
1.2 JRM Support any number of antennas together with F engine 305 and X engine rev 322 and later.\n
1.1 JRM Requires F engine rev 302 or later and X engine rev 308 or later.\n

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
    p.set_usage('corr_adc_amplitudes.py [options] CONFIG FILE')
    p.add_option('-v', '--verbose', dest='verbose', action='store_true',
        help='Print raw output.')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])


    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for s,server in enumerate(c.xsrvs): c.loggers[s].setLevel(10)
    print 'done.'

    servers = c.fsrvs
    fpgas = c.ffpgas
    n_ants = c.config['n_ants']
    n_ants_per_xaui = c.config['n_ants_per_xaui']
    n_xaui_ports_per_fpga = c.config['n_xaui_ports_per_fpga']
    adc_bits = c.config['adc_bits']
    adc_levels_acc_len = c.config['adc_levels_acc_len']
    pols = c.config['pols']

    while(1):
        amps=c.get_adc_amplitudes()
        time.sleep(1)
        #Move cursor home:
        print '%c[H'%chr(27)
        #clear the screen:
        print '%c[2J'%chr(27)
        print 'IBOB: ADC0 is bottom (furthest from power port), ADC1 is top (closest to power port). ROACH: ADC0 is right, ADC1 is left (when viewed from front)'
        print 'ADC input amplitudes averaged %i times.'%c.config['adc_levels_acc_len']
        print '------------------------------------------------'
        for ant,pol in amps:
            ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
            print 'Ant %i pol %s (%s input %i): %.3f (%2.2f bits used)'%(ant,pol,c.srvs[ffpga_n],feng_input, amps[(ant,pol)]['rms'],amps[(ant,pol)]['bits'])
    print '--------------------'

except KeyboardInterrupt:
    exit_clean()
except:
    print ''

print 'Done with all'
exit_clean()
