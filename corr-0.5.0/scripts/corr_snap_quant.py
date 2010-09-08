#!/usr/bin/env python

'''
Grabs the contents of "snap_xaui" for analysis.
Does not use the standard 'corr_functions' error checking.
Assumes 4 bit values for power calculations.
Assumes the correlator is already initialsed and running etc.

Author: Jason Manley
Date: 2009-07-01

Revisions:
2010-07022: JRM Mods to support ROACH based F engines (corr-0.5.0)
2010-02-01: JRM Added facility to offset capture point.
                Added RMS printing and peak bits used.
2009-07-01: JRM Ported to use corr_functions connectivity
                Fixed number of bits calculation

'''
import corr, time, numpy, struct, sys, logging, pylab,matplotlib

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

def drawDataCallback(acc,n_accs):
        matplotlib.pyplot.clf()
        maxY = 0
        matplotlib.pyplot.subplot(1, 1,1)
        unpackedData,n_accs = get_data(acc,n_accs)
        matplotlib.pyplot.plot(numpy.divide(unpackedData,n_accs))
        #matplotlib.pyplot.xticks(range(0,1024,10))
        matplotlib.pyplot.xlim(0,c.config['n_chans'])
        matplotlib.pyplot.title('Quantiser amplitude output for input %i %s, averaged over %i spectra.'%(ant,pol,n_accs))
        matplotlib.pyplot.xlabel('Frequency channel')
        matplotlib.pyplot.ylabel('Average level')
        #fig.canvas.draw()
        fig.canvas.manager.window.after(100, drawDataCallback,unpackedData,n_accs)
   
def get_data(acc,n_accs):
    print 'Integrating data %i...'%n_accs,
    print ' Grabbing data off snap blocks...',
    bram_dmp=c.ffpgas[ffpga_n].get_snap(dev_name,['bram'],man_trig=man_trigger,wait_period=2)
    print 'done.'

    print ' Unpacking bram contents...',
    sys.stdout.flush()
    pckd_8bit = struct.unpack('>%iB'%(bram_dmp['length']*4),bram_dmp['bram'])
    unpacked_vals=[]
    for val in pckd_8bit:
        pol_r_bits = (val & ((2**8) - (2**4)))>>4
        pol_i_bits = (val & ((2**4) - (2**0)))
        unpacked_vals.append(float(((numpy.int8(pol_r_bits << 4)>> 4)))/(2**binary_point) + 1j * float(((numpy.int8(pol_i_bits << 4)>> 4)))/(2**binary_point))
    print 'done.'

    print ' Accumulating...', 
    for i,val in enumerate(unpacked_vals):
        freq=i%c.config['n_chans']
        acc[freq]+=abs(val)
        if opts.verbose:
            print '[%5i] [Freq %4i] %2.2f + %2.2f (summed amplitude %3.2f)'%(i,freq,val.real,val.imag,acc[freq])

    n_accs += (len(unpacked_vals)/c.config['n_chans'])
    print 'done.'

    return (acc,n_accs)

    

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('corr_snap_xaui.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-t', '--man_trigger', dest='man_trigger', action='store_true',
        help='Trigger the snap block manually')   
    p.add_option('-v', '--verbose', dest='verbose', action='store_true',
        help='Print raw output.')  
    p.add_option('-p', '--noplot', dest='noplot', action='store_true',
        help='Do not plot averaged spectrum.')  
    p.add_option('-a', '--ant', dest='ant', type='str', default='0x',
        help='Select antenna to query. Default: 0x')

 
    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()

    if opts.man_trigger: man_trigger=True
    else: man_trigger=False

report=[]
lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.xloggers: logger.setLevel(10)
    print 'done.'

    binary_point = c.config['feng_fix_pnt_pos']
    packet_len=c.config['10gbe_pkt_len']
    n_chans=c.config['n_chans']
    num_bits = c.config['feng_bits']
    adc_bits = c.config['adc_bits']
    adc_levels_acc_len = c.config['adc_levels_acc_len']
    
    ant = int(opts.ant[0:-1])
    pol = opts.ant[-1]

    if not pol in c.config['pols']: print 'Unrecognised polarisation (%s). Must be in'%pol,c.config['pols']
    if ant>c.config['n_ants']: print 'Invalid antenna (%i). There are %i antennas in this design.'%(ant,c.config['n_ants'])

    if num_bits != 4:
        print 'This script is only written to work with 4 bit quantised values.'
        exit()
    
    ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = c.get_ant_location(ant,pol)

    print 'Looking at input %i on %s.'%(feng_input,c.fsrvs[ffpga_n])
    dev_name='quant_snap%i'%feng_input

    acc=numpy.zeros((c.config['n_chans'],))
    n_accs=0

    # set up the figure with a subplot for each polarisation to be plotted
    fig = matplotlib.pyplot.figure()
    ax = fig.add_subplot(1, 1, 1)

    # start the process
    fig.canvas.manager.window.after(100, drawDataCallback,acc,n_accs)
    matplotlib.pyplot.show()
    print 'Plot started.'


except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

exit_clean()

