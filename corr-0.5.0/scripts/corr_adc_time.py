#!/usr/bin/env python

'''
Plots time domain ADC values from a specified antenna and pol.\n

Revisions:
2010/08/03 GSJ Initial.\n

'''
import matplotlib
import time, corr, numpy, struct, sys, logging, pylab


def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n', lh.printMessages()
    print "Unexpected error:", sys.exc_info()
    try:
        c.disconnect_all()
    except:
        pass
    exit()

def exit_clean():
    try:
        c.disconnect_all()
    except:
        pass
    exit()

if __name__ == '__main__':
    from optparse import OptionParser
    p = OptionParser()
    p.set_usage('corr_adc_histogram.py [options] CONFIG FILE')
    p.add_option('-v', '--verbose', dest = 'verbose', action = 'store_true', help = 'Print raw output.')
    p.add_option('-n', '--plotlen', dest = 'plotlen', type = 'int',default= 100, help = 'Number of data points to plot.')
    p.add_option('-a', '--antenna', dest = 'antAndPol', action = 'store', help = 'Specify an antenna and pol for which to get ADC histograms. 3x will give pol x for antenna three. 27y will give pol y for antenna 27.')
    p.set_description(__doc__)
    opts, args = p.parse_args(sys.argv[1:])
    if args==[]:
        print 'Please specify a configuration file!\nExiting.'
        exit()


# make the log handler
lh=corr.log_handlers.DebugLogHandler()

# check the specified antennae, if any
polList = []
if opts.antAndPol == None:
    print 'No antenna given for which to plot data.'
    exit_fail()

try:
    # make the correlator object
    print 'Connecting to correlator...',
    c=corr.corr_functions.Correlator(args[0], lh)
    for s,server in enumerate(c.fsrvs): c.floggers[s].setLevel(10)
    print 'done.'

    ant,pol = int(opts.antAndPol[:-1]),opts.antAndPol[-1]
    (ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input) = c.get_ant_location(ant,pol)
    snapraw1=c.ffpgas[ffpga_n].get_snap('adc_snap%i'%feng_input,['bram'])
    unpackeddata1=struct.unpack('>%ib'%(snapraw1['length']*4),snapraw1['bram'])
    pylab.plot(unpackeddata1[0:opts.plotlen])
    pylab.title('ADC_AMPLITUDE %i %s'%(ant,pol))
    pylab.xlabel('Time in adc samples')
    pylab.ylabel('Adc count')
    pylab.show()

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

print 'Done with all.'
exit_clean()

# end

