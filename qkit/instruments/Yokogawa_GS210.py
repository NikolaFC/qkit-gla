# Yokogawa_GS200.py driver for Yokogawa GS200 DC voltag/current source
# adapted from GS820 driver, Lukas Gruenhaupt @KIT 07/2017
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from qkit.core.instrument_base import Instrument
from qkit import visa
import types
import logging
import numpy
import struct
import time


class Yokogawa_GS210(Instrument):
    '''
    This is the driver for the Yokogawa GS200 multi channel source measure unit

    Usage:
    Initialize with
    <name> = instruments.create('<name>', 'Yokogawa_GS210', address='<GBIP address>',
        reset=<bool>)
    '''

    def __init__(self, name, address, reset=False):
        '''
        Initializes the Yokogawa GS200, and communicates with the wrapper.

        Input:
            name (string)    : name of the instrument
            address (string) : GPIB address
            reset (bool)     : resets to default values

        Output:
            None
        '''
        # Initialize wrapper functions
        logging.info(__name__ + ' : Initializing instrument Yokogawa_GS200')
        Instrument.__init__(self, name, tags=['physical'])

        # Add some global constants
        self._address = address
        #self._numchs = 1
        self.ramp_wait_time = 0.5
        self._visainstrument = visa.instrument(self._address)
        
        #self._visainstrument.write(':SYST:REM')
        

        # Add parameters to wrapper
        
        self.add_parameter('operation_mode',
            flags=Instrument.FLAG_SET,
            type=str, units='')

        self.add_parameter('source_mode',
            flags=Instrument.FLAG_GETSET,
            type=str, units='')

        self.add_parameter('source_range',
            flags=Instrument.FLAG_GETSET ,
            units='', type=str)
            
        self.add_parameter('output',
            flags=Instrument.FLAG_GETSET ,
            units='', type=str)
        
        self.add_parameter('level', 
            flags=Instrument.FLAG_GETSET | Instrument.FLAG_GET_AFTER_SET,
            type=float, units='')

        self.add_parameter('voltage_protection', 
            flags=Instrument.FLAG_GETSET | Instrument.FLAG_GET_AFTER_SET,
            type=float, units='V')

        self.add_parameter('current_protection', 
            flags=Instrument.FLAG_GETSET | Instrument.FLAG_GET_AFTER_SET,
            type=float, units='A')
            
        self.add_parameter('4W',
            flags=Instrument.FLAG_GETSET ,
            units='', type=str)

        self.add_parameter('ramp_wait_time', 
            flags=Instrument.FLAG_GET,
            type=float, units = 's')
          



        # Add functions to wrapper
        
        self.add_function('reset')
        self.add_function('get_all')
        self.add_function('set_defaults')


        
        if reset:
            self.reset()
        else:
            self.get_all()
            self.set_defaults()
            

# functions
    def reset(self):     
        '''
        Resets instrument to default values

        Input:
            None
    
        Output:
            None
        '''
        logging.debug(__name__ + ' : Resetting instrument')
        self._visainstrument.write('*RST')
        self.get_all()
      
    def get_all(self):
        '''
        Reads all relevant parameters from instrument

        Input:
            None

        Output:
            None
        '''
        logging.debug(__name__ + ' : Get all relevant data from device')
        
        
        self.get('source_mode')
        self.get('source_range')
        self.get('output')
        self.get('level')
        self.get('voltage_protection')
        self.get('current_protection')
        self.get('4W')
        self.get('ramp_wait_time')






            
        
        
    def set_defaults(self):
        '''
        Set to driver defaults:
        Operation mode is set to remote
        Source range is +-10 mA
        Source mode is current mode
        output remains unchanged
        voltage protection (max. value) is 30 V
        current protection (max. value) is 10 mA
        The measuring mode is set to 2-wire sense
        '''
        self.set('operation_mode', 'REM')
        self.set('source_mode', 'curr')
        self.set('source_range', '10mA')
        #self.set('output', 'off')
        self.set('voltage_protection', '30')
        self.set('current_protection', '0.01')
        self.set('4W', 'off')
        self.set('slope_time')
        self.ramp_wait_time = 0.5

    

        
 # parameters
 
    def do_set_operation_mode(self, mode):
        '''
        Set operation mode.
        '''    
        if mode in ['REM','LOC']:
            logging.debug('Set mode to %s mode', mode)
            self._visainstrument.write(':SYST:%s' % mode)        
        else:
            logging.error('invalid mode %s' % mode)
            

 
    def do_set_source_mode(self, mode):
        '''
        Set source mode to current regime.
        '''    
        if mode in ['curr','volt']:
            logging.debug('Set mode to %s mode', mode)
            self._set_func_par_value('SOUR', 'FUNC', mode)
        else:
            logging.error('invalid mode %s' % mode)
        self.get_all()

    def do_get_source_mode(self):
        '''
        Get source mode 
        
        Input:
            channel (int) : 
        '''
        logging.debug('Get source mode')
        return self._get_func_par('SOUR', 'FUNC')
        
            
            
    def do_set_source_range(self, val):
        '''
        sets source range: 
            determines the min and max values and the resolution
            - 1 mA  --> +- 1.2 mA  resolution 10 nA (+-30 V load Voltage)
            - 10 mA  --> +- 12 mA  resolution 100 nA (+-30 V load Voltage)
            - 100 mA --> +- 120 mA  resolution 1 umA (+-30 V load Voltage)
            - 200 mA --> +- 200 mA  resolution 1 umA (+-30 V load Voltage)
            
            - 10 mV  --> +- 12 mV  resolution 100 nA (---)
            - 100 mV  --> +- 120 mV  resolution 1 umA (---)
            - 1 V  --> +- 1.2 mV  resolution 1 umA (+-200 mA load Current)
            - 10 V  --> +- 12 mV  resolution 1 umA (+-200 mA load Current)
            - 30 mV  --> +- 32 mV  resolution 1 umA (+-200 mA load Current)

         
        Input:
            val (string)  : Value + Unit 
            example: 10mA

        Output:

        '''
        logging.debug('Set source range to %s' % val)
        self._set_func_par_value('sour', 'rang', val)

            
    def do_get_source_range(self):
        '''
        Get source range 
        '''
        logging.debug('Get source range')
        
        return self._get_func_par('sour', 'rang')
        
    def do_set_output(self, val):
        '''
        Sets outputs of channels in "on" or "off" position.
        
        '''
        if val in ['on','off']:
            logging.debug('Set output to %s' % val)
            self._set_func_par_value('outp', 'stat', val)
        else:
            logging.error('Invalid value %s' % val)
            
    def do_get_output(self):
        '''
        Gets output state
        '''
        logging.debug('Get status of output')
        #ans=self._get_func_par('outp','stat')
        ans = self._visainstrument.ask(':outp?')
        
        if ans=='zero':
            return 'off'
        if int(ans):
            print 'Attention: Output is set on; Be careful!'      #warning if output is on! No fast current changes if coil is attached
            return 'on'
        else:
            return 'off'
        
    def do_set_level(self, val):
        '''
        Set measuring level
        If source mode is 'curr' values are in [mA]
        If source mode is 'volt' values are in [V]
        '''
        logging.debug('Set measuring level')
        #if self.get('output', query = False) == 'off':
        #    self.set('output', 'on')
        mode = self.get('source_mode')
        if mode == 'curr':
            self._set_func_par_value('sour', 'lev', val*10**-3)    #values are given in mA for current mode
        elif mode == 'volt':
            self._set_func_par_value('sour', 'lev', val)
        else:
            print 'error'

        
    def do_get_level(self):
        '''
        Gets source output level
        If source mode is 'curr' values are in [mA]
        If source mode is 'volt' values are in [V]       
        '''
        logging.debug('Get measuring level')
        mode = self.get('source_mode')
        if mode == 'curr':
            return float(self._get_func_par('sour','lev'))*1000     #values are returned in mA for current mode
        elif mode == 'volt':
            return float(self._get_func_par('sour','lev'))
        else:
            return 'error'
        
        
    def do_set_voltage_protection(self, val):
        '''
        Gets voltage protection value
        '''
        logging.debug('Get voltage protection value')
        self._set_func_par_value('SOUR','PROT:VOLT', val)
        
    def do_get_voltage_protection(self):
        '''
        Gets voltage protection value
        '''                
        return float(self._get_func_par('SOUR','PROT:VOLT'))
        
    def do_set_current_protection(self, val):
        '''
        Gets voltage protection value
        '''
        logging.debug('Get voltage protection value')
        self._set_func_par_value('SOUR','PROT:CURR', val)
        
    def do_get_current_protection(self):
        '''
        Gets voltage protection value
        '''                
        return float(self._get_func_par('SOUR','PROT:CURR'))
        
        
    def do_set_4W(self, val):
        '''
        Sets measurement mode to 4-wire or 2-wire mode.
        Value should be on or off. 
        "On" devotes to 4-wire mode. "Off" devotes to 2-wire mode.
        In the instrument appropriate command is ":sens:rem on/off"
        '''
        if val in ['on','off']:
            logging.debug('Set 4W to %s' % val)
            self._set_func_par_value('sens', 'rem', val)
        else:
            logging.error('Invalid value %s' % val)

    def do_get_4W(self):
        '''
        Gets measurement mode
        '''
        logging.debug('Get 4-wire measurement mode')
        ans = self._get_func_par('sens', 'rem')
        
        if int(ans):
            return 'on'
        else:
            return 'off'
            
    def do_get_ramp_wait_time(self):
        '''
        Get ramp time: Parameter is used for a current ramp and determines the waiting time 
        between two subsequent steps.
        '''
        logging.debug('Get ramp time')
        return self.ramp_wait_time

    def do_set_ramp_wait_time(self, val):
        '''
        Get ramp time: Parameter is used for a current ramp and determines the waiting time 
        between two subsequent steps.
        '''
        logging.debug('Set ramp time to %s s' % val)
        self.ramp_wait_time = val
        
        
        
   # core communication
    def _set_func_par_value(self, func, par, val):
        '''
        For internal use only!!
        Changes the value of the parameter for the function specified

        Input:
            ch (int)
            func (string) :
            par (string)  :
            val (depends) :

        Output:
            None
        '''
        string = ':%s:%s %s\r\n' %(func, par, val)
        logging.debug(__name__ + ' : Set instrument to %s' % string)
        self._visainstrument.write(string)

    def _get_func_par(self, func, par):
        '''
        For internal use only!!
        Reads the value of the parameter for the function specified
        from the instrument

        Input:
            ch (int)      :
            func (string) :
            par (string)  :

        Output:
            val (string) :
        '''
        string = ':%s:%s?\r\n' %(func, par)
        ans = self._visainstrument.ask(string)
        logging.debug(__name__ + ' : ask instrument for %s (result %s)' % \
            (string, ans))
        return ans.lower()
        
        
        
        
        
        
    def ramp_current(self,target, step,  wait_time, showvalue=True, outp = False):
        '''
        Ramps the current starting from the actual value to a target value
        Attention: all values are given in mA
        'step' determines the step size
        'wait' determines the sleep time after every step
        'outp' determines if the output is on (True) or off (False) during the ramp
        '''
        
        op = self.get('output')
        start = self.get_level()
        
        
        if outp == True:
            if op == 'off':
                return 'Attention: Output is off! If desired please turn on output manually and repeat operation'  
            elif op == 'on':
                logging.debug('Start current ramp from {} to {} with output on'.format(start,target))
            else: 
                logging.error('Invalid output mode')
        else:
            if op == 'on':
                return  'Attention: Output is on! If desired please turn off output manually and repeat operation'
            elif op == 'off':
                logging.debug('Start current ramp from {} to {} with output off'.format(start,target))
            else: 
                logging.error('Invalid output mode')
                
        if(target < start): step = -step
        elif target == start: return 'Target value {} mA already reached!'.format(target)
        a = numpy.concatenate( (numpy.arange(start, target, step)[1:], [target]) )
        print 'I = {} mA'.format(self.get('level')),
        for i in a:
            if showvalue==True: 
                self.set_level(i)
                print 'I = {} mA'.format(self.get('level')),
            time.sleep(wait_time)   

        
        
        
        
 
 

        

        

        

    def do_get_value(self, channel):
        '''
        Gets measured value
        '''
        logging.debug('Get measured value')
        return float(self._visainstrument.ask(':chan%d:fetc?' % channel))




