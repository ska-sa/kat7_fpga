#! /usr/bin/env python
""" 
Selection of commonly-used correlator control functions.
Requires X engine version 330 and F engine 310 or greater.

UNDER CONSTRUCTION

Author: Jason Manley\n
Revisions:\n
2010-08-05: JRM acc_len_set -> acc_n_set. acc_let_set now in seconds.
2010-06-28  JRM Port to use ROACH based F and X engines.
                Changed naming convention for function calls.
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
\n"""

import corr, time, sys, numpy, os, logging, katcp, struct

class Correlator:
    def __init__(self, config_file,log_handler=None):
        self.config = corr.cn_conf.CorrConf(config_file)
        self.xsrvs = self.config['servers_x']
        self.fsrvs = self.config['servers_f']
        self.allsrvs = self.fsrvs + self.xsrvs

        if log_handler == None: log_handler=corr.log_handlers.DebugLogHandler()
        self.log_handler = log_handler
        self.floggers=[logging.getLogger(s) for s in self.fsrvs]
        self.xloggers=[logging.getLogger(s) for s in self.xsrvs]
        self.loggers=self.floggers + self.xloggers
        for logger in (self.floggers+self.xloggers): logger.addHandler(log_handler)

        self.xfpgas=[corr.katcp_wrapper.FpgaClient(server,self.config['katcp_port'],
                       timeout=10,logger=self.xloggers[s]) for s,server in enumerate(self.xsrvs)]
        self.ffpgas=[corr.katcp_wrapper.FpgaClient(server,self.config['katcp_port'],
                       timeout=10,logger=self.floggers[s]) for s,server in enumerate(self.fsrvs)]
        self.allfpgas = self.ffpgas + self.xfpgas

        time.sleep(2)
        if not self.check_katcp_connections():
            self.check_katcp_connections(verbose=True)
            raise RuntimeError("Connection to FPGA boards failed.")

    def __del__(self):
        self.disconnect_all()

    def disconnect_all(self):
        """Stop all TCP KATCP links to all FPGAs defined in the config file."""
        #tested ok corr-0.5.0 2010-07-19
        try:
            for fpga in (self.allfpgas): fpga.stop()
        except:
            pass
    def get_bl_order(self):
        return corr.sim.get_bl_order(self.config['n_ants'])

    def prog_all(self):
        """Programs all the FPGAs."""
        #tested ok corr-0.5.0 2010-07-19
        for fpga in self.ffpgas:
            fpga.progdev(self.config['bitstream_f'])
        for fpga in self.xfpgas:
            fpga.progdev(self.config['bitstream_x'])
            #time.sleep(4)

    def deprog_all(self):
        """Deprograms all the FPGAs."""
        #tested ok corr-0.5.0 2010-07-19
        for fpga in self.ffpgas:
            fpga.progdev('')
        for fpga in self.xfpgas:
            fpga.progdev('')

    def xread_all(self,register,bram_size,offset=0):
        """Reads a register of specified size from all X-engines. Returns a list."""
        rv = [fpga.read(register,bram_size,offset) for fpga in self.xfpgas]
        return rv

    def fread_all(self,register,bram_size,offset=0):
        """Reads a register of specified size from all F-engines. Returns a list."""
        rv = [fpga.read(register,bram_size,offset) for fpga in self.ffpgas]
        return rv

    def xread_uint_all(self, register):
        """Reads a value from register 'register' for all X-engine FPGAs."""
        return [fpga.read_uint(register) for fpga in self.xfpgas]

    def fread_uint_all(self, register):
        """Reads a value from register 'register' for all F-engine FPGAs."""
        return [fpga.read_uint(register) for fpga in self.ffpgas]

    def xwrite_int_all(self,register,value):
        """Writes to a 32-bit software register on all X-engines."""
        [fpga.write_int(register,value) for fpga in self.xfpgas]

    def fwrite_int_all(self,register,value):
        """Writes to a 32-bit software register on all F-engines."""
        [fpga.write_int(register,value) for fpga in self.ffpgas]

    def feng_ctrl_set_all(self, tvg_noise_sel=False, tvg_ct_sel=False, tvg_pkt_sel=False, tvg_ffdel_sel=False, tvg_en=False, arm_rst=False, mrst=False, clr_status=False, soft_sync=False):
        """Writes a value to all the Fengine control registers."""
        value = tvg_noise_sel << 20 | tvg_ffdel_sel<<19 | tvg_pkt_sel<<18 | tvg_ct_sel<<17 | tvg_en<<16 | clr_status<<3 | arm_rst<<2 | soft_sync<<1 | mrst<<0
        self.fwrite_int_all('control',value)

    def feng_ctrl_get_all(self):
        """Reads and decodes the values from all the Fengine control registers."""
        all_values = self.fread_uint_all('control')
        return [{'mrst':bool(value&(1<<0)),
                'soft_sync':bool(value&(1<<1)),
                'arm':bool(value&(1<<2)),
                'tvg_enable':bool(value&(1<<16)),
                'tvg_ct_sel':bool(value&(1<<17)),
                'tvg_pkt_sel':bool(value&(1<<18)),
                'tvg_ffdel_sel':bool(value&(1<<19)),
                'tvg_noise_sel':bool(value&(1<<20)),
                'clr_status':bool(value&(1<<3))} for value in all_values]

    def feng_tvg_sel(self,noise=False,ct=False,pkt=False,ffdel=False):
        """Turns TVGs on/off on the F engines. Will not disturb other control register settings."""
        #stat=self.feng_ctrl_get_all()
        #self.feng_ctrl_set_all(tvg_en=True,  tvg_ct_sel=ct, tvg_pkt_sel=pkt, tvg_ffdel_sel=ffdel, arm_rst=stat['arm_rst'], mrst=stat['mrst'], clr_status=stat['clr_status'], soft_sync=stat['soft_sync'])
        #self.feng_ctrl_set_all(tvg_en=False, tvg_ct_sel=ct, tvg_pkt_sel=pkt, tvg_ffdel_sel=ffdel, arm_rst=stat['arm_rst'], mrst=stat['mrst'], clr_status=stat['clr_status'], soft_sync=stat['soft_sync'])
        self.feng_ctrl_set_all(tvg_en=True,  tvg_noise_sel=noise, tvg_ct_sel=ct, tvg_pkt_sel=pkt, tvg_ffdel_sel=ffdel)
        self.feng_ctrl_set_all(tvg_en=False, tvg_noise_sel=noise, tvg_ct_sel=ct, tvg_pkt_sel=pkt, tvg_ffdel_sel=ffdel)

    def xeng_ctrl_set_all(self,loopback_mux_rst=False, gbe_out_enable=False, gbe_disable=False, cnt_rst=False, gbe_rst=False, vacc_rst=False):
        """Writes a value to all the Xengine control registers."""
        value = gbe_out_enable<<16 | loopback_mux_rst<<10 | gbe_disable<<9 | cnt_rst<<8 | gbe_rst<<15 | vacc_rst<<0
        self.xwrite_int_all('ctrl', value)

    def xeng_ctrl_get_all(self, translate = True):
        """
        Reads and decodes the values from all the X-engine control registers.
        @param translate: boolean, if True will decode the control registers.
        @return a list by X-engine fpga hostname
        """
        values = self.xread_uint_all('ctrl')
        valuesByFpgaHost = [{'fpgaHost':fpga.host, 'ctrlRegister':values[ctr]} for ctr,fpga in enumerate(self.xfpgas)]
        if not translate: return valuesByFpgaHost
        return [{'fpgaHost':value['fpgaHost'],
                 'ctrlRegister':value['ctrlRegister'],
                'gbe_out_enable':bool(value['ctrlRegister']&(1<<16)),
                'gbe_rst':bool(value['ctrlRegister']&(1<<15)),
                'gbe_out_rst':bool(value['ctrlRegister']&(1<<11)),
                'loopback_mux_rst':bool(value['ctrlRegister']&(1<<10)),
                'gbe_disable':bool(value['ctrlRegister']&(1<<9)),
                'cnt_rst':bool(value['ctrlRegister']&(1<<8)),
                'vacc_rst':bool(value['ctrlRegister']&(1<<0))} for value in valuesByFpgaHost]

    def fft_shift_set_all(self,fft_shift=-1):
        """Configure the FFT on all F engines to the specified schedule. If not specified, default to schedule listed in config file."""
        #tested ok corr-0.5.0 2010-07-20
        if fft_shift <0:
            fft_shift = self.config['fft_shift']
        for ant in range(self.config['f_per_fpga']*self.config['n_pols']):
            self.fwrite_int_all("fft_shift%i"%ant,fft_shift)

    def fft_shift_get_all(self):
        rv={}
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
                rv[(ant,pol)]=self.ffpgas[ffpga_n].read_uint('fft_shift%i'%feng_input)
        return rv

    def feng_status_get_all(self):
        """Reads and decodes the status register from all the Fengines."""
        rv={}
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
                value = self.ffpgas[ffpga_n].read_uint('fstatus%i'%feng_input)
                #for xaui_n in range(self.config['n_xaui_per_ffpga
                rv[(ant,pol)]={'xaui_lnkdn':bool(value&(1<<17)),
                                'xaui_over':bool(value&(1<<16)),
                                'ct_error':bool(value&(1<<3)),
                                'adc_overrange':bool(value&(1<<2)),
                                'fft_overrange':bool(value&(1<<1)),
                                'quant_overrange':bool(value&(1<<0))}
        return rv

    def check_feng_clks(self,verbose=False):
        """ Checks all Fengine FPGAs' clk_frequency registers to confirm correct PPS operation. Requires that the system be sync'd."""
        #tested ok corr-0.5.0 2010-07-19
        import stats
        rv=True
       
        #estimate actual clk freq 
        clk_freq=self.feng_clks_get()
        clk_mhz=[round(cf) for cf in clk_freq] #round to nearest MHz
        expect_rate = round(self.config['feng_clk']/1000000) #expected clock rate in MHz.
        for fbrd,fsrv in enumerate(self.fsrvs):
            if clk_freq[fbrd] <= 100: 
                if verbose: print '\tNo clock detected on %s.'%fsrv
                rv=False

            if (clk_mhz[fbrd] > (expect_rate+1)) or (clk_mhz[fbrd] < (expect_rate -1)) or (clk_mhz[fbrd]==0):
               if verbose: print "\tClocks freq on %s is %i MHz, where expected rate is %i MHz."%(fsrv,clk_mhz[fbrd], expect_rate)
               rv=False

        #check long-term integrity
        uptime=[ut[1] for ut in self.feng_uptime()]
        mode = stats.mode(uptime)
        modalmean=stats.mean(mode[1])
        for fbrd,fsrv in enumerate(self.fsrvs):
            if uptime[fbrd] == 0: 
                rv=False
                if verbose: print '\tNo PPS detected on %s.'%fsrv

            if (uptime[fbrd] > (modalmean+1)) or (uptime[fbrd] < (modalmean -1)) or (uptime[fbrd]==0):
                rv=False
                if verbose: print "\tUptime of %s is %i PPS pulses, where modal mean is %i pulses."%(fsrv,uptime[fbrd], modalmean)

        #check the PPS against sampling clock.
        all_values = self.fread_uint_all('clk_frequency')
        mode = stats.mode(all_values)
        modalmean=stats.mean(mode[1])
        modalfreq=numpy.round((expect_rate*1000000.)/modalmean,3)
        if (modalfreq != 1):
            if verbose: print "\tPPS period is approx %3.2f Hz, not 1Hz."%modalfreq
            rv=False

        for fbrd,fsrv in enumerate(self.fsrvs):
            if all_values[fbrd] == 0: 
                if verbose: print '\tNo PPS detected on %s.'%fsrv
                rv=False
            if (all_values[fbrd] > (modalmean+2)) or (all_values[fbrd] < (modalmean -2)) or (all_values[fbrd]==0):
                if verbose: print "\tClocks between PPS pulses on %s is %i, where modal mean is %i."%(fsrv,all_values[fbrd], modalmean)
                rv=False

        return rv

    def feng_uptime(self):
        """Returns a list of tuples of (armed_status and pps_count) for all fengine fpgas. Where the count since last arm of the pps signals received (and hence number of seconds since last arm)."""
        #tested ok corr-0.5.0 2010-07-19
        all_values = self.fread_uint_all('pps_count')
        pps_cnt = [val & 0x7FFFFFFF for val in all_values]
        arm_stat = [bool(val & 0x80000000) for val in all_values]
        return [(arm_stat[fn],pps_cnt[fn]) for fn in range(len(self.ffpgas))]

    def mcnt_current_get(self,ant=None,pol=None):
        "Returns the current mcnt for a given antenna, pol. If not specified, return a list of mcnts for all connected f engine FPGAs"
        #tested ok corr-0.5.0 2010-07-19
        if ant==None and pol==None:
            msw = self.fread_uint_all('mcount_msw')
            lsw = self.fread_uint_all('mcount_lsw')
            mcnt = [(msw[i] << 32) + lsw[i] for i,srv in enumerate(self.fsrvs)]
            return mcnt
        else:
            ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
            msw = self.ffpgas[ffpga_n].read_uint('mcount_msw')
            lsw = self.ffpgas[ffpga_n].read_uint('mcount_lsw')
            return (msw << 32) + lsw 
    
    def pcnt_current_get(self):
        "Returns the current packet count. ASSUMES THE SYSTEM IS SYNC'd!"
        msw = self.ffpgas[0].read_uint('mcount_msw')
        lsw = self.ffpgas[0].read_uint('mcount_lsw')
        return int(((msw << 32) + lsw)*self.config['timestamp_scale_factor']/self.config['mcnt_scale_factor'])
    
    def arm(self,spead_update=True):
        """Arms all F engines, records arm time in config file and issues SPEAD update. Returns the UTC time at which the system was sync'd in seconds since the Unix epoch (MCNT=0)"""
        #tested ok corr-0.5.0 2010-07-19
        #wait for within 100ms of a half-second, then send out the arm signal.
        ready=(int(time.time()*10)%5)==0
        while not ready: 
            ready=(int(time.time()*10)%5)==0
        trig_time=int(numpy.ceil(time.time()+1)) #Syncs on the next second, to ensure any sync pulses already in the datapipeline have a chance to propagate out.
        self.feng_ctrl_set_all(arm_rst=False)
        self.feng_ctrl_set_all(arm_rst=True)
        self.config.write('correlator','sync_time',trig_time)
        self.feng_ctrl_set_all(arm_rst=False)
        time.sleep(2.1)
        armed_stat=[armed[0] for armed in self.feng_uptime()]
        for i,stat in enumerate(armed_stat):
            if armed_stat[i]:
                raise RuntimeError("%s has not triggered."%self.fsrvs[i])
        if spead_update: self.spead_time_meta_issue()
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
        """Resets all error counters on all connected boards."""
        self.xeng_ctrl_set_all(cnt_rst=False)
        self.xeng_ctrl_set_all(cnt_rst=True)
        self.xeng_ctrl_set_all(cnt_rst=False)
        self.feng_ctrl_set_all(clr_status=False)
        self.feng_ctrl_set_all(clr_status=True)
        self.feng_ctrl_set_all(clr_status=False)

    def rst_vaccs(self):
        """Resets all Xengine Vector Accumulators."""
        self.xeng_ctrl_set_all(vacc_rst=False)
        self.xeng_ctrl_set_all(vacc_rst=True)
        self.xeng_ctrl_set_all(vacc_rst=False)

    def xeng_clks_get(self):
        """Returns the approximate clock rate of each X engine FPGA in MHz."""
        #tested ok corr-0.5.0 2010-07-19
        return [fpga.est_brd_clk() for fpga in self.xfpgas]

    def feng_clks_get(self):
        """Returns the approximate clock rate of each F engine FPGA in MHz."""
        #tested ok corr-0.5.0 2010-07-19
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
        """Checks system health. If true, system is operating nominally. If false, you should run the other checks to figure out what's wrong."""
        if (self.check_x_miss() and self.check_vacc() and self.check_loopback_mcnt() and self.check_xaui_error() ):
            return True
        else:
            return False

    def tvg_vacc_sel(self,constant=0,n_values=-1,spike_value=-1,spike_location=0,counter=False):
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


    def tvg_xeng_sel(self,mode=0, user_values=()):
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

    def fr_delay_set(self,ant,pol,delay=0,delay_rate=0,fringe_phase=0,fringe_rate=0,ld_time=-1):
        """Configures a given ant-pol to a delay in seconds using both the coarse and the fine delay. Load time is optional; if not specified, load ASAP. \n
        Notes: \n
        DOES NOT ACCOUNT FOR WRAPPING MCNT.\n
        IS A ONCE-OFF UPDATE (no babysitting by software)\n
        \t Fringe offset is in degrees.\n
        \t Fringe rate is in cycles per second (Hz).\n
        \t Delay is in seconds.\n
        \t Delay rate is in seconds per second."""

        fine_delay_bits=16
        coarse_delay_bits=16
        fine_delay_rate_bits=16
        fringe_offset_bits=16
        fringe_rate_bits=16

        bitshift_schedule=23
        
        min_ld_time = 0.1 #assume we're able to set and check all the registers in 100ms
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)

        #delays in terms of ADC clock cycles:
        delay_n=delay*self.config['adc_clk']    #delay in clock cycles
        #coarse_delay = int(numpy.round(delay_n)) #delay in whole clock cycles #good for rev 369.
        coarse_delay = int(delay_n) #delay in whole clock cycles #testing for rev370
        fine_delay = (delay_n-coarse_delay)    #delay remainder. need a negative slope for positive delay
        fine_delay_i = int(fine_delay*(2**(fine_delay_bits-1)))  #16 bits of signed data over range -pi to +pi
    
        fine_delay_rate=int(float(delay_rate) * (2**(bitshift_schedule + fine_delay_rate_bits-1))) 

        #figure out the fringe as a fraction of a cycle        
        fr_offset=int(fringe_phase/float(360) * (2**(fringe_offset_bits)))
        #figure out the fringe rate. Input is in cycles per second (Hz). 1) divide by brd clock rate to get cycles per clock. 2) multiply by 2**20
        fr_rate = int(float(fringe_rate) / self.config['feng_clk'] * (2**(bitshift_schedule + fringe_rate_bits-1)))

        #get the current mcnt for this feng:
        mcnt=self.mcnt_current_get(ant,pol)

        cnts=self.ffpgas[ffpga_n].read_uint('delay_tr_status%i'%feng_input)
        arm_cnt0=cnts>>16
        ld_cnt0=cnts&0xffff

        act_delay=(coarse_delay + float(fine_delay_i)/2**fine_delay_bits)/self.config['adc_clk']
        act_fringe_offset = float(fr_offset)/(2**fringe_offset_bits)*360 
        act_fringe_rate = float(fr_rate)/(2**(fringe_rate_bits+bitshift_schedule-1))*self.config['feng_clk']
        act_delay_rate = float(fine_delay_rate)/(2**(bitshift_schedule + fringe_rate_bits-1))

        if (fringe_phase !=0):
            if (fr_offset == 0): self.floggers[ffpga_n].error('Requested fringe phase is too small for this configuration (we do not have enough resolution).')
            else: self.floggers[ffpga_n].warn('Fringe offset actually set to %6.3f degrees.'%act_fringe_offset)

        if (fringe_rate != 0):
            if (fr_rate==0): self.floggers[ffpga_n].error('Requested fringe rate is too slow for this configuration.')
            else: self.floggers[ffpga_n].warn('Fringe rate actually set to %e Hz.'%act_fringe_rate)
        if (delay_rate != 0):
            print 'DELAY RATE IS NOT YET IMPLEMENTED!'
            print 'fine delay rate worked out to',fine_delay_rate
            if (fine_delay_rate==0): self.floggers[ffpga_n].error('Requested delay rate too slow for this configuration.')
            if (abs(fine_delay_rate) > 2**(fine_delay_rate_bits-1)): 
                self.floggers[ffpga_n].error('Requested delay rate out of range (-%e to +%e).'%((2**(fine_delay_rate_bits-bitshift_schedule-1)),(2**(fine_delay_rate_bits-bitshift_schedule-1))))
                fine_delay_rate_i=0
            else: self.floggers[ffpga_n].warn('Delay rate actually set to %e seconds per second.'%act_delay_rate) 
        if (delay != 0):
            if (fine_delay_i==0) and (coarse_delay==0): 
                self.floggers[ffpga_n].error('Requested delay is too small for this configuration (our resolution is too low).')
            elif abs(fine_delay_i) > 2**(fine_delay_bits-1): 
                self.floggers[ffpga_n].error('Internal logic error calculating fine delays.')
                fine_delay=0
            if abs(coarse_delay) > (2**(coarse_delay_bits)): 
                self.floggers[ffpga_n].error('Requested delay is out of range (-%e to +%e).'%((2**(coarse_delay_bits-1))/self.config['adc_clk']))
            else: self.floggers[ffpga_n].warn('Delay actually set to %e seconds.'%act_delay)

        #figure out the load time
        if ld_time < 0: 
            #figure out the load-time mcnt:
            ld_mcnt=int(mcnt + self.config['mcnt_scale_factor']*(min_ld_time))
        else:
            ld_mcnt=self.mcnt_from_time(ld_time)
        if (ld_mcnt < (mcnt +  self.config['mcnt_scale_factor']*min_ld_time)): raise RuntimeError("Cannot load at a time in the past.")
        
        #setup the delays:
        self.ffpgas[ffpga_n].write_int('coarse_delay%i'%feng_input,coarse_delay)
        #fine delay (LSbs) is fraction of a cycle * 2^15 (16 bits allocated, signed integer). 
        #increment fine_delay by MSbs much every FPGA clock cycle shifted 2**20???
        self.ffpgas[ffpga_n].write('a1_fd%i'%feng_input,struct.pack('>hh',fine_delay_rate,fine_delay_i))
        
        #print 'Coarse delay: %i, fine delay: %2.3f (%i), delay_rate: %2.2f (%i).'%(coarse_delay,fine_delay,fine_delay_i,delay_rate,fine_delay_rate)

        #setup the fringe rotation
        #LSbs is offset as a fraction of a cycle in fix_16_15 (1 = pi radians ; -1 = -1radians). 
        #MSbs is fringe rate as fractional increment to fr_offset per FPGA clock cycle as fix_16.15. FPGA divides this rate by 2**20 internally.
        self.ffpgas[ffpga_n].write('a0_fd%i'%feng_input,struct.pack('>hh',fr_rate,fr_offset))  
        print 'Phase offset: %2.3f (%i), phase rate: %2.3f (%i).'%(fringe_phase,fr_offset,fringe_rate,fr_rate)

        #set the load time:
        self.ffpgas[ffpga_n].write_int('ld_time_lsw%i'%feng_input,(ld_mcnt&0xffffffff))
        self.ffpgas[ffpga_n].write_int('ld_time_msw%i'%feng_input,(ld_mcnt>>32)|(1<<31))
        self.ffpgas[ffpga_n].write_int('ld_time_msw%i'%feng_input,(ld_mcnt>>32)&0x7fffffff)

        #check that it loaded correctly:
        #wait 'till the time has elapsed
        sleep_time=self.time_from_mcnt(ld_mcnt) - self.time_from_mcnt(mcnt)
        time.sleep(sleep_time)
        #print 'waiting %2.3f seconds'%sleep_time

        cnts=self.ffpgas[ffpga_n].read_uint('delay_tr_status%i'%feng_input)
        if (arm_cnt0 == (cnts>>16)): 
            if (cnts>>16)==0: raise RuntimeError('Ant %i%s (Feng %i on %s) appears to be held in master reset.'%(ant,pol,feng_input,c.fsrvs[ffpga_n]))
            else: raise RuntimeError('Ant %i%s (Feng %i on %s) did not arm.'%(ant,pol,feng_input,c.fsrvs[ffpga_n]))
        if (ld_cnt0 >= (cnts&0xffff)): 
            after_mcnt=self.mcnt_current_get(ant,pol) 
            #print 'before: %i, target: %i, after: %i'%(mcnt,ld_mcnt,after_mcnt)
            #print 'start: %10.3f, target: %10.3f, after: %10.3f'%(self.time_from_mcnt(mcnt),self.time_from_mcnt(ld_mcnt),self.time_from_mcnt(after_mcnt))
            if after_mcnt > ld_mcnt: raise RuntimeError('We missed loading the registers by about %4.1f ms.'%((after_mcnt-ld_mcnt)/self.config['mcnt_scale_factor']*1000))
            else: raise RuntimeError('Ant %i%s (Feng %i on %s) did not load correctly for an unknown reason.'%(ant,pol,feng_input,self.fsrvs[ffpga_n]))

    def time_from_mcnt(self,mcnt):
        """Returns the unix time UTC equivalent to the input MCNT."""
        return self.config['sync_time']+float(mcnt)/self.config['mcnt_scale_factor']
        
    def mcnt_from_time(self,time_seconds):
        """Returns the mcnt of the correlator from a given UTC system time (seconds since Unix Epoch)."""
        return int((time_seconds - self.config['sync_time'])*self.config['mcnt_scale_factor'])

        #print 'Current Feng mcnt: %16X, uptime: %16is, target mcnt: %16X (%16i)'%(current_mcnt,uptime,target_pkt_mcnt,target_pkt_mcnt)
        
    def time_from_pcnt(self,pcnt):
        """Returns the unix time UTC equivalent to the input packet timestamp."""
        return self.config['sync_time']+float(pcnt)/float(self.config['timestamp_scale_factor'])
        
    def pcnt_from_time(self,time_seconds):
        """Returns the packet timestamp from a given UTC system time (seconds since Unix Epoch)."""
        return int((time_seconds - self.config['sync_time'])*self.config['timestamp_scale_factor'])

    def acc_n_set(self,n_accs=-1,spead_update=True):
        """Set the Accumulation Length (in # of spectrum accumulations). If not specified, get the config from the config file."""
        if n_accs<0: n_accs=self.config['acc_len']
        n_accs = int(n_accs / self.config['xeng_acc_len'])
        self.xwrite_int_all('acc_len', n_accs)
        self.config.write('correlator','acc_len',n_accs)
        self.vacc_sync() #this is needed in case we decrease the accumulation period on a new_acc transition where some vaccs would then be out of sync
        self.config.calc_int_time()
        if spead_update: self.spead_time_meta_issue()

    def acc_time_set(self,acc_time=-1):
        """Set the accumulation time in seconds. If not specified, use the default from the config file."""
        if acc_time<0: acc_time=self.config['int_time']
        n_accs = acc_time * self.config['bandwidth']/self.config['n_chans'] 
        self.acc_n_set(n_accs=n_accs)

    def feng_brd_id_set(self):
        """Sets the F engine boards' antenna indices. (Numbers the base_ant software register.)"""
        for f,fpga in enumerate(self.ffpgas):
            fpga.write_int('board_id', f)

    def xeng_brd_id_set(self):
        """Sets the X engine boards' antenna indices."""
        for x in range(self.config['x_per_fpga']):
            for f,fpga in enumerate(self.xfpgas):
                fpga.write_int('inst_xeng_id%i'%x,x*len(self.xfpgas)+f)


    def get_ant_location(self, ant, pol='x'):
        " Returns the (ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input) location for a given antenna. Ant is integer, as are all returns."
        #tested ok corr-0.5.0 2010-07-19
        if ant > self.config['n_ants']: 
            raise RuntimeError("There is no antenna %i in this design (total %i antennas)."%(ant,self.config['n_ants']))
        xfpga_n  = ant/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_xfpga']
        ffpga_n  = ant/self.config['n_ants_per_xaui']/self.config['n_xaui_ports_per_ffpga']
        xxaui_n  = ant/self.config['n_ants_per_xaui']%self.config['n_xaui_ports_per_xfpga']
        fxaui_n  = ant/self.config['n_ants_per_xaui']%self.config['n_xaui_ports_per_ffpga']
        feng_input = ant%(self.config['f_per_fpga'])*self.config['n_pols'] + self.config['pol_map'][pol]
        return (ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input)

    def udp_exchange_port_set(self):
        """Set the UDP TX port for internal correlator data exchange."""
        self.xwrite_int_all('gbe_port', self.config['10gbe_port'])

    def config_roach_10gbe_ports(self):
        """Configures 10GbE ports on roach X engines for correlator data exchange using TGTAP."""
        for f,fpga in enumerate(self.xfpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                start_addr=self.config['10gbe_ip']
                start_port=self.config['10gbe_port']
                mac,ip,port=self.get_roach_gbe_conf(start_addr,(f*self.config['n_xaui_ports_per_xfpga']+x),start_port)
                fpga.tap_start('gbe%i'%x,'gbe%i'%x,mac,ip,port)
                # THIS LINE SHOULD NOT BE REQUIRED WITH DAVE'S UPCOMING 10GBE CORE MODS
                # Assign an IP address to each XAUI port's associated 10GbE core.
                fpga.write_int('gbe_ip%i'%x, ip)
                
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
                # THIS LINE SHOULD NOT BE REQUIRED WITH DAVE'S UPCOMING 10GBE CORE MODS
                # Assign an IP address to each XAUI port's associated 10GbE core.
                fpga.write_int('gbe_ip%i'%x, ip)

    def config_udp_output(self):
        """Configures the X engine 10GbE output cores. CURRENTLY DISABLED."""
        self.xwrite_int_all('gbe_out_ip_addr',self.config['rx_udp_ip'])
        self.xwrite_int_all('gbe_out_port',self.config['rx_udp_port'])
        self.xwrite_int_all('gbe_out_pkt_len',self.config['rx_pkt_payload_len'])
        for x in range(self.config['x_per_fpga']):
            for f,fpga in enumerate(self.xfpgas):
                #Temporary for correlators with separate gbe core for output data:
                ip_offset=self.config['10gbe_ip']+len(self.xfpgas)*self.config['x_per_fpga']
                mac,ip,port=self.get_roach_gbe_conf(ip_offset,(f*self.config['n_xaui_ports_per_xfpga']+x),self.config['rx_udp_port'])
                fpga.tap_start('gbe_out%i'%x,mac,ip,port)

    def enable_udp_output(self):
        self.xeng_ctrl_set_all(gbe_out_enable=True)

    def disable_udp_output(self):
        self.xeng_ctrl_set_all(gbe_out_enable=False)

    def deconfig_roach_10gbe_ports(self):
        """Stops tgtap drivers for the X engines."""
        for f,fpga in enumerate(self.xfpgas):
            for x in range(self.config['n_xaui_ports_per_xfpga']):
                fpga.tap_stop('gbe%i'%x)

    def vacc_sync(self,ld_time=-1):
        """Arms all vector accumulators to start accumulating at a given time. If no time is specified, after about a second from now."""
        min_ld_time=0.5

        arm_cnt0={}
        ld_cnt0={}
        for loc_xeng_n in range(self.config['x_per_fpga']):
            for xf_n,srv in enumerate(self.xsrvs):
                xeng_n = loc_xeng_n * self.config['x_per_fpga'] + xf_n
                cnts=self.xfpgas[xf_n].read_uint('vacc_ld_status%i'%loc_xeng_n)
                arm_cnt0[xeng_n]=cnts>>16
                ld_cnt0[xeng_n]=cnts&0xffff

        pcnt=self.pcnt_current_get()
        #figure out the load time
        if ld_time < 0:
            #figure out the load-time pcnt:
            ld_pcnt=int(pcnt + self.config['timestamp_scale_factor']*(min_ld_time))
        else:
            ld_pcnt=self.pcnt_from_time(ld_time)

        if (ld_pcnt < (pcnt + self.config['timestamp_scale_factor']*min_ld_time)): raise RuntimeError("Cannot load at a time in the past.")

        #round to the nearest spectrum cycle. this is: n_ants*(n_chans_per_xeng)*(xeng_acc_len) clock cycles. pcnts themselves are rounded to nearest xeng_acc_len.
        round_target=self.config['n_ants']*self.config['n_chans']/self.config['n_xeng']
        #However, hardware rounds to n_chans, irrespective of anything else (oops!).
        ld_pcnt=(ld_pcnt/self.config['n_chans'])*self.config['n_chans']

        self.xwrite_int_all('vacc_time_lsw',(ld_pcnt&0xffffffff))
        self.xwrite_int_all('vacc_time_msw',(ld_pcnt>>32)+1<<31)
        self.xwrite_int_all('vacc_time_msw',(ld_pcnt>>32)+0<<31)

        #wait 'till the time has elapsed
        time.sleep(self.time_from_pcnt(ld_pcnt) - self.time_from_pcnt(pcnt))
        after_pcnt=self.pcnt_current_get()
        time.sleep(0.2) #acount for a crazy network latency
        #print 'waiting %2.3f seconds'%sleep_time

        for loc_xeng_n in range(self.config['x_per_fpga']):
            for xf_n,srv in enumerate(self.xsrvs):
                xeng_n = loc_xeng_n * self.config['x_per_fpga'] + xf_n
                cnts=self.xfpgas[xf_n].read_uint('vacc_ld_status%i'%loc_xeng_n)
                if ((cnts>>16)==0): 
                    raise RuntimeError('Xeng %i on %s appears to be held in reset.'%(loc_xeng_n,srv))
                if (arm_cnt0[xeng_n] == (cnts>>16)): 
                    raise RuntimeError('Xeng %i on %s did not arm.'%(loc_xeng_n,srv))
                if (ld_cnt0[xeng_n] >= (cnts&0xffff)): 
                    print 'before: %i, target: %i, after: %i'%(pcnt,ld_pcnt,after_pcnt)
                    print 'start: %10.3f, target: %10.3f, after: %10.3f'%(self.time_from_pcnt(pcnt),self.time_from_pcnt(ld_pcnt),self.time_from_pcnt(after_pcnt))
                    if after_pcnt > ld_pcnt: raise RuntimeError('We missed loading the registers by about %4.1f ms.'%((after_pcnt-ld_pcnt)/self.config['timestamp_scale_factor']* 1000))
                    else: raise RuntimeError('Xeng %i on %s did not load correctly for an unknown reason.'%(loc_xeng_n,srv))
                    

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
            print 'Capturing from snap offset',offset
            self.xwrite_int_all(dev_name+'_trig_offset',offset)

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

    def fsnap_all(self,dev_name,brams,man_trig=False,man_valid=False,wait_period=1,offset=-1,circular_capture=False):
        """Triggers and retrieves data from the a snap block device on all the F engines. Depending on the hardware capabilities, it can optionally capture with an offset. The actual captured length and starting offset is returned with the dictionary of data for each FPGA (useful if you've done a circular capture and can't calculate this yourself).\n
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
            self.fwrite_int_all(dev_name+'_trig_offset',offset)
            #print 'Capturing from snap offset %i'%offset

        #print 'Triggering Capture...',
        self.fwrite_int_all(dev_name+'_ctrl',(0 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))
        self.fwrite_int_all(dev_name+'_ctrl',(1 + (man_trig<<1) + (man_valid<<2) + (circular_capture<<3)))

        done=False
        start_time=time.time()
        while not (done and (offset>0 or circular_capture)) and ((time.time()-start_time)<wait_period): 
            addr      = self.fread_uint_all(dev_name+'_addr')
            done_list = [not bool(i & 0x80000000) for i in addr]
            if (done_list == [True for i in self.fsrvs]): done=True
        bram_sizes=[i&0x7fffffff for i in self.fread_uint_all(dev_name+'_addr')]
        bram_dmp={'lengths':numpy.add(bram_sizes,1)}
        bram_dmp['offsets']=[0 for f in self.ffpgas]
        #print 'Addr+1:',bram_dmp['lengths']
        for f,fpga in enumerate(self.ffpgas):
            if (bram_sizes[f] != fpga.read_uint(dev_name+'_addr')&0x7fffffff) or bram_sizes[f]==0:
                #if address is still changing, then the snap block didn't finish capturing. we return empty.  
                print "Looks like snap block on %s didn't finish."%self.fsrvs[f]
                bram_dmp['lengths'][f]=0
                bram_dmp['offsets'][f]=0
                bram_sizes[f]=0

        if (circular_capture or (offset>=0)) and not man_trig:
            bram_dmp['offsets']=numpy.subtract(numpy.add(self.fread_uint_all(dev_name+'_tr_en_cnt'),offset),bram_sizes)
            #print 'Valids since offset trig:',self.read_uint_all(dev_name+'_tr_en_cnt')
            #print 'offsets:',bram_dmp['offsets']
        else: bram_dmp['offsets']=[0 for f in self.ffpgas]
    
        for f,fpga in enumerate(self.ffpgas):
            if (bram_dmp['offsets'][f] < 0):  
                raise RuntimeError('SNAP block hardware or logic failure happened. Returning no data.')
                bram_dmp['lengths'][f]=0
                bram_dmp['offsets'][f]=0
                bram_sizes[f]=0

        for b,bram in enumerate(brams):
            bram_path = dev_name+'_'+bram
            bram_dmp[bram]=[]
            for f,fpga in enumerate(self.ffpgas):
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

    def rf_gain_set(self,ant,pol,gain=None):
        """Enables the RF switch and configures the RF attenuators on KATADC boards. pol is ['x'|'y']. \n
        \t KATADC's valid range is -11.5 to 20dB. \n
        \t If no gain is specified, use the defaults from the config file."""
        #tested ok corr-0.5.0 2010-07-19
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        if gain == None:
            gain = self.config['rf_gain_%i%c'%(ant,pol)] 
        if gain > 20 or gain < -11.5: raise RuntimeError("Invalid gain setting of %i. Valid range for KATADC is -11.5 to +20")
        self.ffpgas[ffpga_n].write_int('adc_ctrl%i'%feng_input,(1<<31)+int((20-gain)*2))
        self.config.write('equalisation','rf_gain_%i%c'%(ant,pol),gain)

    def rf_status_get(self,ant,pol):
        """Grabs the current value of the RF attenuators and RF switch state for KATADC boards. return (enabled,gain in dB) pol is ['x'|'y']"""
        #tested ok corr-0.5.0 2010-07-19
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        value = self.ffpgas[ffpga_n].read_uint('adc_ctrl%i'%feng_input)
        return (bool(value&(1<<31)),20.0-(value&0x3f)*0.5)

    def rf_status_get_all(self):
        """Grabs the current status of the RF chain on all KATADC boards."""
        #RF switch is in MSb.
        #tested ok corr-0.5.0 2010-07-19
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        rv={}
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                rv[(ant,pol)]=self.rf_status_get(ant,pol)
        return rv

    def rf_gain_set_all(self,gain=None):
        """Sets the RF gain configuration of all inputs to "gain". If no level is given, use the defaults from the config file."""
        #tested ok corr-0.5.0 2010-07-19
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported."%self.config['adc_type'])
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                self.rf_gain_set(ant,pol,gain)

    def rf_disable(self,ant,pol):
        """Disable the RF switch on KATADC boards. pol is ['x'|'y']"""
        #tested ok corr-0.5.0 2010-08-07
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported at this time."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        self.ffpgas[ffpga_n].write_int('adc_ctrl%i'%feng_input,self.ffpgas[ffpga_n].read_uint('adc_ctrl%i'%feng_input)&0x7fffffff)

    def rf_enable(self,ant,pol):
        """Enable the RF switch on KATADC boards. pol is ['x'|'y']"""
        #tested ok corr-0.5.0 2010-08-07
        #RF switch is in MSb.
        if self.config['adc_type'] != 'katadc' : raise RuntimeError("Unsupported ADC type of %s. Only katadc is supported at this time."%self.config['adc_type'])
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        self.ffpgas[ffpga_n].write_int('adc_ctrl%i'%feng_input,self.ffpgas[ffpga_n].read_uint('adc_ctrl%i'%feng_input)|0x80000000)

    def eq_set_all(self,verbose=False,init_poly=[],init_coeffs=[]):
        """Initialise all connected Fengines' EQs to given polynomial. If no polynomial or coefficients are given, use defaults from config file."""
        #tested ok corr-0.5.0 2010-08-07
        for ant in range(self.config['n_ants']):
            for pol in self.config['pols']:
                self.eq_spectrum_set(ant=ant,pol=pol,verbose=verbose,init_coeffs=init_coeffs,init_poly=init_poly)

    def eq_default_get(self,ant,pol,verbose=False):
        "Fetches the default equalisation configuration from the config file and returns a list of the coefficients for a given input. pol is ['x'|'y']" 
        #tested ok corr-0.5.0 2010-08-07
        n_coeffs = self.config['n_chans']/self.config['eq_decimation']

        if self.config['eq_default'] == 'coeffs':
            equalisation = self.config['eq_coeffs_%i%c'%(ant,pol)]

        elif self.config['eq_default'] == 'poly':
            poly = self.config['eq_poly_%i%c'%(ant,pol)]
            equalisation = numpy.polyval(poly, range(self.config['n_chans']))[self.config['eq_decimation']/2::self.config['eq_decimation']]
            if self.config['eq_type']=='complex':
                equalisation = [eq+0*1j for eq in equalisation]

        if verbose:
            for term,coeff in enumerate(equalisation):
                print '''Retrieved default EQ (%s) for antenna %i%c: '''%(ant,pol,self.config['eq_default']),
                if term==(len(coeffs)-1): print '%i...'%(coeff),
                else: print '%ix^%i +'%(coeff,len(coeffs)-term-1),
                sys.stdout.flush()
            print ''
                
        if len(equalisation) != n_coeffs: raise RuntimeError("Something's wrong. I have %i eq coefficients when I should have %i."%(len(equalisation),n_coeffs))
        return equalisation

    def eq_spectrum_get(self,ant,pol):
        """Retrieves the equaliser settings currently programmed in an F engine for the given antenna,polarisation. Assumes equaliser of 16 bits. Returns an array of length n_chans."""
        
        #tested ok corr-0.5.0 2010-08-07
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        register_name='eq%i'%(feng_input)
        n_coeffs = self.config['n_chans']/self.config['eq_decimation']

        if self.config['eq_type'] == 'scalar':
            bd=self.ffpgas[ffpga_n].read(register_name,n_coeffs*2)
            coeffs=numpy.array(struct.unpack('>%ih'%n_coeffs,bd))
            nacexp=(numpy.reshape(coeffs,(n_coeffs,1))*numpy.ones((1,self.config['eq_decimation']))).reshape(self.config['n_chans'])
            return nacexp
            
        elif self.config['eq_type'] == 'complex':
            bd=self.ffpgas[ffpga_n].read(register_name,n_coeffs*4)
            coeffs=struct.unpack('>%ih'%(n_coeffs*2),bd)
            na=numpy.array(coeffs,dtype=numpy.float64)
            nac=na.view(dtype=numpy.complex128)
            nacexp=(numpy.reshape(nac,(n_coeffs,1))*numpy.ones((1,self.config['eq_decimation']))).reshape(self.config['n_chans'])
            return nacexp
            
        else: raise RuntimeError("Unable to interpret eq_type. Expecting scalar or complex.")

    def eq_spectrum_set(self,ant,pol,verbose=False,init_coeffs=[],init_poly=[]):
        """Set a given antenna and polarisation equaliser to given co-efficients. pol is 'x' or 'y'. ant is integer in range n_ants. Assumes equaliser of 16 bits. init_coeffs is list of length n_chans/decimation_factor."""
        #tested ok corr-0.5.0 2010-08-07
        ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
        fpga=self.ffpgas[ffpga_n]
        pol_n = self.config['pol_map'][pol]
        register_name='eq%i'%(feng_input)
        n_coeffs = self.config['n_chans']/self.config['eq_decimation']

        if init_coeffs == [] and init_poly == []: 
            coeffs = self.eq_default_get(ant,pol)
        elif len(init_coeffs) == n_coeffs:
            coeffs = init_coeffs
        elif len(init_coeffs)>0: 
            raise RuntimeError ('You specified %i coefficients, but there are %i EQ coefficients in this design.'%(len(init_coeffs),n_coeffs))
        else:
            coeffs = numpy.polyval(init_poly, range(self.config['n_chans']))[self.config['eq_decimation']/2::self.config['eq_decimation']]

        if verbose:
            print 'Writing new coefficient values to config file...'
            #print coeffs
        self.config.write('equalisation','eq_coeff_%i%c'%(ant,pol),coeffs)

        if self.config['eq_type'] == 'scalar':
            coeffs    = numpy.real(coeffs) 
            coeff_str = struct.pack('>%iH'%n_coeffs,coeffs)
        elif self.config['eq_type'] == 'complex':
            coeffs    = numpy.array(coeffs,dtype=numpy.complex128)
            coeff_str = struct.pack('>%ih'%(2*n_coeffs),*coeffs.view(dtype=numpy.float64))
        else: raise RuntimeError('EQ type not supported.')

        if verbose:
            for term,coeff in enumerate(coeffs):
                print '''Initialising EQ for antenna %i%c, input %i on %s (register %s)'s index %i to '''%(ant,pol,feng_input,self.fsrvs[ffpga_n],register_name,term),coeff

        fpga.write(register_name,coeff_str)

    def adc_amplitudes_get(self,ants=[]):
        """Gets the ADC RMS amplitudes from the F engines. If no antennas are specified, return all."""
        if ants == []:
            ants = range(self.config['n_ants'])
        rv = {}
        for ant in ants:
            for pol in self.config['pols']:
                ffpga_n,xfpga_n,fxaui_n,xxaui_n,feng_input = self.get_ant_location(ant,pol)
                rv[(ant,pol)]={}
                rv[(ant,pol)]['raw']=self.ffpgas[ffpga_n].read_uint('adc_sum_sq%i'%(feng_input))
                #here we have adc_bits -1 because the device outputs signed values in range -1 to +1, but rms range is 0 to 1(ok, sqrt(2)) so one bit is "wasted" on sign indication.
                rv[(ant,pol)]['rms']=numpy.sqrt(rv[(ant,pol)]['raw']/float(self.config['adc_levels_acc_len']))/(2**(self.config['adc_bits']-1))
                if rv[(ant,pol)]['rms'] == 0: rv[(ant,pol)]['bits']=0
                else: rv[(ant,pol)]['bits'] = numpy.log2(rv[(ant,pol)]['rms'] * (2**(self.config['adc_bits'])))
                if rv[(ant,pol)]['bits'] < 0: rv[(ant,pol)]['bits']=0
        return rv

    def spead_static_meta_issue(self):
        """ Issues the SPEAD metadata packets containing the payload and options descriptors and unpack sequences."""
        import spead
        #tested ok corr-0.5.0 2010-08-07
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        ig.add_item(name="adc_clk",id=0x1007,
            description="Clock rate of ADC (samples per second).",
            shape=[],fmt=spead.mkfmt(('u',64)),
            init_val=self.config['adc_clk'])

        ig.add_item(name="n_bls",id=0x1008,
            description="The total number of baselines in the data product.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_bls'])

        ig.add_item(name="n_chans",id=0x1009,
            description="The total number of frequency channels present in any integration.",
            shape=[], fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_chans'])

        ig.add_item(name="n_ants",id=0x100A,
            description="The total number of dual-pol antennas in the system.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_ants'])

        ig.add_item(name="n_xengs",id=0x100B,
            description="The total number of X engines in the system.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_xeng'])

        ig.add_item(name="center_freq",id=0x1011,
            description="The center frequency of the DBE in Hz, 64-bit IEEE floating-point number.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['center_freq'])

        ig.add_item(name="bandwidth",id=0x1013,
            description="The analogue bandwidth of the digitally processed signal in Hz.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['bandwidth'])

        
        #1015/1016 are taken (see time_metadata_issue below)

        ig.add_item(name="fft_shift",id=0x101E,
            description="The FFT bitshift pattern. F-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['fft_shift'])

        ig.add_item(name="xeng_acc_len",id=0x101F,
            description="Number of spectra accumulated inside X engine. Determines minimum integration time and user-configurable integration time stepsize. X-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['xeng_acc_len'])

        ig.add_item(name="requant_bits",id=0x1020,
            description="Number of bits after requantisation in the F engines (post FFT and any phasing stages).",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['feng_bits'])

        ig.add_item(name="feng_pkt_len",id=0x1021,
            description="Payload size of 10GbE packet exchange between F and X engines in 64 bit words. Usually equal to the number of spectra accumulated inside X engine. F-engine correlator internals.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['10gbe_pkt_len'])

        ig.add_item(name="rx_udp_port",id=0x1022,
            description="Destination UDP port for X engine output.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['rx_udp_port'])

        ig.add_item(name="feng_udp_port",id=0x1023,
            description="Destination UDP port for F engine data exchange.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['10gbe_port'])

#        ig.add_item(name="rx_udp_ip_str",id=0x1024,
#            description="Destination IP address for X engine output UDP packets.",
#            shape=[-1],fmt=spead.STR_FMT,
#            init_val=self.config['rx_udp_ip_str'])

        ig.add_item(name="feng_start_ip",id=0x1025,
            description="F engine starting IP address.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['10gbe_ip'])

        ig.add_item(name="xeng_rate",id=0x1026,
            description="Target clock rate of processing engines (xeng).",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['xeng_clk'])

        ig.add_item(name="n_stokes",id=0x1040,
            description="Number of Stokes parameters in output.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_stokes'])

        ig.add_item(name="x_per_fpga",id=0x1041,
            description="Number of X engines per FPGA.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['x_per_fpga'])

        ig.add_item(name="n_ants_per_xaui",id=0x1042,
            description="Number of antennas' data per XAUI link.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_ants_per_xaui'])

        ig.add_item(name="ddc_mix_freq",id=0x1043,
            description="Digital downconverter mixing freqency as a fraction of the ADC sampling frequency. eg: 0.25. Set to zero if no DDC is present.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['ddc_mix_freq'])

        ig.add_item(name="ddc_decimation",id=0x1044,
            description="Frequency decimation of the digital downconverter (determines how much bandwidth is processed) eg: 4",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['ddc_decimation'])

        ig.add_item(name="adc_bits",id=0x1045,
            description="ADC quantisation (bits).",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['adc_bits'])

        ig.add_item(name="scale_factor_timestamp",id=0x1046,
            description="Timestamp scaling factor. Divide the SPEAD data packet timestamp by this number to get back to seconds since last sync.",
            shape=[],fmt=spead.mkfmt(('u',64)),
            init_val=self.config['timestamp_scale_factor'])

        ig.add_item(name="xeng_out_bits_per_sample",id=0x1048,
            description="The number of bits per value of the xeng accumulator output. Note this is for a single value, not the combined complex size.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['xeng_sample_bits'])

        tx.send_heap(ig.get_heap())

    def spead_time_meta_issue(self):
        """Issues a SPEAD packet to notify the receiver that we've resync'd the system, acc len has changed etc."""
        #tested ok corr-0.5.0 2010-08-07
        import spead
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        ig.add_item(name="n_accs",id=0x1015,
            description="The number of spectra that are accumulated per integration.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['n_accs'])

        ig.add_item(name="int_time",id=0x1016,
            description="Approximate (it's a float!) integration time per accumulation in seconds.",
            shape=[],fmt=spead.mkfmt(('f',64)),
            init_val=self.config['int_time'])

        ig.add_item(name='sync_time',id=0x1027,
            description="Time at which the system was last synchronised (armed and triggered by a 1PPS) in seconds since the Unix Epoch.",
            shape=[],fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
            init_val=self.config['sync_time'])

        tx.send_heap(ig.get_heap())

    def spead_eq_meta_issue(self):
        """Issues a SPEAD heap for the RF gain and EQ settings."""
        import spead
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        for ant in range(self.config['n_ants']):
            for pn,pol in enumerate(self.config['pols']):
                ig.add_item(name="rf_gain_%i%c"%(ant,pol),id=0x1200+ant*self.config['n_pols']+pn,
                    description="The analogue RF gain applied at the ADC for input %i%c in dB."%(ant,pol),
                    shape=[],fmt=spead.mkfmt(('f',64)),
                    init_val=self.config['rf_gain_%i%c'%(ant,pol)])

                ig.add_item(name="eq_coef_%i%c"%(ant,pol),id=0x1400+ant*self.config['n_pols']+pn,
                    description="The digital amplitude scaling prior to requantisation post-FFT for input %i%c. Unitless."%(ant,pol),
                    init_val=self.config['eq_coeffs_%i%c'%(ant,pol)])

        tx.send_heap(ig.get_heap())


    def spead_data_descriptor_issue(self):
        """ Issues the SPEAD data descriptors for the HW 10GbE output, to enable receivers to decode the data."""
        #tested ok corr-0.5.0 2010-08-07
        import spead
        tx=spead.Transmitter(spead.TransportUDPtx(self.config['rx_udp_ip_str'],self.config['rx_udp_port']))
        ig=spead.ItemGroup()

        if self.config['xeng_sample_bits'] != 32: raise RuntimeError("Invalid bitwidth of X engine output. You specified %i, but I'm hardcoded for 32."%self.config['xeng_sample_bits'])

        for x in range(self.config['n_xeng']):
            ig.add_item(name=('timestamp%i'%x), id=0x1600+x,
                description='Timestamp of start of this integration. uint counting multiples of ADC samples since last sync (sync_time, id=0x1027). Divide this number by timestamp_scale (id=0x1046) to get back to seconds since last sync when this integration was actually started. Note that the receiver will need to figure out the centre timestamp of the accumulation (eg, by adding half of int_time, id 0x1016).',
                shape=[], fmt=spead.mkfmt(('u',spead.ADDRSIZE)),
                init_val=0)

            ig.add_item(name=("xeng_raw%i"%x),id=(0x1800+x),
                description="Raw data for xengine %i out of %i. Frequency channels are split amonst xengines. Frequencies are distributed to xengines in a round-robin fashion, starting with engine 0. Data from all X engines must thus be combed or interleaved together to get continuous frequencies. Each xengine calculates all baselines (n_bls given by SPEAD ID 0x100B) for a given frequency channel. For a given baseline, -SPEAD ID 0x1040- stokes parameters are calculated (nominally 4 since xengines are natively dual-polarisation; software remapping is required for single-baseline designs). Each stokes parameter consists of a complex number (two real and imaginary unsigned integers)."%(x,self.config['n_xeng']),
                ndarray=(numpy.dtype(numpy.int32),(self.config['n_chans']/self.config['n_xeng'],self.config['n_bls'],self.config['n_stokes'],2)))

        tx.send_heap(ig.get_heap())

