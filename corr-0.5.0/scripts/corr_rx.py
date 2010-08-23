#!/usr/bin/python
import corr,ephem,aipy,numpy,sys

def exit_fail():
    print 'FAILURE DETECTED. Log entries:\n',lh.printMessages()
    print "Unexpected error:", sys.exc_info()
    try:
        c.disconnect_all()
    except: pass
    try:
        rx.stop()
    except: pass
    raise
    exit()

def exit_clean():
    try:
        c.disconnect_all()
    except: pass
    try:
        rx.stop()
    except: pass
    exit()


if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('corr_rx.py [options] CONFIG_FILE')
    p.set_description(__doc__)
    p.add_option('-v', '--verbose', dest='verbose', action='store_true',
        help='Print raw contents.')
    p.add_option('-s', '--bufferslots', dest='bufferslots', type='int', default=10240,
        help='Number of buffer slots to allocate. Default 10240.')
    p.add_option('-w', '--bufferwindows', dest='bufferwindows', type='int', default=4,
        help='Number of simultaneous buffer windows. Default 4.')
    p.add_option('-t', '--t_per_file', dest='t_per_file', type='int', default=2,
        help='Length of time in minutes to capture data before starting a new file. Default 2 min.')

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
    
    if c.config['n_pols']==2 and c.config['pols']==['x','y']:
        pols=['xx','yy','xy','yx']
    else:
        raise RuntimeError("You polarisation configuration is not supported.")

    port = c.config['katcp_port']
    n_chans=c.config['n_chans']
    adc_clk=c.config['adc_clk']
    int_time = c.config['int_time'] #integration time in seconds
    acc_len = c.config['n_accs'] # number of accumulations
    bandwidth = float(c.config['bandwidth'])/1000000000 #system bandwidth in GHz
    sdf = bandwidth/n_chans #change in frequency per channel in GHz
    sfreq = sdf/2  # sky frequency of (center of) first channel in window in GHz

    location=0,0,0 #GPS co-ordinates of this array
    ants=[(ant,ant,ant) for ant in range(c.config['n_ants'])] #this is supposed to label the location of the antennas?
    freqs = numpy.arange(c.config['n_chans'], dtype=numpy.float) * sdf + sfreq
    beam = aipy.phs.Beam(freqs)
    ants = [aipy.phs.Antenna(a[0],a[1],a[2],beam) for a in ants]
    aa = aipy.phs.AntennaArray(ants=ants, location=location)

    t_per_file=ephem.minute*opts.t_per_file

    n_windows_to_buffer=opts.bufferwindows
    n_bufferslots=opts.bufferslots
    max_payload_len=8192

    sdisp_destination_ip = "127.0.0.1"
    print "Sending signal display data to",sdisp_destination_ip

    rx=corr.dacq.DataReceiver(aa, pols=pols, adc_rate=adc_clk,
                nchan=n_chans, sfreq=sfreq, sdf=sdf,
                inttime=int_time, t_per_file=t_per_file,
                nwin=n_windows_to_buffer, bufferslots=n_bufferslots, 
                payload_len=max_payload_len, sdisp=1, 
                sdisp_destination_ip=sdisp_destination_ip,
                acc_len=acc_len)
    rx.start(port)

    raw_input("Press Enter to terminate...\n") 
        #capture a bunch of stuff here

    rx.stop()


except KeyboardInterrupt:
    exit_clean()
except:
    exit_fail()

exit_clean()

