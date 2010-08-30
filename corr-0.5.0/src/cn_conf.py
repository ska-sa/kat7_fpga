import iniparse,exceptions,socket,struct
"""
Library for parsing CASPER correlator configuration files

Author: Jason Manley
Revision: 2008-02-08

Revs:
2010-08-05: JRM changed adc_clk to integer Hz (from float GHz)
                added calc of timestamp scaling factors and misc other bits
2010-06-28: JRM Added support for reconfigurable F engines (ie ROACH)
2009-12-10: JRM Changed IP address formats to input strings, but return integers.
                Added __setitem__, though it's volatile.
                added calculation of n_bls, bandwidth, integration time etc.
2008-02-08: JRM Replaced custom tokeniser with string.split
                Changed EQ to EQ_polys
                Changed max_payload_len to rx_buffer_size

"""
LISTDELIMIT = ','
PORTDELIMIT = ':'


class CorrConf:    
    def __init__(self, config_file):
        self.config_file=config_file
        self.cp = iniparse.INIConfig(open(self.config_file,'rb'))
        self.config=dict()
        self.read_all()

    def __getitem__(self,item):
        return self.config[item]

    def __setitem__(self,item,value):
        self.config[item]=value

    def file_exists(self):
        try:
            f = open(self.config_file)
        except IOError:
            exists = False
        else:
            exists = True
            f.close()
        return exists

    def calc_int_time(self):
        self.config['n_accs']=self.config['acc_len']*self.config['xeng_acc_len']
        self.config['int_time']= float(self.config['n_chans'])*self.config['n_accs']/self.config['bandwidth']

    def read_all(self):
        if not self.file_exists():
            raise RuntimeError('Error opening config file')
        self.config['pol_map']={'x':0,'y':1}
        self.config['rev_pol_map']={0:'x',1:'y'}
        self.config['pols']=['x','y']
        self.config['n_pols']=2
        self.config['xeng_sample_bits']=32

        #get the server stuff
        self.read_int('katcp','katcp_port')
        self.config['servers_f'] = self.cp.katcp.servers_f.split(LISTDELIMIT)
        self.config['servers_x'] = self.cp.katcp.servers_x.split(LISTDELIMIT)
        self.config['bitstream_f'] = self.cp.katcp.bitstream_f
        self.config['bitstream_x'] = self.cp.katcp.bitstream_x

        #get the correlator config stuff:
        self.read_int('correlator','n_chans')
        self.read_int('correlator','n_ants')
        self.read_int('correlator','fft_shift')
        self.read_int('correlator','acc_len')
        self.read_int('correlator','adc_clk')
        self.read_int('correlator','n_stokes')
        self.read_int('correlator','x_per_fpga')
        self.read_int('correlator','n_ants_per_xaui')
        self.read_int('correlator','clk_per_sync')
        self.read_int('correlator','xeng_acc_len')
        self.read_float('correlator','ddc_mix_freq')
        self.read_int('correlator','ddc_decimation')
        self.read_int('correlator','10gbe_port')
        self.read_int('correlator','10gbe_pkt_len')
        self.read_int('correlator','feng_bits')
        self.read_int('correlator','feng_fix_pnt_pos')
        self.read_int('correlator','xeng_clk')
        self.read_int('correlator','n_xaui_ports_per_xfpga')
        self.read_int('correlator','n_xaui_ports_per_ffpga')
        self.read_int('correlator','adc_bits')
        self.read_int('correlator','adc_levels_acc_len')
        self.read_int('correlator','sync_time')
        self.config['10gbe_ip']=struct.unpack('>I',socket.inet_aton(self.get_line('correlator','10gbe_ip')))[0]
        #print '10GbE IP address is %i'%self.config['10gbe_ip']

        #sanity checks:
        if self.config['n_ants']%len(self.config['servers_f']) != 0:
            raise RuntimeError("You have %i antennas, but %i F boards. That can't be right."%(self.config['n_ants'],len(self.config['servers_f'])))


        self.config['n_xeng']=self.config['x_per_fpga']*len(self.config['servers_x'])
        self.config['n_feng']=self.config['n_ants']
        self.config['f_per_fpga']=self.config['n_feng']/len(self.config['servers_f'])
        self.config['n_bls']=self.config['n_ants']*(self.config['n_ants']+1)/2

        if self.config['ddc_mix_freq']<=0:
            #We're dealing with a "real" PFB, either wideband or narrowband.
            self.config['bandwidth']=self.config['adc_clk']/2.
            self.config['center_freq']=self.config['adc_clk']/4.
        else:
            #We're dealing with a complex PFB with a DDC upfront.
            self.config['bandwidth']=float(self.config['adc_clk'])/self.config['ddc_decimation']
            self.config['center_freq']=float(self.config['adc_clk'])*self.config['ddc_mix_freq']

        self.calc_int_time()

        #get the receiver section:
        self.config['receiver']=dict()
        self.read_int('receiver','rx_udp_port')
        self.read_int('receiver','rx_pkt_payload_len')
        self.read_int('receiver','instance_id')
        self.config['rx_udp_ip_str']=self.get_line('receiver','rx_udp_ip')
        self.config['rx_udp_ip']=struct.unpack('>I',socket.inet_aton(self.get_line('receiver','rx_udp_ip')))[0]
        #print 'RX UDP IP address is %i'%self.config['rx_udp_ip']

        #equalisation section:
        self.read_str('equalisation','eq_default')
        self.read_str('equalisation','eq_type')
        self.read_int('equalisation','eq_decimation')
        #self.read_int('equalisation','eq_brams_per_pol_interleave')
        
        self.read_str('correlator','adc_type')
        self.config['adc_demux'] = {'katadc':4,'iadc':4}[self.config['adc_type']]
        self.config['feng_clk'] = self.config['adc_clk']/self.config['adc_demux']
        self.config['mcnt_scale_factor']=self.config['feng_clk']
        self.config['timestamp_scale_factor']=self.config['bandwidth']/self.config['xeng_acc_len']

        if self.config['adc_type'] == 'katadc':
            for ant in range(self.config['n_ants']):
                for pol in ['x','y']:
                    ant_rf_gain = self.get_line('equalisation','rf_gain_%i%c'%(ant,pol))
                    if (ant_rf_gain):
                        self.config['rf_gain_%i%c'%(ant,pol)]=int(ant_rf_gain)
                    else:
                        raise RuntimeError('ERR rf_gain_%i%c'%(ant,pol))

        if not self.config['eq_default'] in ['poly','coeffs']: raise RuntimeError('ERR invalid eq_default')

        if self.config['eq_default'] == 'poly':
            for ant in range(self.config['n_ants']):
                for pol in ['x','y']:
                    ant_eq_str=self.get_line('equalisation','eq_poly_%i%c'%(ant,pol))
                    if (ant_eq_str):
                        self.config['eq_poly_%i%c'%(ant,pol)]=[int(coef) for coef in ant_eq_str.split(LISTDELIMIT)]
                    else:
                        raise RuntimeError('ERR eq_poly_%i%c'%(ant,pol))

        for ant in range(self.config['n_ants']):
            for pol in ['x','y']:
                try: ant_eq_str=self.get_line('equalisation','eq_coeffs_%i%c'%(ant,pol))
                except: pass
                if (ant_eq_str):
                    self.config['eq_coeffs_%i%c'%(ant,pol)]=eval(ant_eq_str)
                elif self.config['eq_default'] == 'coeffs': raise RuntimeError('ERR eq_coeffs_%i%c'%(ant,pol))

    def write(self,section,variable,value):
        self.config[variable]=value
        self.cp[section][variable]=str(value)
        fpw=open(self.config_file,'w')
        print >>fpw,self.cp
        fpw.close()

    def get_line(self,section,variable):
        return self.cp[section][variable]

    def read_int(self,section,variable):
        self.config[variable]=int(self.cp[section][variable])

    def read_bool(self,section,variable):
        self.config[variable]=(self.cp[section][variable] != '0')

    def read_str(self,section,variable):
        self.config[variable]=self.cp[section][variable]

    def read_float(self,section,variable):
        self.config[variable]=float(self.cp[section][variable])
