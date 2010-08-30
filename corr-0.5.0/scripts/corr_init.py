#! /usr/bin/env python
""" 
Script for initialising casper_n correlators. Requires X engine version 330 and F engine 310 or greater.\n
Can be left running (assuming sufficient bandwidth) and will continuously check that system is sync'd. will attempt recovery if sync is lost.\n\n

Author: Jason Manley\n
Revisions:\n
2010-08-08  JRM Changed order of execution to match dataflow.
2010-08-05  JRM Mods at GMRT for int time, feng clock, vacc sync checks etc.
2010-07-20  JRM Mods to use ROACH based F engines.\n 
2010-04-02  JCL Removed base_ant0 software register from Xengines, moved it to Fengines, and renamed it to use ibob_addr0 and ibob_data0.  Use function write_ibob() from corr_functions.py to set antenna offsets on Fengines
2010-01-06  JRM Added output control and self-check after primary init.
2009-12-02  JRM Re-enabled acc_len config.\n
2009-11-20: JRM Hardcoded 10GbE configuration call.\n
2009-11-10: JRM Added EQ config.\n
2009-07-02: JRM Switch to use corr_functions.\n
2009-06-15  JRM New 10GbE config scheme for ROACH.\n
2009-05-25  JRM Switched to KATCP.\n
2008-10-30  JRM Removed loopback flush since this has been fixed in hardware\n
2008-09-12  JRM Added support for different numbers of X and F engines\n
2008-02-20  JRM Now uses UDP borphserver\n
                New ibob address/data communication scheme\n
2008-02-14  JRM Fixed gbe_config for >1 BEE\n
2008-01-09  JRM DESIGNED FOR Cn rev 308b and upwards\n
                New loopback_mux flush\n
                Now grabs config settings from global corr.conf file \n
"""
import corr, time, sys, numpy, os, logging, katcp, socket, struct

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
    p.set_usage('corr_init.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-r', '--n_retries', dest='n_retries', type='int', default=40, 
        help='Number of times to try after an error before giving up. Default: 40')
    p.add_option('-p', '--skip_prog', dest='prog_fpga',action='store_false', default=True, 
        help='Skip FPGA programming (assumes already programmed).  Default: program the FPGAs')
    p.add_option('-e', '--skip_eq', dest='prog_eq',action='store_false', default=True, 
        help='Skip configuration of the equaliser in the F engines.  Default: set the EQ according to config file.')
    p.add_option('-c', '--skip_core_init', dest='prog_10gbe_cores',action='store_false', default=True, 
        help='Skip configuring the 10GbE cores (ie starting tgtap drivers).  Default: start all drivers')
    p.add_option('-o', '--skip_output_config', dest='config_output',action='store_false', default=True, 
        help='Do not begin outputting packetised data.  Default: start the output.')
    p.add_option('-v', '--verbose', dest='verbose',action='store_true', default=False, 
        help='Be verbose about errors.')
    p.add_option('-s', '--spead', dest='spead',action='store_false', default=True, 
        help='Do not send SPEAD metadata and data descriptor packets. Default: send all SPEAD info.')

    opts, args = p.parse_args(sys.argv[1:])

    if args==[]:
        print 'Please specify a configuration file! \nExiting.'
        exit()
    verbose=opts.verbose
    prog_fpga=opts.prog_fpga

lh=corr.log_handlers.DebugLogHandler()

try:
    print 'Connecting...',
    c=corr.corr_functions.Correlator(args[0],lh)
    for logger in c.floggers+c.xloggers: logger.setLevel(10)
    print 'done'

    print '\n======================'
    print 'Initial configuration:'
    print '======================'

    if prog_fpga:
        print ''' Clearing the FPGAs...''',
        sys.stdout.flush()
        c.deprog_all()
        time.sleep(2)
        print 'done.'

        # PROGRAM THE DEVICES
        print ''' Programming the Fengines with %s and the Xengines with %s...'''%(c.config['bitstream_f'],c.config['bitstream_x']),
        sys.stdout.flush()
        c.prog_all()
        print 'done.'
    else: print ' Skipped programming FPGAs.'

    # Disable 10GbE cores until the network's been setup and ARP tables have settled. 
    # Need to do a reset here too to flush buffers in the core. But must be careful; resets are asynchronous and there must be no activity on the core (fifos) when they are reset.
    print('\n Pausing 10GbE data exchange, resetting the 10GbE cores and clearing X engine TVGs...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(gbe_disable=True) #DO NOT RESET THE 10GBE CORES SYNCHRONOUSLY... Packets will be routed strangely!
    c.xeng_ctrl_set_all(gbe_disable=True, gbe_rst=True) 
    print 'done.'

    print ''' Syncing the F engines...''',
    sys.stdout.flush()
    trig_time=c.arm()
    print 'Armed. Expect trigg at %s local (%s UTC).'%(time.strftime('%H:%M:%S',time.localtime(trig_time)),time.strftime('%H:%M:%S',time.gmtime(trig_time))),
    print 'SPEAD packet sent.'

    print(''' Checking F engine clocks...'''),
    sys.stdout.flush()
    if c.check_feng_clks(): print 'ok'
    else: 
        print ('FAILURES detected! Details:')
        c.check_feng_clks(verbose=True)

    print(''' Setting the board indices...'''),
    sys.stdout.flush()
    c.feng_brd_id_set()
    c.xeng_brd_id_set()
    print ('''done''')

    if c.config['adc_type'] == 'katadc':
        print(''' Setting the RF gain stages on the KATADC...'''),
        sys.stdout.flush()
        c.rf_gain_set_all()
        print ('''done''')

    print(''' Setting the FFT shift schedule to 0x%X...'''%c.config['fft_shift']),
    sys.stdout.flush()
    c.fft_shift_set_all()
    print ('''done''')

    print ' Configuring EQ...',
    sys.stdout.flush()
    if opts.prog_eq:
        c.eq_set_all()
        print 'done'
    else: print 'skipped.'

    # Set UDP TX data port
    print (''' Setting the UDP TX data port to %i...'''%(c.config['10gbe_port'])),
    sys.stdout.flush()
    c.udp_exchange_port_set()
    print 'done'

    # Configure the 10 GbE cores and load tgtap drivers
    print(''' Configuring the 10GbE cores...'''),
    sys.stdout.flush()
    if opts.prog_10gbe_cores:
        c.config_roach_10gbe_ports()
        print 'done'
    else: print 'skipped'

    print('''\nWaiting for ARP to complete...'''),
    if opts.prog_10gbe_cores:
        sys.stdout.flush()
        time.sleep(15) #all boards should have cycled through entire ARP table in 256*0.1=26 seconds?
        print '''done'''
    else: print 'skipped'

    # Restart 10GbE data exchange (had to wait until the network's been setup and ARP tables have settled).
    # need to be careful about resets. these are asynchronous.
    print(' Starting 10GbE data exchange...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(gbe_disable=True,gbe_rst=False)
    c.xeng_ctrl_set_all(gbe_disable=False,gbe_rst=False)
    print 'done.'
    
    print(' Flushing loopback muxs...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(loopback_mux_rst=True,gbe_disable=True)
    time.sleep(2)
    c.xeng_ctrl_set_all(loopback_mux_rst=False,gbe_disable=False)
    print 'done.'

    print '\n============================================================='
    print 'Verifying correct Feng ---> Xeng <--> switch data exchange...'
    print '============================================================='

    wait_time=len(c.xfpgas)/2
    print(''' Wait %i seconds for system to stabalise...'''%wait_time),
    sys.stdout.flush()
    time.sleep(wait_time)
    print '''done'''

    print(''' Resetting error counters...'''),
    sys.stdout.flush()
    c.rst_cnt()
    print '''done'''

    time.sleep(1)

    print(""" Checking that all XAUI links are working..."""),
    sys.stdout.flush()
    if c.check_xaui_error(): print 'ok'
    else: 
        print ('FAILURES detected! Details:')
        c.check_xaui_error(verbose=True)

    print(""" Checking that the same timestamp F engine data is arriving at all X boards within a sync period..."""),
    if c.check_xaui_sync(): print 'ok'
    else: 
        print ('FAILURE! ')
        print "Check your 1PPS, clock source, XAUI links, clock on this computer (should be NTP sync'd for reliable arming) and KATCP network links."
        exit_clean()


    print(''' Checking that all X engine FPGAs are sending 10GbE packets...'''),
    sys.stdout.flush()
    if c.check_10gbe_tx(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_10gbe_tx(verbose=True)

    print(''' Checking that all X engine FPGAs are receiving 10GbE packets...'''),
    sys.stdout.flush()
    if c.check_10gbe_rx(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_10gbe_rx(verbose=True)
        exit_clean()

    print(''' Waiting for loopback muxes to sync...'''),
    sys.stdout.flush()
    loopback_ok=c.check_loopback_mcnt()
    loop_retry_cnt=0
    while (not loopback_ok) and (loop_retry_cnt< opts.n_retries):
        time.sleep(1)
        loop_retry_cnt+=1
        print '%i...'%loop_retry_cnt,
        sys.stdout.flush()
        loopback_ok=c.check_loopback_mcnt()
    if c.check_loopback_mcnt(): print 'ok'
    else: 
        print ('FAILURES detected!')
        exit_clean()


    print ''' Checking that all X engines are receiving all their packets...''',
    sys.stdout.flush()
    time.sleep(1)
    c.rst_cnt()
    if c.check_x_miss(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_x_miss(verbose=True)
        exit_clean()

    print (''' Setting the number of accumulations to %i (%2.2f seconds) and syncing VACCs...'''%(c.config['n_accs'],c.config['int_time'])),
    sys.stdout.flush()
    c.acc_time_set()
    c.rst_cnt()
    print 'done'

    print(''' Checking vector accumulators...'''),
    sys.stdout.flush()
    print "Waiting for an integration to finish...",
    sys.stdout.flush()
    time.sleep(c.config['int_time']+0.1)
    print('''done. Checking...'''),
    sys.stdout.flush()
    if c.check_vacc(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_vacc(verbose=True)
        exit_clean()
    
    if opts.config_output: 
        print ' Enabling UDP output...',
        sys.stdout.flush()
        c.write_all_xeng_ctrl(gbe_out_enable=True)
        print  'done'

    print ' Sending SPEAD metatdata and data descriptors...',
    sys.stdout.flush()
    if opts.spead:
        c.spead_static_meta_issue()
        c.spead_eq_meta_issue()
        c.spead_time_meta_issue()
        c.spead_data_descriptor_issue()
        print 'done'
    else: print 'skipped.'

    print ' Configuring UDP 10GbE output to %s:%i...'%(c.config['rx_udp_ip_str'],c.config['rx_udp_port']),
    sys.stdout.flush()
    if opts.config_output: 
        c.config_udp_output()
        print 'done'
    else: print 'skipped.'


    print(''' Resetting error counters...'''),
    sys.stdout.flush()
    c.rst_cnt()
    print '''done'''

except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
