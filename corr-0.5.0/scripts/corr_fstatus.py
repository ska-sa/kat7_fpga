#! /usr/bin/env python
"""
Reads the error counters on the correlator Xengines and reports such things as accumulated XAUI and packet errors.
\n\n
Revisions:
2010-07-22  JRM Ported for corr-0.5.5
2009-12-01  JRM Layout changes, check for loopback sync
2009/11/30  JRM Added support for gbe_rx_err_cnt for rev322e onwards.
2009/07/16  JRM Updated for x engine rev 322 with KATCP.
"""
import corr, time, sys,struct,logging

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
    p.set_usage('read_missing.py [options] CONFIG_FILE')
    p.set_description(__doc__)

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
    servers = c.fsrvs
    n_ants = c.config['n_ants']
    start_t = time.time()

    clk_check = c.feng_clks_get()
    print 'Connected F engines: '
    for fn,feng in enumerate(c.fsrvs):
        print '\t %s (%i MHz)'%(feng,clk_check[fn])

    pps_check = c.check_feng_clks()
    print "F engine clock integrity: %s."%{True: 'Pass', False: "FAIL!"}[pps_check]
    if not pps_check: print c.check_feng_clk_freq(verbose=True)

    lookup={'adc_overrange': 'ADC RF input overrange.',
            'ct_error': 'Corner-turner error.',
            'fft_overrange': 'Overflow in the FFT.',
            'quant_overrange': 'Quantiser overrange.',
            'xaui_lnkdn': 'XAUI link is down.',
            'xaui_over': "XAUI link's TX buffer is overflowing"}

    time.sleep(2)

    #clear the screen:
    print '%c[2J'%chr(27)


    while True:

        loopback_ok=c.check_loopback_mcnt() 
        mcnts = c.mcnt_current_get()
        status = c.feng_status_get_all()
        uptime = c.feng_uptime()
        fft_shift = c.fft_shift_get_all()
        
        if c.config['adc_type'] == 'katadc' : rf_status = c.rf_status_get_all()
    
        # move cursor home
        print '%c[2J'%chr(27)
        
        for ant in range(c.config['n_ants']):
            for pol in c.config['pols']:
                ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = c.get_ant_location(ant,pol)
                print '  Input %i%s (%s input %i, mcnt %i):'%(ant,pol,c.fsrvs[ffpga_n],feng_input, mcnts[ffpga_n])
                
                if c.config['adc_type'] == 'katadc' :
                    print "\tRF %8s:      gain:  %5.1f dB"%({True: 'Enabled', False: 'Disabled'}[rf_status[(ant,pol)][0]],rf_status[(ant,pol)][1])

                print     '\tFFT shift pattern:       0x%06x'%fft_shift[(ant,pol)]

                print '\tCumulative errors: ',
                for item,error in status[(ant,pol)].items():
                    if error == True: print lookup[item],
                print ''


        print 'Time: %i seconds'%(time.time() - start_t)
        time.sleep(2)

except KeyboardInterrupt:
        exit_clean()
except: 
        exit_fail()

exit_clean()

