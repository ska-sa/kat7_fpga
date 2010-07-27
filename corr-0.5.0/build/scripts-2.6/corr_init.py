#!/usr/bin/python
""" 
Script for initialising casper_n correlators. Requires X engine version 330 and F engine 310 or greater.\n
Can be left running (assuming sufficient bandwidth) and will continuously check that system is sync'd. will attempt recovery if sync is lost.\n\n

Author: Jason Manley\n
Revisions:\n
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
    p.set_usage('init_corr.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-m', '--monitor_only', dest='monitor_only', action='store_true', default=False, 
        help='Skip the initialision. ie Only monitor.')
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
        print ''' Programming the Fengines with %s and the Xengines with %s...'''%(c.config['fbitstream'],c.config['xbitstream']),
        sys.stdout.flush()
        c.prog_all()
        print 'done.'
    else: print ' Skipped programming FPGAs.'

    # Disable 10GbE cores until the network's been setup and ARP tables have settled. Need to do a reset here too to flush buffers in the core.
    print('\n Pausing 10GbE data exchange, resetting the 10GbE cores and clearing X engine TVGs...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(gbe_disable=True, gbe_rst=True)
    print 'done.'

    if opts.prog_10gbe_cores:
        # Configure the 10 GbE cores and load tgtap drivers
        print(''' Configuring the 10GbE cores...'''),
        sys.stdout.flush()
        c.config_roach_10gbe_ports()
        time.sleep(10)
        #lh.printMessages()
        print 'done'

    print ''' Syncing the F engines...'''
    sys.stdout.flush()
    trig_time=c.arm()
    print 'Armed. Expect trigg at %s local (%s UTC).'%(time.strftime('%H:%M:%S',time.localtime(trig_time)),time.strftime('%H:%M:%S',time.gmtime(trig_time)))
    #send a SPEAD resync packet:
    #time_skt=socket.socket(type=socket.SOCK_DGRAM)
    #pkt_str=struct.pack('>HHHHQ',0x5453,3,0,1,trig_time)
    #time_skt.sendto(pkt_str,(c.config['rx_udp_ip_str'],c.config['rx_udp_port']))
    #time_skt.close()
    #print 'Pkt sent.'
    print 'done'

    print (''' Setting the accumulation length to %i (%2.2f seconds)...'''%(c.config['acc_len'],c.config['int_time'])),
    sys.stdout.flush()
    c.acc_len_set()
    print 'done'

    print(''' Setting the board indices...'''),
    sys.stdout.flush()
    #c.brd_id_set()
    print ('''done''')

    # Set UDP TX data port
    print (''' Setting the UDP TX data port to %i...'''%(c.config['10gbe_port'])),
    sys.stdout.flush()
    c.udp_exchange_port_set()
    print 'done'

    if opts.prog_10gbe_cores:
        print('''\nWaiting for ARP to complete...'''),
        sys.stdout.flush()
        time.sleep(15)
        print '''done'''

    if opts.config_output: 
        out_ip=socket.inet_ntop(socket.AF_INET,struct.pack('>I',c.config['rx_udp_ip']))
        print '\n Configuring UDP 10GbE Output to %s:%i...'%(out_ip,c.config['rx_udp_port']),
        c.config_udp_output()
        print 'done'

        #print ' Enabling UDP output...',
        #sys.stdout.flush()
        #c.write_all_xeng_ctrl(gbe_out_enable=True)
        #print  'done'
    
    else:
        """Even if we aren't configuring the 10GbE cores, we still need to setup these registers, because they're interrogated by cn_tx.py"""
        for x in range(c.config['x_per_fpga']):
            for f,fpga in enumerate(c.xfpgas):
                fpga.write_int('inst_xeng_id%i'%x,x*len(c.xfpgas)+f)

    #print('Resetting 10GbE cores...'),
    #sys.stdout.flush()
    #c.write_all_xeng_ctrl(gbe_rst=True)
    #c.write_all_xeng_ctrl(gbe_rst=False)
    #print 'done.'

    # Restart 10GbE data exchange (had to wait until the network's been setup and ARP tables have settled).
    print(' Starting 10GbE data exchange...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(gbe_disable=False)
    print 'done.'
    
    print ' Configuring EQ...',
    sys.stdout.flush()
    if opts.prog_eq:
        c.eq_set_all()
        print 'done'
    else: print 'skipped.'

    print(' Flushing loopback muxs...'),
    sys.stdout.flush()
    c.xeng_ctrl_set_all(loopback_mux_rst=True,gbe_disable=True)
    time.sleep(2)
    c.xeng_ctrl_set_all(loopback_mux_rst=False,gbe_disable=False)
    print 'done.'

    print '\n================================'
    print 'Verifying correct operation...'
    print '================================'

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
    if c.check_xaui_error(): print 'ok'
    else: 
        print ('FAILURES detected! Details:')
        c.check_xaui_error(verbose=True)

    print(""" Checking that F engines are sync'd to first order..."""),
    if c.check_xaui_sync(): print 'ok'
    else: 
        print ('FAILURE!')
        exit_clean()


    print(''' Checking that all BEE FPGAs are sending 10GbE packets...'''),
    sys.stdout.flush()
    if c.check_10gbe_tx(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_10gbe_tx(verbose=True)

    print(''' Checking that all BEE FPGAs are receiving 10GbE packets...'''),
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

    print(''' Resetting error counters...'''),
    sys.stdout.flush()
    c.rst_cnt()
    print '''done'''

    time.sleep(1)

    print ''' Checking that all X engines are receiving all their packets...''',
    sys.stdout.flush()
    if c.check_x_miss(): print 'ok'
    else: 
        print ('FAILURES detected!')
        c.check_x_miss(verbose=True)
        exit_clean()

#    monitor()
except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()
