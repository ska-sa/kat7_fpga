#! /usr/bin/env python
""" 
Selection of commonly-used correlator control functions.
Requires X engine version 330 and F engine 310 or greater.

UNDER CONSTRUCTION

Author: Jason Manley\n
Revisions:\n
2010-06-28  JRM Port to use ROACH based F and X engines.
2010-04-02  JCL Removed base_ant0 software register from Xengines, moved it to Fengines, and renamed it to use ibob_addr0 and ibob_data0.  
                New function write_ibob().
                Check for VACC errors.
2010-01-06  JRM Added gbe_out enable to X engine control register
2009-12-14  JRM Changed snap_x to expect two kinds of snap block, original simple kind, and new one with circular capture, which should have certain additional registers (wr_since_trig).
2009-12-10  JRM Started adding SPEAD stuff.
2009-12-01  JRM Added check for loopback mux sync to, and fixed bugs in, loopback_check_mcnt.\n
                Changed all "check" functions to just return true/false for global system health. Some have "verbose" option to print more detailed errors.\n
                Added loopback_mux_rst to xeng_ctrl
2009-11-06  JRM Bugfix snap_x offset triggering.\n
2009-11-04  JRM Added ibob_eq_x.\n
2009-10-29  JRM Bugfix snap_x.\n
2009-06-26  JRM UNDER CONSTRUCTION.\n
\n

"""
import corr, time, sys, numpy, os, logging, katcp, struct

class Correlator:
    def __init__(self, config_file,log_handler=''):
        self.config = corr.cn_conf.CorrConf(config_file)
        self.xsrvs = self.config['servers_x']
        self.fsrvs = self.config['servers_f']
        self.allsrvs = self.fsrvs+self.xsrvs

        if log_handler == '': log_handler=corr.log_handlers.DebugLogHandler()
        self.log_handler = log_handler
        self.floggers=[logging.getLogger(s) for s in self.fsrvs]
        self.xloggers=[logging.getLogger(s) for s in self.xsrvs]
        for logger in (self.floggers+self.xloggers): logger.addHandler(log_handler)

        self.xfpgas=[corr.katcp_wrapper.FpgaClient(server,self.config['katcp_port'],
                       timeout=10,logger=self.xloggers[s]) for s,server in enumerate(self.xsrvs)]
        self.ffpgas=[corr.katcp_wrapper.FpgaClient(server,self.config['katcp_port'],
                       timeout=10,logger=self.floggers[s]) for s,server in enumerate(self.fsrvs)]
        self.allfpgas = self.ffpgas + self.xfpgas

        time.sleep(0.5)
        if not self.check_katcp_connections():
            self.check_katcp_connections(verbose=True)
            raise RuntimeError("Connection to FPGA boards failed.")

    def __del__(self):
        self.disconnect_all()

    def disconnect_all(self):
        """Stop all TCP KATCP links to all FPGAs defined in the config file."""
        try:
            for fpga in (self.allfpgas): fpga.stop()
        except:
            pass

    def prog_all(self):
        """Programs all the FPGAs."""
        for fpga in self.ffpgas:
            fpga.progdev(self.config['bitstream_f'])
        for fpga in self.xfpgas:
            fpga.progdev(self.config['bitstream_x'])
            #time.sleep(4)

    def deprog_all(self):
        """Deprograms all the FPGAs."""
        for fpga in self.ffpgas:
            fpga.progdev('')
        for fpga in self.xfpgas:
            fpga.progdev('')

    def xread_all(self,register,bram_size,offset=0):
        """Reads a register of specified size from all X engines. Returns a list."""
        rv = [fpga.read(register,bram_size,offset) for fpga in self.xfpgas]
        return rv

    def fread_all(self,register,bram_size,offset=0):
        """Reads a register of specified size from all F engines. Returns a list."""
        rv = [fpga.read(register,bram_size,offset) for fpga in self.ffpgas]
        return rv

    def xread_uint_all(self, register):
        """Reads a value from register 'register' for all Xeng FPGAs."""
        return [fpga.read_uint(register) for fpga in self.xfpgas]

    def fread_uint_all(self, register):
        """Reads a value from register 'register' for all Feng FPGAs."""
        return [fpga.read_uint(register) for fpga in self.ffpgas]

    def xwrite_int_all(self,register,value):
        """Writes to a 32-bit software register on all Xengines."""
        [fpga.write_int(register,value) for fpga in self.xfpgas]

    def fwrite_int_all(self,register,value):
        """Writes to a 32-bit software register on all Fengines."""
        [fpga.write_int(register,value) for fpga in self.ffpgas]

    def write_all_feng_ctrl(self, use_sram_tvg=False, use_fft_tvg1=False, use_fft_tvg2=False, arm_rst=False, mrst=False, clr_errors=False, soft_sync=False):
        """Writes a value to all the Fengine control registers."""
        value = use_sram_tvg<<6 | use_fft_tvg2<<5 | use_fft_tvg1<<4 | clr_errors<<3 | arm_rst<<2 | soft_sync<<1 | mrst<<0
        self.fwrite_int_all('control',value)

    def read_all_feng_ctrl(self):
        """Reads and decodes the values from all the Fengine control registers."""
        all_values = self.fread_uint_all('control')
        return [{'mrst':bool(value&(1<<0)),
                'soft_sync':bool(value&(1<<1)),
                'arm':bool(value&(1<<2)),
                'clr_errors':bool(value&(1<<3))} for value in all_values]

    def write_all_xeng_ctrl(self,loopback_mux_rst=False, gbe_out_enable=False, gbe_disable=False, cnt_rst=False, gbe_rst=False, vacc_rst=False):
        """Writes a value to all the Xengine control registers."""
        value = gbe_out_enable<<16 | loopback_mux_rst<<10 | gbe_disable<<9 | cnt_rst<<8 | gbe_rst<<15 | vacc_rst<<0
        self.xwrite_int_all('ctrl',value)

    def set_fft_shift(self,fft_shift=-1):
        """Configure the FFT on all F engines to the specified schedule. If not specified, default to schedule listed in config file."""
        if fft_shift <0:
            fft_shift = self.config['fft_shift']
        for ant in range(f_per_fpga):
            self.fwrite_int_all("fft_shift%i"%ant,fft_shift)

    def read_all_feng_status(self):
        """Reads and decodes the status register from all the Fengines."""
        for ant in range(self.config['n_ants']):
            ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
            stat = self.ffpgasead_uint_all('fstatus%i'%fn)
            return [{'xaui_lnkdn':bool(value&(1<<2)),
                    'xaui_over':bool(value&(1<<1)),
                    'armed':bool(value&(1<<0))} for value in all_values]

    def read_all_xeng_ctrl(self):
        """Reads and decodes the values from all the Xengine control registers."""
        all_values = self.xread_uint_all('ctrl')
        return [{'gbe_out_enable':bool(value&(1<<16)),
                'gbe_rst':bool(value&(1<<15)),
                'gbe_out_rst':bool(value&(1<<11)),
                'loopback_mux_rst':bool(value&(1<<10)),
                'gbe_disable':bool(value&(1<<9)),
                'cnt_rst':bool(value&(1<<8)),
                'vacc_rst':bool(value&(1<<0))} for value in all_values]

    def check_feng_clk_freq(self,verbose=False):
        """ Checks all Fengine FPGAs' clk_frequency registers to confirm correct PPS operation."""
        all_values = self.fread_uint_all('clk_frequency')
        mode = stats.mode(all_values)
        modalmean=stats.mean(mode[1])
        for fbrd,fsrv in enumerate(self.fsrvs):
            if (all_values[fbrd] > (modalmean+1)) or (all_values[fbrd] < (modalmean -1)):
                if verbose: print "\tClocks between PPS pulses on %s is %i, where mode is %i."%(fsrv,all_values[fbrd], modalmean)
                rv=False
        return rv

    def feng_uptime(self):
        """Returns a list of tuples of (armed_status and pps_count) for all fengine fpgas. Where the count since last arm of the pps signals received (and hence number of seconds since last arm)."""
        all_values = self.fread_uint_all('pps_count')
        pps_cnt = [val & 0x7FFFFFFF for val in all_values]
        arm_stat = [bool(val & 0x80000000) for val in all_values]
        return [(arm_stat[fn],pps_cnt[fn]) for fn in range(len(self.ffpgas))]

    def get_current_mcnt(self):
        "Returns a list of mcnts for all connected f engine FPGAs"
        msw = self.fread_uint_all('mcnt_msw')
        lsw = self.fread_uint_all('mcnt_lsw')
        mcnt = [(msw[i] << 32) + lsw[i] for i in self.fsrvs]
        return mcnt
    
    def arm(self):
        """Arms all F engines. Returns the UTC time at which the system was sync'd in seconds since the Unix epoch (MCNT=0)"""
        #wait for within 100ms of a half-second, then send out the arm signal.
        ready=(int(time.time()*10)%5)==0
        while not ready: 
            ready=(int(time.time()*10)%5)==0
        trig_time=numpy.ceil(time.time()+1) #Syncs on the next second, to ensure any sync pulses already in the datapipeline have a chance to propagate out.
        self.write_all_feng_ctrl(arm_rst=False)
        self.write_all_feng_ctrl(arm_rst=True)
        self.config.write('correlator','sync_time',trig_time)
        return trig_time

    def get_roach_gbe_conf(self,start_addr,fpga,port):
        """Generates 10GbE configuration strings for ROACH-based xengines starting from 
        ip "start_addr" for FPGA numbered "FPGA" (offset from start addr).
        Returns a (mac,ip,port) tuple suitable for passing to tap_start."""
        sys.stdout.flush()
        ip = (start_addr + fpga) & ((1<<32)-1)
        mac = (2<<40) + (2<<32) + ip
        return (mac,ip,port)

    def rst_cnt(self):
        """Resets all error counters on the X engines."""
        self.write_all_xeng_ctrl(cnt_rst=False)
        self.write_all_xeng_ctrl(cnt_rst=True)

    def get_xeng_clks(self):
        """Returns the approximate clock rate of each X engine FPGA in MHz."""
        return [fpga.est_brd_clk() for fpga in self.xfpgas]

    def get_feng_clks(self):
        """Returns the approximate clock rate of each F engine FPGA in MHz."""
        return [fpga.est_brd_clk() for fpga in self.ffpgas]

    def check_katcp_connections(self,verbose=False):
        """Returns a boolean result of a KATCP ping to all all connected boards."""
        result = True
        for fn,fpga in enumerate(self.allfpgas):
            try:
                fpga.ping()
                if verbose: print 'Connection to %s ok.'%self.allsrvs[fn]
            except:
                if verbose: print 'Failure connecting to %s.'%self.allsrvs[fn]
                result = False
        return result

    def check_x_miss(self,verbose=False):
        """Returns boolean pass/fail to indicate if any X engine has missed any data, or if the descrambler is stalled."""
        rv = True
        for x in range(self.config['x_per_fpga']):
            err_check = self.xread_uint_all('pkt_reord_err%i'%(x))
            cnt_check = self.xread_uint_all('pkt_reord_cnt%i'%(x))
            for xbrd,xsrv in enumerate(self.xsrvs):
                if (err_check[xbrd] !=0) or (cnt_check[xbrd] == 0) :
                    if verbose: print "\tMissing X engine data on %s's X engine %i."%(xsrv,x)
                    rv=False
        return rv

    def check_xaui_error(self,verbose=False):
        """Returns a boolean indicating if any X engines have bad incomming XAUI links.
        Checks that data is flowing and that no errors have occured."""
        rv = True
        for x in range(self.config['n_xaui_ports_per_xfpga']):
            cnt_check = self.xread_uint_all('xaui_cnt%i'%(x))
            err_check = self.xread_uint_all('xaui_err%i'%x)
            for f in range(self.config['n_ants']/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_xfpga']):
                if (cnt_check[f] == 0):
                    rv=False
                    if verbose: print '\tNo F engine data on %s, XAUI port %i.'%(self.xsrvs[f],x)
                if (err_check[f] !=0):
                    if verbose: print '\tBad F engine data on %s, XAUI port %i.'%(self.xsrvs[f],x)
                    rv=False
        return rv

    def check_10gbe_tx(self,verbose=False):
        """Checks that the 10GbE cores are transmitting data. Outputs boolean good/bad."""
        rv=True
        for x in range(self.config['n_xaui_ports_per_xfpga']):
            firstpass_check = self.xread_uint_all('gbe_tx_cnt%i'%x)
            time.sleep(0.01)
            secondpass_check = self.xread_uint_all('gbe_tx_cnt%i'%x)

            for f in range(self.config['n_ants']/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_xfpga']):
                if (secondpass_check[f] == 0) or (secondpass_check[f] == firstpass_check[f]):
                    if verbose: print '\t10GbE core %i on %s is stalled.'%(x,self.xsrvs[f])
                    rv = False
        return rv

    def check_10gbe_rx(self,verbose=False):
        """Checks that all the 10GbE cores are receiving packets."""
        rv=True
        for x in range(min(self.config['n_xaui_ports_per_xfpga'],self.config['x_per_fpga'])):
            firstpass_check = self.xread_uint_all('gbe_rx_cnt%i'%x)
            time.sleep(0.01)
            secondpass_check = self.xread_uint_all('gbe_rx_cnt%i'%x)
            for s,xsrv in enumerate(self.xsrvs):
                if (secondpass_check[s] == 0):
                    rv=False
                    if (verbose): print('\tFAILURE! 10GbE core %i on %s is not receiving any packets.' %(s,xsrv))
                elif (secondpass_check[s] == firstpass_check[s]):
                    rv=False
                    if (verbose): print('\tFAILURE! 10GbE core %i on %s received %i packets, but then stopped.'%(s,xsrv,secondpass_check[s]))
        return rv

    def check_loopback_mcnt(self,verbose=False):
        """Checks to see if the mux_pkts block has become stuck waiting for a crazy mcnt Returns boolean true/false."""
        rv=True
        for x in range(min(self.config['n_xaui_ports_per_xfpga'],self.config['x_per_fpga'])):
            firstpass_check = self.xread_all('loopback_mux%i_mcnt'%x,4)
            time.sleep(0.01)
            secondpass_check = self.xread_all('loopback_mux%i_mcnt'%x,4)
            for f in range(self.config['n_ants']/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_xfpga']):
                firstloopmcnt,firstgbemcnt=struct.unpack('>HH',firstpass_check[f])
                secondloopmcnt,secondgbemcnt=struct.unpack('>HH',secondpass_check[f])
                if abs(secondloopmcnt - secondgbemcnt) > (self.config['x_per_fpga']*len(self.xsrvs)): 
                    rv=False
                    if verbose: print('\tFAILURE! Loopback mux on %s GbE port %i is not syncd.' %(self.xsrvs[f],x))

                if (secondloopmcnt == firstloopmcnt):
                    if verbose: print('\tFAILURE! Loopback on %s GbE port %i is stalled.' %(self.xsrvs[f],x))
                    rv = False

                if (secondgbemcnt == firstgbemcnt):
                    if verbose: print('\tFAILURE! 10GbE input on %s GbE port %i is stalled.' %(self.xsrvs[f],x))
                    rv = False
        return rv

    def attempt_fix(self,n_retries=1):
        """Try to fix (sync) the system. If n_retries is <0, retry forever. Otherwise, retry for n_retries."""
        while(1):
            if self.check_all(): return True
            elif n_retries == 0: return False
            #Attempt resync:
            self.arm()
            time.sleep(4)
            rst_cnt()
            time.sleep(2)
            if n_retries > 0:
                n_retries -= 1
                #print ' Retries remaining: %i'%n_retries


    def check_vacc(self,verbose=False):
        """Returns boolean pass/fail to indicate if any X engine has vector accumulator errors."""
        rv = True
        for x in range(self.config['x_per_fpga']):
            err_check = self.xread_uint_all('vacc_err_cnt%i'%(x))
            cnt_check = self.xread_uint_all('vacc_cnt%i'%(x))
            for nx,xsrv in enumerate(self.xsrvs):
                if (err_check[nx] !=0):
                    if verbose: print '\tVector accumulator errors on %s, X engine %i.'%(xsrv,x)
                    rv=False
                if (cnt_check[nx] == 0) :
                    if verbose: print '\tNo vector accumulator data on %s, X engine %i.'%(xsrv,x)
                    rv=False
        return rv

    def check_all(self):
        if (self.check_x_miss() and self.check_vacc() and self.check_loopback_mcnt() and self.check_xaui_error()):
            return True
        else:
            return False

    def sel_vacc_tvg(self,constant=0,n_values=-1,spike_value=-1,spike_location=0,counter=False):
        """Select Vector Accumulator TVG in X engines. Disables other TVGs in the process. 
            Options can be any combination of the following:
                constant:   Integer.    Insert a constant value for accumulation.
                n_values:   Integer.    How many numbers to inject into VACC. Value less than zero uses xengine timing.
                spike_value:    Int.    Inject a spike of this value in each accumulated vector. value less than zero disables.
                spike_location: Int.    Position in vector where spike should be placed.
                counter:    Boolean.    Place a ramp in the VACC.
        """
        #bit5 = rst
        #bit4 = inject counter
        #bit3 = inject vector
        #bit2 = valid_sel
        #bit1 = data_sel
        #bit0 = enable pulse generation

        if spike_value>=0:
            ctrl = (counter<<4) + (1<<3) + (1<<1)
        else:
            ctrl = (counter<<4) + (0<<3) + (1<<1)

        if n_values>0:
            ctrl += (1<<2)
            
        for xeng in range(self.config['x_per_fpga']):
            self.xwrite_int_all('vacc_tvg%i_write1'%(xeng),constant)
            self.xwrite_int_all('vacc_tvg%i_ins_vect_loc'%(xeng),spike_location)
            self.xwrite_int_all('vacc_tvg%i_ins_vect_val'%(xeng),spike_value)
            self.xwrite_int_all('vacc_tvg%i_n_pulses'%(xeng),n_values)
            self.xwrite_int_all('vacc_tvg%i_n_per_group'%(xeng),self.config['n_bls']*self.config['n_stokes']*2)
            self.xwrite_int_all('vacc_tvg%i_group_period'%(xeng),self.config['n_ants']*self.config['xeng_acc_len'])
            self.xwrite_int_all('tvg_sel',(ctrl + (1<<5))<<9)
            self.xwrite_int_all('tvg_sel',(ctrl + (0<<5) + 1)<<9)


    def sel_xeng_tvg(self,mode=0, user_values=()):
        """Select Xengine TVG. Disables VACC (and other) TVGs in the process. Mode can be:
            0: no TVG selected.
            1: select 4-bit counters. Real components count up, imaginary components count down. Bot polarisations have equal values.
            2: Fixed numbers: Pol0real=0.125, Pol0imag=-0.75, Pol1real=0.5, Pol1imag=-0.2
            3: User-defined input values. Should be 8 values, passed as tuple in user_value."""

        if mode>4 or mode<0:
            raise RuntimeError("Invalid mode selection. Mode must be in range(0,4).")
        else:
            self.xwrite_int_all('tvg_sel',mode<<3) 

        if mode==3:
            for i,v in enumerate(user_val):
                for xeng in range(self.config['x_per_fpga']):
                    self.xwrite_int_all('xeng_tvg%i_tv%i'%(xeng,i),v)

    def set_acc_len(self,acc_len=-1):
        """Set the Accumulation Length (in # of spectrum accumulations). If not specified, get the config from the config file."""
        if acc_len<0: acc_len=self.config['acc_len']
        self.xwrite_int_all('acc_len', acc_len)

    def set_ant_index(self):
        """Sets the F engine boards' antenna indices. (Numbers the base_ant software register.)"""
        ant = 0
        for f,fpga in enumerate(self.ffpgas):
            fpga.write_int('base_ant', ant)
            ant += self.config['f_per_feng']

    def get_ant_location(self, ant, pol='x'):
        " Returns the (ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_inputinputinputinputinputinputinputinputinput) location for a given antenna. Ant is integer, as are all returns."
        if ant > self.config['n_ants']: 
            raise RuntimeError("There is no antenna %i in this design (total %i antennas)."%(ant,self.config['n_ants']))
        xfpga_n  = ant/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_xfpga']
        ffpga_n  = ant/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_ffpga']
        xxaui_n  = ant/self.config['n_ants_per_xaui']%self.config['n_xaui_ports_per_xfpga']
        fxaui_n  = ant/self.config['n_ants_per_xaui']%self.config['n_xaui_ports_per_ffpga']
        feng_input = ant%self.config['n_ants_per_xaui'] + self.config['pol_map'][pol]
        return (ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input)

    def set_udp_exchange_port(self):
        """Set the UDP TX port for internal correlator data exchange."""
        self.xwrite_int_all('gbe_port', data_port)

# THIS FUNCTION SHOULD NOT BE REQUIRED WITH DAVE'S UPCOMING 10GBE CORE MODS
#    def set_udp_exchange_ip(self):
#        """Assign an IP address to each XAUI port's associated 10GbE core."""
#        for xaui in range(self.config['n_xaui_ports_per_xfpga']):
#            for f,fpga in enumerate(self.xfpgas):
#                ip = gbe_start_ip + f + xaui*(len(self.xfpgas))
#                fpga.xwrite_int('gbe_ip%i'%xaui, ip)

    def config_roach_10gbe_ports(self):
        """Configures 10GbE ports on roach X engines for correlator data exchange using TGTAP."""
        for f,fpga in enumerate(self.fpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                start_addr=self.config['10gbe_ip']
                start_port=self.config['10gbe_port']
                mac,ip,port=self.get_roach_gbe_conf(start_addr,(f*self.config['n_xaui_ports_per_xfpga']+x),start_port)
                fpga.tap_start('gbe%i'%x,'gbe%i'%x,mac,ip,port)
                
    def config_roach_10gbe_ports_static(self):
        """STATICALLY configures 10GbE ports on roach X engines for correlator data exchange. Will not work with 10GbE output (we don't know the receiving computer's MAC)."""
        arp_table=[(2**48)-1 for i in range(256)]

        for f,fpga in enumerate(self.xfpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                start_addr=self.config['10gbe_ip']
                start_port=self.config['10gbe_port']
                mac,ip,port=self.get_roach_gbe_conf(start_addr,(f*self.config['n_xaui_ports_per_xfpga']+x),start_port)
                arp_table[ip%256]=mac

        for f,fpga in enumerate(self.xfpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                mac,ip,port=self.get_roach_gbe_conf(start_addr,(f*self.config['n_xaui_ports_per_xfpga']+x),start_port)
                fpga.config_10gbe_core('gbe%i'%x,mac,ip,port,arp_table)


    def config_udp_output(self):
        self.xwrite_int_all('gbe_out_ip_addr',self.config['rx_udp_ip'])
        self.xwrite_int_all('gbe_out_port',self.config['rx_udp_port'])
        self.xwrite_int_all('gbe_out_pkt_len',self.config['rx_pkt_payload_len'])
        for x in range(self.config['x_per_fpga']):
            for f,fpga in enumerate(self.xfpgas):
                fpga.xwrite_int('inst_xeng_id%i'%x,x*len(self.xfpgas)+f)
                #Temporary for correlators with separate gbe core for output data:
                ip_offset=self.config['10gbe_ip']+len(self.xfpgas)*self.config['x_per_fpga']
                mac,ip,port=self.get_roach_gbe_conf(ip_offset,(f*self.config['n_xaui_ports_per_xfpga']+x),self.config['rx_udp_port'])
                fpga.tap_start('gbe_out%i'%x,mac,ip,port)

    def enable_udp_output(self):
        self.xwrite_all_xeng_ctrl(gbe_out_enable=True)

    def disable_udp_output(self):
        self.xwrite_all_xeng_ctrl(gbe_out_enable=False)

    def deconfig_roach_10gbe_ports(self):
        """Stops tgtap drivers for the X engines."""
        for f,fpga in enumerate(self.xfpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                fpga.tap_stop('gbe%i'%x)

    def xsnap_all(self,dev_name,brams,man_trig=False,man_valid=False,wait_period=1,offset=-1,circular_capture=False):
        """Triggers and retrieves data from the a snap block device on all the X engines. Depending on the hardware capabilities, it can optionally capture with an offset. The actual captured length and starting offset is returned with the dictionary of data for each FPGA (useful if you've done a circular capture and can't calculate this yourself).\n
        \tdev_name: string, name of the snap block.\n
        \tman_trig: boolean, Trigger the snap block manually.\n
        \toffset: integer, wait this number of valids before beginning capture. Set to negative value if your hardware doesn't support this or the circular capture function.\n
        \tcircular_capture: boolean, Enable the circular capture function.\n
        \twait_period: integer, wait this number of seconds between triggering and trying to read-back the data.\n
        \tbrams: list, names of the bram components.\n
        \tRETURNS: dictionary with keywords: \n
        \t\tlengths: list of integers matching number of valids captured off each fpga.\n
        \t\toffset: optional (depending on snap block version) list of number of valids elapsed since last trigger on each fpga.
        \t\t{brams}: list of data from each fpga for corresponding bram.\n
        """
        if offset >= 0:
            self.xwrite_int_all(dev_name+'_trig_offset',offset)
            #print 'Capturing from snap offset %i'%offset

        #print 'Triggering Capture...',
        self.xwrite_int_all(dev_name+'_ctrl',(0 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))
        self.xwrite_int_all(dev_name+'_ctrl',(1 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))

        done=False
        start_time=time.time()
        while not (done and (offset>0 or circular_capture)) and ((time.time()-start_time)<wait_period): 
            addr      = self.xread_uint_all(dev_name+'_addr')
            done_list = [not bool(i & 0x80000000) for i in addr]
            if (done_list == [True for i in self.xsrvs]): done=True
        bram_sizes=[i&0x7fffffff for i in self.xread_uint_all(dev_name+'_addr')]
        bram_dmp={'lengths':numpy.add(bram_sizes,1)}
        bram_dmp['offsets']=[0 for f in self.xfpgas]
        #print 'Addr+1:',bram_dmp['lengths']
        for f,fpga in enumerate(self.xfpgas):
            if (bram_sizes[f] != fpga.read_uint(dev_name+'_addr')&0x7fffffff) or bram_sizes[f]==0:
                #if address is still changing, then the snap block didn't finish capturing. we return empty.  
                print "Looks like snap block on %s didn't finish."%self.xsrvs[f]
                bram_dmp['lengths'][f]=0
                bram_dmp['offsets'][f]=0
                bram_sizes[f]=0

        if (circular_capture or (offset>=0)) and not man_trig:
            bram_dmp['offsets']=numpy.subtract(numpy.add(self.xread_uint_all(dev_name+'_tr_en_cnt'),offset),bram_sizes)
            #print 'Valids since offset trig:',self.read_uint_all(dev_name+'_tr_en_cnt')
            #print 'offsets:',bram_dmp['offsets']
        else: bram_dmp['offsets']=[0 for f in self.xfpgas]
    
        for f,fpga in enumerate(self.xfpgas):
            if (bram_dmp['offsets'][f] < 0):  
                raise RuntimeError('SNAP block hardware or logic failure happened. Returning no data.')
                bram_dmp['lengths'][f]=0
                bram_dmp['offsets'][f]=0
                bram_sizes[f]=0

        for b,bram in enumerate(brams):
            bram_path = dev_name+'_'+bram
            bram_dmp[bram]=[]
            for f,fpga in enumerate(self.xfpgas):
                if (bram_sizes[f] == 0): 
                    bram_dmp[bram].append([])
                else: 
                    bram_dmp[bram].append(fpga.read(bram_path,(bram_sizes[f]+1)*4))
        return bram_dmp


    def check_xaui_sync(self,verbose=False):
        """Checks if all F engines are in sync by examining mcnts at sync of incomming XAUI streams. \n
        If this test passes, it does not gaurantee that the system is indeed sync'd,
         merely that the F engines were reset between the same 1PPS pulses.
        Returns boolean true/false if system is in sync.
        """
        max_mcnt_difference=4
        mcnts=dict()
        mcnts_list=[]
        mcnt_tot=0
        rv=True

        for ant in range(0,self.config['n_ants'],self.config['n_ants_per_xaui']):
            f = ant / self.config['n_ants_per_xaui'] / self.config['n_xaui_ports_per_xfpga']
            x = ant / self.config['n_ants_per_xaui'] % self.config['n_xaui_ports_per_xfpga']

            n_xaui=f*self.config['n_xaui_ports_per_xfpga']+x
            #print 'Checking antenna %i on fpga %i, xaui %i. Entry %i.'%(ant,f,x,n_xaui)
            mcnts[n_xaui]=dict()
            mcnts[n_xaui]['mcnt'] =self.xfpgas[f].read_uint('xaui_sync_mcnt%i'%x)
            mcnts_list.append(mcnts[n_xaui]['mcnt'])

        import stats
        mcnts['mode']=stats.mode(mcnts_list)
        if mcnts['mode']==0:
            raise RuntimeError("Too many XAUI links are receiving no data. Unable to produce a reliable result.")
        mcnts['modalmean']=stats.mean(mcnts['mode'][1])

#        mcnts:['mean']=stats.mean(mcnts_list)
#        mcnts['median']=stats.median(mcnts_list)
#        print 'mean: %i, median: %i, modal mean: %i mode:'%(mcnts['mean'],mcnts['median'],mcnts['modalmean']),mcnts['mode']

        for ant in range(0,self.config['n_ants'],self.config['n_ants_per_xaui']):
            f = ant / self.config['n_ants_per_xaui'] / self.config['n_xaui_ports_per_xfpga']
            x = ant / self.config['n_ants_per_xaui'] % self.config['n_xaui_ports_per_xfpga']
            n_xaui=f*self.config['n_xaui_ports_per_xfpga']+x
            if mcnts[n_xaui]['mcnt']>(mcnts['modalmean']+max_mcnt_difference) or mcnts[n_xaui]['mcnt'] < (mcnts['modalmean']-max_mcnt_difference):
                rv=False
                if verbose: print 'Sync check failed on %s, port %i with error of %i.'%(self.xservers[f],x,mcnts[n_xaui]['mcnt']-mcnts['modalmean'])
        return rv

    def rf_atten_set(self,ant,pol,level=-1):
        """Enables the RF switch and configures the RF attenuators on KATADC boards. pol is ['x'|'y']"""
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        if level <0:
            level = self.config['rf_att_%i%c'%(ant,pol)] 
        self.ffpgas[ffpga_n].write_int('adc_ctrl%i'%feng_input,(1<<31)+level)

    def rf_atten_set_all(self,level=-1):
        """Sets the RF gain configuration of all inputs to "level". If no level is given, or value is negative, use the defaults from the config file."""
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                self.rf_atten_set(ant,pol,level)

    def rf_disable(self,ant,pol):
        """Disable the RF switch on KATADC boards. pol is ['x'|'y']"""
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported at this time."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        level=self.ffpgas[ffpga_n].read_uint('adc_ctrl%i'%feng_input)&(0x8fffffff)
        self.ffpgas[ffpga_n].write_int('adc_ctrl%i'%feng_input,(1<<31)+level)

    def get_default_eq(self,ant,pol):
        "Fetches the default equalisation configuration from the config file and returns a list of the coefficients for a given input. pol is ['x'|'y']" 
        n_coeffs = self.config['n_chans']/self.config['eq_decimation']
        if self.config['eq_default'] == 'poly':
            poly = self.config['eq_poly_%i%c'%(ant,pol)]
            equalisation = numpy.polyval(poly, range(self.config['n_chans']))[self.config['eq_decimation']/2::self.config['eq_decimation']]
            if self.config['eq_type']=='complex':
                equalisation = [eq+eq*1j for eq in equalisation]
                
        elif self.config['eq_default'] == 'coef':
            equalisation = self.config['eq_coeffs_%i%c'%(ant,pol)]

        if len(equalisation) != n_coeffs: raise RuntimeError("Something's wrong. I have %i eq coefficients when I should have %i."%(len(equalisation),n_coeffs))
        return equalisation

    def eq_set_all(self,verbose_level=0,init_poly=[]):
        """Initialise all connected Fengines' EQs to given polynomial. If no polynomial is given, use defaults from config file."""
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                eq_coeffs = numpy.polyval(init_poly, range(self.config['n_chans']))[self.config['eq_decimation']/2::self.config['eq_decimation']]
                eq_coeffs = [int(coeff) for coeff in eq_coeffs]
                self.eq_spectrum_set(ant=ant,pol=pol,verbose_level=verbose_level,init_coeffs=eq_coeffs)

    def eq_spectrum_set(self,ant,pol,verbose_level=0,init_coeffs=[]):
        """Set a given antenna and polarisation equaliser to given co-efficients. pol is 'x' or 'y'. ant is integer in range n_ants. Assumes equaliser of 16 bits. init_coeffs is list of length n_chans/decimation_factor."""
        fpga=self.ffpgas[ffpga_n]
        pol_n = self.config['pol_map'][pol]
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        register_name='eq%i'%(2*feng_input)
        n_coeffs = self.config['n_chans']/self.config['eq_decimation']

        if init_coeffs == []: 
            coeffs = self.get_default_eq(ant,pol)
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
        else: raise RuntimeError ('You specified %i coefficients, but there are %i EQ coefficients in this design.'%(len(init_coeffs),n_coeffs))

        if verbose_level>0:
            print 'Writing new coefficient values to config file...'
        self.config.write('equalisation','eq_coeff_%i%c'%(ant,pol),coeffs)

        if verbose_level>0:
            for term,coeff in enumerate(coeffs):
                print '''Initialising EQ for antenna %i%c, input %i on %s (register %s)'s index %i to'''%(ant,pol,feng_input,self.fsrvs[ffpga_n],register_name,term),
                if term==(len(coeffs)-1): print '%i...'%(coeff),
                else: print '%ix^%i +'%(coeff,len(coeffs)-term-1),
                sys.stdout.flush()
            print ''

        if self.config['eq_type'] == 'scalar':
            coeffs    = numpy.real(coeffs) 
            coeff_str = struct.pack('>%iH'%n_coeffs,coeffs)

        elif self.config['eq_type'] == 'complex':
            coeffs    = numpy.array(coeffs,dtype=numpy.complex128)
            coeff_str = struct.pack('>%iH'%(2*n_coeffs),coeffs.view(dtype=numpy.float64))

        if (verbose_level > 1):
            print 'About to set EQ addr %i to %f.'%(chan,gain)
        
        fpga.write(register_name,coeff_str)

    def get_adc_amplitudes(self,ants=[]):
        """Gets the ADC RMS amplitudes from the F engines. If no antennas are specified, return all."""
        if ants == []:
            ants = range(self.config['n_ants'])
        rv = {}
        for ant in ants:
            for pol in self.config['pols']:
                ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
                rv[(ant,pol)]={}
                rv[(ant,pol)]['raw']=self.ffpgas[ffpga_n].read_uint('adc_levels%i'%(feng_input))
                rv[(ant,pol)]['rms']=numpy.sqrt(rv[(ant,pol)]['raw']/self.config['adc_levels_acc_len'])/(2**self.config['adc_bits'])
                if rv[(ant,pol)]['rms'] == 0: rv[(ant,pol)]['bits']=0
                else: rv[(ant,pol)]['bits'] = numpy.log2(rv[(ant,pol)]['rms'] * (2**(self.config['adc_bits'])))

    def issue_spead_metadata(self):
        """ Issues the SPEAD metadata packets containing the payload and options descriptors and unpack sequences."""
        print "NOT IMPLEMENTED YET"
        import spead
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        ig.add_item(name="adc_clk",id=0x1007,
            description="Clock rate of ADC (samples per second).",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['adc_clk'])

        ig.add_item(name="n_chans",id=0x1009,
            description="The total number of frequency channels present in any integration.",
            shape=[], fmt=spead.mkfmt(('u',spead.ADDRSIZE)),init_val=self.config['n_chans'])

        ig.add_item(name="n_bls",id=0x100B,
            description="The total number of baselines in the data product.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_bls'])

        ig.add_item(name="n_stokes",id=0x1040,
            description="Number of Stokes parameters in output.",
            shape=[],fmt=spead.mkfmt(('u',8)),
            init_val=self.config['n_stokes'])

        ig.add_item(name="n_ants",id=0x100A,
            description="The total number of dual-pol antennas in the system.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_ants'])

        ig.add_item(name="xeng_out_bits_per_sample",id=0x1048,
            description="The number of bits per value of the xeng accumulator output. Note this is for a single value, not the combined complex size.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['xeng_sample_bits'])

        ig.additem(name="center_freq",id=0x1011,
            description="The center frequency of the DBE in Hz, 64-bit IEEE floating-point number.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_value=self.config['center_freq'])

        ig.additem(name="bandwidth",id=0x1013,
            description="The analogue bandwidth of the digitally processed signal in Hz.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_value=self.config['bandwidth'])

        ig.additem(name="n_accs",id=0x1015,
            description="The number of spectra that are accumulated per integration.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_value=self.config['acc_len']*self.config['xeng_acc_len'])

        #how to do quantisation scalars?  recommend 1D array of complex numbers

        ig.additem(name="fft_shift",id=0x101E,
            description="The FFT bitshift pattern. F-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_value=self.config['fft_shift'])

        ig.add_item(name="x_per_fpga",id=0x1041,
            description="Number of X engines per FPGA.",
            shape=[],fmt=spead.mkfmt(('u',16)),
            init_val=self.config['x_per_fpga'])
        ig.add_item(name="n_ants_per_xaui",id=0x1042,
            description="Number of antennas' data per XAUI link.",
            shape=[],fmt=spead.mkfmt(('u',32)),
            init_val=self.config['n_ants_per_xaui'])

        ig.add_item(name="ddc_mix_freq",id=0x1043,
            description="Digital downconverter mixing freqency as a fraction of the ADC sampling frequency. eg: 0.25. Set to zero if no DDC is present.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['ddc_mix_freq'])

        ig.add_item(name="ddc_decimation",id=0x1044,
            description="Frequency decimation of the digital downconverter (determines how much bandwidth is processed) eg: 4",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['ddc_decimation'])

        ig.additem(name="xeng_acc_len",id=0x101F,
            description="Number of spectra accumulated inside X engine. Determines minimum integration time and user-configurable integration time stepsize. X-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_value=self.config['xeng_acc_len'])

        ig.additem(name="requant_bits",id=0x1020,
            description="Number of bits after requantisation in the F engines (post FFT and any phasing stages).",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_value=self.config['feng_bits'])

        ig.additem(name="feng_pkt_len",id=0x1021,
            description="Payload size of 10GbE packet exchange between F and X engines in 64 bit words. Usually equal to the number of spectra accumulated inside X engine. F-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_value=self.config['10gbe_pkt_len'])

        ig.add_item(name="rx_udp_port",id=0x1022,
            description="Destination UDP port for X engine output.",
            shape=[],fmt=spead.mkfmt(('u',16)),
            init_val=self.config['rx_udp_port'])

        ig.add_item(name="rx_udp_ip_str",id=0x1024,
            description="Destination IP address for X engine output UDP packets.",
            shape=[-1],fmt=spead.STR_FMT,
            init_val=self.config['rx_udp_ip_str'])

        ig.add_item(name="feng_start_ip",id=0x1025,
            description="F engine starting IP address.",
            shape=[],fmt=spead.mkfmt(('u',32)),
            init_val=self.config['10gbe_ip'])

        ig.add_item(name="feng_udp_port",id=0x1023,
            description="Destination UDP port for F engine data exchange.",
            shape=[],fmt=spead.mkfmt(('u',32)),
            init_val=self.config['10gbe_port'])

        ig.add_item(name="eng_rate",id=0x1026,
            description="Target clock rate of processing engines (xeng).",
            shape=[],fmt=spead.mkfmt(('u',32)),
            init_val=self.config['x_eng_clk'])

        ig.add_item(name="adc_bits",id=0x1045,
            description="ADC quantisation (bits).",
            shape=[],fmt=spead.mkfmt(('u',32)),
            init_val=self.config['adc_bits'])

        tx.send_heap(ig.get_heap())


    def issue_spead_data_descriptor(self):
        """ Issues the SPEAD data descriptors for the HW 10GbE output, to enable receivers to decode the data."""
        import spead
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        ig.add_item(name='complex',id=0x2040,
            description="A complex number consisting of two unsigned integers. (Real,Imag)",
            shape=[],fmt=spead.mkfmt(('u',32),('u',32)))

        ig.add_item(name="baseline",id=0x2041,
            description="An array of all the baselines for a single frequency channel.",
            shape=[self.config['n_bls']],fmt=spead.mkfmt(('0',0x2040)))

        ig.add_item(name="spectrum",id=0x2042,
            description="An array of all the frequency channels in the system (each one consisting of all baselines for a given channel).",
            shape=[self.config['n_chans']],fmt=spead.mkfmt(('0',0x2041)))

        for x in range(self.n_xengs):
            ig.add_item(name=("xeng_raw%i"%x),id=(0x2048+x),
                description="Raw data for xengine %i out of %i. Frequency channels are split amonst xengines. Frequencies are distributed to xengines in a round-robin fashion, starting with engine 0. Data from all X engines must thus be combed or interleaved together to get continuous frequencies. Each xengine calculates all baselines (n_bls given by SPEAD ID 0x100B) for a given frequency channel. For a given baseline, -SPEAD ID 0x1040- stokes parameters are calculated (nominally 4 since xengines are natively dual-polarisation; software remapping is required for single-baseline designs). Each stokes parameter consists of two numbers, real and imaginary, each component of which is given by SPEAD ID     0x1048."%(x,self.config['n_xengs']),
                shape=[self.config['n_xengs']],fmt=spead.mkfmt(('0',0x2040)))

        tx.send_heap(ig.get_heap())

