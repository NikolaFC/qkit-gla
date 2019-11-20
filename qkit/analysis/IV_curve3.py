# -*- coding: utf-8 -*-
# IV_curve.py analysis class for IV like transport measurements
# Micha Wildermuth, micha.wildermuth@kit.edu 2019

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

import sys
import numpy as np
from scipy import signal as sig
# TODO: uncertainty analysis probably using import uncertainties

import qkit
from qkit.storage.store import Data
import qkit.measure.measurement_class as mc
from qkit.gui.plot import plot as qviewkit

import json
from qkit.measure.json_handler import QkitJSONEncoder


class IV_curve3(object):
    """
    This is an analysis class IV like transport measurements taken by qkit.measure.transport.transport.py
    """

    def __init__(self):
        """
        Initializes an analysis class IV like transport measurements taken by qkit.measure.transport.transport.py

        Parameters
        ----------
        None

        Returns
        -------
        None

        Examples
        --------
        >>> import numpy as np
        >>> import qkit
        QKIT configuration initialized -> available as qkit.cfg[...]
        >>> qkit.start()
        Starting QKIT framework ... -> qkit.core.startup
        Loading module ... S10_logging.py
        Loading module ... S12_lockfile.py
        Loading module ... S14_setup_directories.py
        Loading module ... S20_check_for_updates.py
        Loading module ... S25_info_service.py
        Loading module ... S30_qkit_start.py
        Loading module ... S65_load_RI_service.py
        Loading module ... S70_load_visa.py
        Loading module ... S80_load_file_service.py
        Loading module ... S85_init_measurement.py
        Loading module ... S98_started.py
        Loading module ... S99_init_user.py
        Initialized the file info database (qkit.fid) in 0.000 seconds.

        >>> from qkit.analysis.IV_curve import IV_curve as IVC
        >>> ivc = IVC()
        Initialized the file info database (qkit.fid) in 0.000 seconds.
        """
        qkit.fid.update_all()  # update file database
        self.uuid, self.path, self.df = None, None, None
        self.mo = mc.Measurement()  # qkit-sample object
        self.m_type, self.scan_dim, self.sweeptype, self.sweeps, self.bias = None, None, None, None, None
        self.I, self.V, self.V_corr, self.dVdI = None, None, None, None
        self.I_offsets, self.V_offsets, self.I_offset, self.V_offset = None, None, None, None
        self.x_ds, self.x_coordname, self.x_unit, self.x_vec = None, None, None, None
        self.y_ds, self.y_coordname, self.y_unit, self.y_vec = None, None, None, None
        self.si_prefix = {'y': 1e-24,  # yocto
                          'z': 1e-21,  # zepto
                          'a': 1e-18,  # atto
                          'f': 1e-15,  # femto
                          'p': 1e-12,  # pico
                          'n': 1e-9,  # nano
                          'u': 1e-6,  # micro
                          'm': 1e-3,  # milli
                          'c': 1e-2,  # centi
                          'd': 1e-1,  # deci
                          'k': 1e3,  # kilo
                          'M': 1e6,  # mega
                          'G': 1e9,  # giga
                          'T': 1e12,  # tera
                          'P': 1e15,  # peta
                          'E': 1e18,  # exa
                          'Z': 1e21,  # zetta
                          'Y': 1e24,  # yotta
                          }

    def load(self, uuid, dVdI='analysis0'):
        """
        Loads transport measurement data with given uuid <uuid>.

        Parameters
        ----------
        uuid: str
            qkit identification name, that is looked for and loaded
        dVdI: str | boolean
            Folder, where numerical derivative dV/dI is tried to load form datafile, if this was already analyzed during the measurement. If False, dV/dI is not loaded. Default is 'analysis0'.

        Returns
        -------
        None

        Examples
        --------
        >>> ivc.load(uuid='XXXXXX')
        """
        if uuid != self.uuid and self.uuid is not None:
            self.__init__()
        self.uuid = uuid
        self.path = qkit.fid.get(self.uuid)
        self.df = Data(self.path)
        self.mo.load(qkit.fid.measure_db[self.uuid])
        self.m_type = self.mo.measurement_type  # measurement type
        if self.m_type == 'transport':
            self.scan_dim = self.df.data.i_0.attrs['ds_type']  # scan dimension (1D, 2D, ...)
            self.bias = self.get_bias()
            self.sweeps = self.mo.sample.sweeps  # sweeps (start, stop, step)
            self.sweeptype = self.get_sweeptype()
            shape = np.concatenate([[len(self.sweeps)], np.max([self.df['entry/data0/i_{:d}'.format(j)].shape for j in range(len(self.sweeps))], axis=0)])  # (number of sweeps, eventually len y-values, eventually len x-values, maximal number of sweep points)
            self.I, self.V, self.dVdI = np.empty(shape=shape), np.empty(shape=shape), np.empty(shape=shape)
            for j in range(shape[0]):
                i = self.df['entry/data0/i_{:d}'.format(j)][:]
                v = self.df['entry/data0/v_{:d}'.format(j)][:]
                if dVdI:
                    try:
                        dvdi = self.df['entry/{:s}/dvdi_{:d}'.format(dVdI, j)][:]  # if analysis already done during measurement
                    except KeyError:
                        dvdi = self.get_dydx(x=self.I[j], y=self.V[j])
                pad_width = np.insert(np.diff([i.shape, shape[1:]], axis=0), (0,), np.zeros(self.scan_dim)).reshape(self.scan_dim, 2)
                if pad_width.any():
                    self.I[j] = np.pad(i, pad_width, 'constant', constant_values=np.nan)  # fill with current values (eventually add nans at the end, if sweeps have different lengths)
                    self.V[j] = np.pad(v, pad_width, 'constant', constant_values=np.nan)  # fill with voltage values (eventually add nans at the end, if sweeps have different lengths)
                    if dVdI:
                        self.dVdI[j] = np.pad(dvdi, pad_width, 'constant', constant_values=np.nan)  # fill with differential resistance values (eventually add nans at the end, if sweeps have different lengths)
                else:
                    self.I[j] = i
                    self.V[j] = v
                    if dVdI:
                        self.dVdI[j] = dvdi
            if self.scan_dim >= 2:  # 2D or 3D scan
                # x parameter
                self.x_ds = self.df[self.df.data.i_0.attrs['x_ds_url']]
                self.x_coordname = self.x_ds.attrs['name']
                self.x_unit = self.x_ds.attrs['unit']
                self.x_vec = self.x_ds[:]
                if self.scan_dim == 3:  # 3D scan
                    # y parameter
                    self.y_ds = self.df[self.df.data.i_0.attrs['y_ds_url']]
                    self.y_coordname = self.y_ds.attrs['name']
                    self.y_unit = self.y_ds.attrs['unit']
                    self.y_vec = self.y_ds[:]
                else:
                    self.y_ds, self.y_coordname, self.y_unit, self.y_vec = None, None, None, None
            else:
                self.x_ds, self.x_coordname, self.x_unit, self.x_vec = None, None, None, None
        else:
            raise ValueError('No data of transport measurements')
        return

    def save(self, filename, params=None):
        """
        Saves the class variables
             * uuid,
             * path,
             * measurement_object,
             * measurement_type,
             * scan_dimension,
             * sweep_type,
             * sweeps,
             * bias,
             * I,
             * V,
             * V_corr (only if set
             * dVdI,
             * I_offsets,
             * V_offsets,
             * I_offset,
             * V_offset,
             * x_coordname,
             * x_unit,
             * x_vector,
             * y_coordname,
             * y_unit,
             * y_vector
        as well as <params> to a json-file.

        Parameters
        ----------
        filename: str
            Filename of the .json-file that is created.
        params: dict
            Additional variables that are saved. Default is None, so that only the above mentioned class variables are saved.

        Returns
        -------
        None
        """
        params = params if params else {}
        params = {**{'uuid': self.uuid,
                     'path': self.path,
                     'measurement_object': self.mo.get_JSON(),
                     'measurement_type': self.m_type,
                     'scan_dimension': self.scan_dim,
                     'sweep_type': self.sweeptype,
                     'sweeps': self.sweeps,
                     'bias': self.bias,
                     'I': self.I,
                     'V': self.V,
                     'dVdI': self.dVdI,
                     'I_offsets': self.I_offsets,
                     'V_offsets': self.V_offsets,
                     'I_offset': self.I_offset,
                     'V_offset': self.V_offset,
                     'x_coordname': self.x_coordname,
                     'x_unit': self.x_unit,
                     'x_vector': self.x_vec,
                     'y_coordname': self.y_coordname,
                     'y_unit': self.y_unit,
                     'y_vector': self.y_vec},
                  **params}
        if self.V_corr:
            params['V_corr'] = self.V_corr
        if '.json' not in filename:
            filename += '.json'
        with open(filename, 'w') as filehandler:
            json.dump(obj=params, fp=filehandler, indent=4, cls=QkitJSONEncoder, sort_keys=True)

    def open_qviewkit(self, uuid=None, ds=None):
        """

        uuid: str
        ds: str | list(str)
            Datasets that are opened instantaneously. Default is 'views/IV'
        """
        if uuid is None:
            df = self.df
        else:
            df = Data(qkit.fid.get(uuid))
        if ds is None:
            ds = ['views/IV']
            # try:
            #     if self.scan_dim > 1:
            #         for i in range(len(self.sweeps)):
            #             datasets.append('{:s}_{:d}'.format({0: 'I', 1: 'V'}[not self.bias].lower(), i))
        elif not np.iterable(ds) and type(ds) is str:
            ds = [ds]
        else:
            raise ValueError('Argument <ds> needs to be set properly.')
        qviewkit.plot(df.get_filepath(), datasets=ds)  # opens IV-view by default

    def get_bias(self, df=None):
        """
        Gets bias mode of the measurement. Evaluate 'x_ds_url' (1D), 'y_ds_url' (2D), 'z_ds_url' (3D) of i_0 and v_0 and checks congruence.

        Parameters
        ----------
        df: qkit.storage.store.Data (optional)
            Datafile of transport measurement. Default is None that means self.df

        Returns
        -------
        mode: int
            Bias mode. Meanings are 0 (current) and 1 (voltage).
        """
        #
        if df is None:
            df = self.df
        self.bias = {'i': 0, 'v': 1}[str(
            df.data.i_0.attrs.get('{:s}_ds_url'.format(chr(self.scan_dim + 119))) and
            df.data.v_0.attrs.get('{:s}_ds_url'.format(chr(self.scan_dim + 119)))).split('/')[-1][0]]
        return self.bias

    def get_sweeptype(self, sweeps=None):
        """
        Gets the sweeptype of predefined set of sweeps as generated by qkit.measure.transport.transport.py

        Parameters
        ----------
        sweeps: array_likes of array_likes of floats (optional)
            Set of sweeps containing start, stop and step size (e.g. sweep object using qkit.measure.transport.transport.sweep class). Default is None that means self.sweeps.

        Returns
        -------
        sweeptype: int
            Type of set of sweeps. Is 0 (halfswing), 1 (4 quadrants) or None (arbitrary set of sweeps).
        """
        if sweeps is None:
            sweeps = self.sweeps
        # check if sweeps are halfswing
        if len(sweeps) == 2:
            if all(np.array(sweeps[0])[[1, 0, 2]] == np.array(sweeps[1])[:3]):
                self.sweeptype = 0
        # check if sweeps are 4quadrants
        elif len(sweeps) == 4:
            if all(np.array(sweeps[0])[[1, 0, 2]] == np.array(sweeps[1])[:3]) and all(np.array(sweeps[2])[[1, 0, 2]] == np.array(sweeps[3])[:3]):
                self.sweeptype = 1
        else:
            self.sweeptype = None
        return self.sweeptype

    def get_dVdI(self, I=None, V=None, mode=sig.savgol_filter, **kwargs):
        """
        Calculates numerical derivative dV/dI.

        Parameters
        ----------
        I: numpy.array (optional)
            An N-dimensional array containing current values. Default is None that means self.I.
        V: numpy.array (optional)
            An N-dimensional array containing voltage values. Default is None that means self.V.
        mode: function (optional)
            Function that calculates the numerical gradient dx from a given array x. Default is scipy.signal.savgol_filter (Savitzky Golay filter).
        kwargs:
            Keyword arguments forwarded to the function <mode>.

        Returns
        -------
        dVdI: numpy.array
            Numerical derivative dV/dI

        Examples
        --------
        # Savitzky Golay filter
        >>> ivc.get_dVdI()

        # numerical gradient
        >>> ivc.get_dVdI(mode=np.gradient)
        """
        if V is None:
            y = self.V
        else:
            y = V
        if I is None:
            x = self.I
        else:
            x = I
        self.dVdI = self.get_dydx(y=y, x=x, mode=mode, **kwargs)
        return self.dVdI

    def get_dydx(self, y, x=None, mode=sig.savgol_filter, **kwargs):
        """
        Calculates numerical derivative dy/dx

        Parameters
        ----------
        y: numpy.array
            An N-dimensional array containing y-values
        x: numpy.array (optional)
            An N-dimensional array containing x-values. Default is None which means that x is considered as index.
        mode: function (optional)
            Function that calculates the numerical gradient dx from a given array x. Default is scipy.signal.savgol_filter (Savitzky Golay filter).
        kwargs:
            Keyword arguments forwarded to the function <mode>. Default for scipy.signal.savgol_filter is {'window_length': 15, 'polyorder': 3, 'deriv': 1} and for numpy.gradient {'axis': self.scan_dim}

        Returns
        -------
        dy/dx: numpy.array
            Numerical gradient quotient. If no x is given, dx = np.ones(nop)

        Examples
        --------
        Savitzky Golay filter
        >>> ivc.get_dydx(y=np.arange(1e1), mode=sig.savgol_filter, window_length=9, polyorder=3, deriv=1)
        array([1., 1., 1., 1., 1., 1., 1., 1., 1., 1.])

        numerical gradient
        >>> ivc.get_dydx(mode=np.gradient)
        ivc.get_dydx(y=np.arange(1e1), mode=np.gradient)
        """
        if mode == sig.savgol_filter:
            if 'window_length' not in kwargs.keys():
                kwargs['window_length'] = 15
            if 'polyorder' not in kwargs.keys():
                kwargs['polyorder'] = 3
            if 'deriv' not in kwargs.keys():
                kwargs['deriv'] = 1
        elif mode == np.gradient:
            if 'axis' not in kwargs.keys():
                kwargs['axis'] = self.scan_dim
        if x is None:
            try:
                return mode(y, **kwargs)
            except Exception as e:
                print('{:s}\n slice np.nans at the end, differentiate and add np.nans at the end'.format(e))
                y_nans = np.isnan(y)
                return np.concatenate([mode(y[np.logical_not(y_nans)], **kwargs), y[y_nans]])
        else:
            try:
                return mode(y, **kwargs)/mode(x, **kwargs)
            except Exception as e:
                print('{:s}\n slice np.nans at the end, differentiate and add np.nans at the end'.format(e))
                x_nans = np.isnan(x)
                y_nans = np.isnan(y)
                return np.concatenate([mode(y[np.logical_not(y_nans)], **kwargs), y[y_nans]])/np.concatenate([mode(x[np.logical_not(x_nans)], **kwargs), x[x_nans]])

    def get_offsets(self, x=None, y=None, threshold=20e-6, offset=0, yr=False):
        """
        Calculates x- and y-offset for every trace. Therefore the branch where the y-values are nearly constant are evaluated. The average of all corresponding x-values is considered to be the x-offset and the average of the extreme y-values are considered as y-offset.

        Parameters
        ----------
        x: numpy.array (optional)
            An N-dimensional array containing x-values. Default is None, where x is considered as self.V and self.I in the current and voltage bias, respectively.
        y: numpy.array (optional)
            An N-dimensional array containing y-values. Default is None, where y is considered as self.I and self.V in the current and voltage bias, respectively.
        threshold: float (optional)
            Threshold voltage that limits the superconducting branch. Default is 20e-6.
        offset: float (optional)
            Voltage offset that shifts the limits of the superconducting branch which is set by <threshold>. Default is 0.
        yr: bool (optional)
            Condition, if critical or retrapping y-values are evaluated. Default is False.

        Returns
        -------
        I_offsets: numpy.array
            Current offsets of every single trace.
        V_offsets: numpy.array
            Voltage offsets of every single trace.
        """
        if x is None:
            x = [self.V, self.I][self.bias]
        if y is None:
            y = [self.I, self.V][self.bias]
        ''' constant range via threshold (for JJ superconducting range via threshold voltage) '''
        mask = np.logical_and(x >= -threshold + offset, x <= threshold + offset)
        x_const, y_const = np.copy(x), np.copy(y)
        np.place(x_const, np.logical_not(mask), np.nan)
        np.place(y_const, np.logical_not(mask), np.nan)
        if self.sweeptype == 0:  # halfswing
            ''' get x offset (for JJ voltage offset)'''
            x_offsets = np.mean(np.nanmean(x_const, axis=self.scan_dim), axis=0)
            ''' get y offset (for JJ current offset) '''
            if yr:  # retrapping y (for JJ retrapping current)
                y_rs = np.array([np.nanmax(y_const[0], axis=(self.scan_dim-1)), np.nanmin(y_const[1], axis=(self.scan_dim-1))])
                y_offsets = np.mean(y_rs, axis=0)
            else:  # critical y (for JJ critical current)
                y_cs = np.array([np.nanmin(y_const[0], axis=(self.scan_dim-1)), np.nanmax(y_const[1], axis=(self.scan_dim-1))])
                y_offsets = np.mean(y_cs, axis=0)
        elif self.sweeptype == 1:  # 4 quadrants
            ''' get x offset '''
            x_offsets = np.mean(np.nanmean(x_const, axis=self.scan_dim), axis=0)
            ''' get y offset '''
            if yr:  # retrapping y (for JJ retrapping current)
                y_rs = np.array([np.nanmax(y_const[1], axis=(self.scan_dim-1)), np.nanmin(y_const[3], axis=(self.scan_dim-1))])
                y_offsets = np.mean(y_rs, axis=0)
            else:  # critical y (for JJ critical current)
                y_cs = np.array([np.nanmax(y_const[0], axis=(self.scan_dim-1)), np.nanmin(y_const[2], axis=(self.scan_dim-1))])
                y_offsets = np.mean(y_cs, axis=0)
        else:
            raise NotImplementedError('No algorithm implemented for custom sweeptype')
        self.I_offsets, self.V_offsets = [x_offsets, y_offsets][::int(np.sign(self.bias - .5))]
        return self.I_offsets, self.V_offsets

    def get_offset(self, *args, **kwargs):
        """
        Calculates x- and y-offset for the whole data set. Therefore the branch where the y-values are nearly constant are evaluated. The average of all corresponding x-values is considered to be the x-offset and the average of the extreme y-values are considered as y-offset.

        Parameters
        ----------
        x: numpy.array (optional)
            An N-dimensional array containing x-values. Default is None, where x is considered as self.V and self.I in the current and voltage bias, respectively.
        y: numpy.array (optional)
            An N-dimensional array containing y-values. Default is None, where y is considered as self.I and self.V in the current and voltage bias, respectively.
        threshold: float (optional)
            Threshold voltage that limits the superconducting branch. Default is 20e-6.
        offset: float (optional)
            Voltage offset that shifts the limits of the superconducting branch which is set by <threshold>. Default is 0.
        yr: bool (optional)
            Condition, if critical or retrapping y-values are evaluated. Default is False.

        Returns
        -------
        I_offsets: numpy.array
            Current offsets of the whole data set.
        V_offsets: numpy.array
            Voltage offsets of the whole data set.
        """
        self.I_offset, self.V_offset = np.fromiter(map(np.nanmean, self.get_offsets(*args, **kwargs)), dtype=float)
        return self.I_offset, self.V_offset

    def get_2wire_slope_correction(self, I=None, V=None, dVdI=None, peak_finder=sig.find_peaks, **kwargs):
        """
        Gets voltage values corrected by an ohmic slope such as occur in 2wire measurements.
        The two maxima in the differential resistivity <dVdI> are identified as critical and retrapping currents. The slope of the superconducting regime in between (which should ideally be infinity) is fitted using numpy.linalg.qr algorithm and subtracted from the raw data.

        Parameters
        ----------
        I: numpy.array (optional)
            An N-dimensional array containing current values. Default is None that means self.I.
        V: numpy.array (optional)
            An N-dimensional array containing voltage values. Default is None that means self.V.
        dVdI: numpy.array (optional)
            An N-dimensional array containing differential resistance (dV/dI) values. Default is None that means self.dVdI.
        peak_finder: function (optional)
            Peak finding algorithm. Default is scipy.signal.find_peaks.
        kwargs:
            Keyword arguments forwarded to the peak finding algorithm <peak_finder>.

        Returns
        -------
        V_corr: numpy.array
            Ohmic slope corrected voltage values
        """
        def lin_fit(x, y):
            X = np.stack((x, np.ones(len(x)))).T
            q, r = np.linalg.qr(X)
            p = np.dot(q.T, y)
            return np.dot(np.linalg.inv(r), p)
        if I is None:
            I = self.I
        if V is None:
            V = self.V
        if dVdI is None:
            dVdI = self.dVdI
        if peak_finder is sig.find_peaks and 'prominence' not in kwargs.keys():
            kwargs['prominence'] = 100
        if peak_finder is sig.find_peaks_cwt and 'widths' not in kwargs.keys():
            kwargs['widths'] = np.arange(10)
        ''' peak detection in dV/dI '''
        if self.scan_dim == 1:
            peaks = map(lambda dVdI1D:
                        peak_finder(dVdI1D, **kwargs),
                        dVdI)
            slices = map(lambda peaks1D:
                         slice(*np.sort(peaks1D[0][peaks1D[1]['prominences'].argsort()[-2:][::-1]])),
                         peaks)
            popts = map(lambda I1D, V1D, s1D:
                        lin_fit(I1D[s1D], V1D[s1D]),
                        I, V, slices)
            self.V_corr = np.array(list(map(lambda I1D, V1D, popt1D:
                                            V1D - (popt1D[0] * I1D + popt1D[1]),
                                            I, V, popts)),
                                   dtype=float)
            return self.V_corr
        elif self.scan_dim == 2:
            peaks = map(lambda dVdI2D:
                        map(lambda dVdI1D:
                            peak_finder(dVdI1D, **kwargs),
                            dVdI2D),
                        dVdI)
            slices = map(lambda peaks2D:
                         map(lambda peaks1D:
                             slice(*np.sort(peaks1D[0][peaks1D[1]['prominences'].argsort()[-2:][::-1]])),
                             peaks2D),
                         peaks)
            popts = map(lambda I2D, V2D, s2D:
                        map(lambda I1D, V1D, s1D:
                            lin_fit(I1D[s1D], V1D[s1D]),
                            I2D, V2D, s2D),
                        I, V, slices)
            self.V_corr = np.array(list(map(lambda I2D, V2D, popt2D:
                                            map(lambda I1D, V1D, popt1D:
                                                V1D - (popt1D[0] * I1D + popt1D[1]),
                                                I2D, V2D, popt2D),
                                            I, V, popts)),
                                   dtype=float)
            return self.V_corr
        elif self.scan_dim == 3:
            peaks = map(lambda dVdI3D:
                        map(lambda dVdI2D:
                            map(lambda dVdI1D:
                                peak_finder(dVdI1D, **kwargs),
                                dVdI2D),
                            dVdI3D),
                        dVdI)
            slices = map(lambda peaks3D:
                         map(lambda peaks2D:
                             map(lambda peaks1D:
                                 slice(*np.sort(peaks1D[0][peaks1D[1]['prominences'].argsort()[-2:][::-1]])),
                                 peaks2D),
                             peaks3D),
                         peaks)
            popts = map(lambda I3D, V3D, s3D:
                        map(lambda I2D, V2D, s2D:
                            map(lambda I1D, V1D, s1D:
                                lin_fit(I1D[s1D], V1D[s1D]),
                                I2D, V2D, s2D),
                            I3D, V3D, s3D),
                        I, V, slices)
            self.V_corr = np.array(list(map(lambda I3D, V3D, popt3D:
                                            map(lambda I2D, V2D, popt2D:
                                                map(lambda I1D, V1D, popt1D:
                                                    V1D - (popt1D[0] * I1D + popt1D[1]),
                                                    I2D, V2D, popt2D),
                                                I3D, V3D, popt3D),
                                            I, V, popts)),
                                   dtype=float)
            return self.V_corr
        else:
            raise ValueError('Scan dimension must be in {1, 2, 3}')

    def get_Ic_threshold(self, I=None, V=None, dVdI=None, threshold=20e-6, offset=None, Ir=False):
        """
        Get critical current values. These are considered as currents, where the voltage jumps beyond threshold ± <threshold> - <offset>.

        Parameters
        ----------
        I: numpy.array (optional)
            An N-dimensional array containing current values. Default is None that means self.I.
        V: numpy.array (optional)
            An N-dimensional array containing voltage values. Default is None that means self.V.
        threshold: float (optional)
            Threshold voltage that limits the superconducting branch. Default is 20e-6.
        offset: float (optional)
            Voltage offset that shifts the limits of the superconducting branch which is set by <threshold>. Default is None that means self.V_offset.
        Ir: bool (optional)
            Condition, if retrapping currents are returned, too. Default is False.

        Returns
        -------
        I_cs: numpy.array
            Critical current values.
        I_rs: numpy.array (optional)
            Retrapping current values.
        """
        if len(V.shape)-1 == 0: # single trace used for in situ fit
            mask = np.logical_and(V >= -threshold + offset, V <= threshold + offset)
            I_sc = np.copy(I)
            np.place(I_sc, np.logical_not(mask), np.nan)
            return np.nanmax(I_sc)
        if V is None:
            V = self.V
        if I is None:
            I = self.I
        if offset is None:
            if self.V_offset is None:
                offset = 0
            else:
                offset = self.V_offset
        ''' constant range via threshold (for JJ superconducting range via threshold voltage) '''
        mask = np.logical_and(V >= -threshold + offset, V <= threshold + offset)
        V_sc, I_sc = np.copy(V), np.copy(I)
        np.place(V_sc, np.logical_not(mask), np.nan)
        np.place(I_sc, np.logical_not(mask), np.nan)
        if self.sweeptype == 0:  # halfswing
            ''' critical current '''
            I_cs = np.array([np.nanmin(I_sc[0], axis=(self.scan_dim-1)), np.nanmax(I_sc[1], axis=(self.scan_dim-1))])
            ''' retrapping current '''
            I_rs = np.array([np.nanmax(I_sc[0], axis=(self.scan_dim-1)), np.nanmin(I_sc[1], axis=(self.scan_dim-1))])
        elif self.sweeptype == 1:  # 4 quadrants
            ''' critical current '''
            I_cs = np.array([np.nanmax(I_sc[0], axis=(self.scan_dim-1)), np.nanmin(I_sc[2], axis=(self.scan_dim-1))])
            ''' retrapping current '''
            I_rs = np.array([np.nanmax(I_sc[1], axis=(self.scan_dim-1)), np.nanmin(I_sc[3], axis=(self.scan_dim-1))])
        else:
            raise NotImplementedError('No algorithm implemented for custom sweeptype')
        if Ir:
            return [I_cs, I_rs]
        else:
            return I_cs

    def get_Ic_deriv(self, I=None, V=None, dVdI=None, Ir=False, tol_offset=20e-6, window=5, peak_finder=sig.find_peaks, **kwargs):
        """
        Gets critical current values using the numerical derivative dV/dI.
        Peaks in these data correspond to voltage jumps, are detected with a peak finding algorithm <peak_finder> and checked, whether the corresponding voltage jumps out or in the superconducting branch, that is identified as critical or retrapping current, respectively. Therefore the average of half the window below and above the peak is considered. The superconducting branch, in turn, is assumed as the voltage offset <self.V_offset> within the tolerance <tol_offset>.

        Parameters
        ----------
        I: numpy.array (optional)
            An N-dimensional array containing current values. Default is None that means self.I.
        V: numpy.array (optional)
            An N-dimensional array containing voltage values. Default is None that means self.V.
        dVdI: numpy.array (optional)
            An N-dimensional array containing differential resistance (dV/dI) values. Default is None that means self.dVdI.
        Ir: bool (optional)
            Condition, if retrapping currents are returned, too. Default is False
        tol_offset: float (optional)
            Voltage offset tolerance that limits the superconducting branch around the voltage offset <self.V_offset>. Default is 20e-6.
        window: int (optional)
            Window around the jump, where the voltage is evaluated and classified as 'superconducting branch'. Default is 5 that considers two values below and 2 values above the jump.
        peak_finder: function (optional)
            Peak finding algorithm. Default is scipy.signal.find_peaks.
        kwargs:
            Keyword arguments forwarded to the peak finding algorithm <peak_finder>.

        Returns
        -------
        I_cs: numpy.array
            Critical current values.
        I_rs: numpy.array (optional)
            Retrapping current values.
        properties: dict
            Properties of all found peaks (not only I_c and I_r, but also further jumps), such as corresponding currents, voltages, differential resistances, indices as well as returns of the used peak finding algorithm.

        Examples
        --------
        >>> I_cs, props = ivc.get_Ic_deriv(prominence=100)
        >>> if ivc.scan_dim == 1:
        >>>     Is = np.array(list(map(lambda p1D: p1D['I'], props)))  # has shape (number of sweeps, number of peaks)
        >>> elif ivc.scan_dim == 2:
        >>>     Is = np.array(list(map(lambda p2D: list(map(lambda p1D: p1D['I'], p2D)), props)))  # has shape (number of sweeps, number of x-values, number of peaks)
        >>> elif ivc.scan_dim == 3:
        >>>     Is = np.array(list(map(lambda p3D: list(map(lambda p2D: list(map(lambda p1D: p1D['I'], p2D)), p3D)), props)))  # has shape (number of sweeps, number of y-values, number of x-values, number of peaks)
        """
        def _peak_finder(x, **_kwargs):
            ans = peak_finder(x, **_kwargs)
            if np.array_equal(ans[0], []):  # no peaks found
                return [np.array([False]), {}]
            else:
                return ans
        if len(V.shape)-1 == 0: # single trace used for in situ fit
            peaks = _peak_finder(dVdI, **kwargs)
            try:
                return I[peaks[0]]
            except IndexError:  # if no peak found return np.nan
                return np.nan
        if I is None:
            I = self.I
        if V is None:
            V = self.V
        if dVdI is None:
            dVdI = self.dVdI
        if peak_finder is sig.find_peaks and 'prominence' not in kwargs.keys():
            kwargs['prominence'] = 100
        if peak_finder is sig.find_peaks_cwt and 'widths' not in kwargs.keys():
            kwargs['widths'] = np.arange(10)
        ''' peak detection in dV/dI '''
        #if self.scan_dim == 1:
        if len(V.shape)-1 == 1:
            peaks = np.array(list(map(lambda dVdI1D:
                                      _peak_finder(dVdI1D, **kwargs),
                                      dVdI)))
        #elif self.scan_dim == 2:
        elif len(V.shape)-1 == 2:
            peaks = np.array(list(map(lambda dVdI2D:
                                      list(map(lambda dVdI1D:
                                               _peak_finder(dVdI1D, **kwargs),
                                               dVdI2D)),
                                      dVdI)))
        #elif self.scan_dim == 3:
        elif len(V.shape)-1 == 3:
            peaks = np.array(list(map(lambda dVdI3D:
                                      list(map(lambda dVdI2D:
                                               list(map(lambda dVdI1D:
                                                        _peak_finder(dVdI1D, **kwargs),
                                                        dVdI2D)),
                                               dVdI3D)),
                                      dVdI)))
        else:
            raise ValueError('Scan dimension must be in {1, 2, 3}')
        return self._classify_jump(I=I, V=V, Y=dVdI, peaks=peaks, tol_offset=tol_offset, window=window, Ir=Ir)

    def get_Ic_dft(self, I=None, V=None, dVdI=None, s=10, Ir=False, tol_offset=20e-6, window=5, peak_finder=sig.find_peaks, **kwargs):
        """
        Gets critical current values using a discrete Fourier transform, a smoothed derivation in the frequency domain and an inverse Fourier transform.
        Therefore the voltage values are corrected by the linear offset slope, fast Fourier transformed to the frequency domain, multiplied with a Gaussian smoothed derivation function if*exp(-s*f^2) in the frequency domain and inversely fast Fourier transformed to the time domain. This corresponds to the convolution of the voltage values with the Gaussian smoothed derivation function in the time domain.
        Peaks in these data correspond to voltage jumps, are detected with a peak finding algorithm <peak_finder> and checked, whether the corresponding voltage jumps out or in the superconducting branch, that is identified as critical or retrapping current, respectively. Therefore the average of half the window below and above the peak is considered. The superconducting branch, in turn, is assumed as the voltage offset <self.V_offset> within the tolerance <tol_offset>.

        Parameters
        ----------
        I: numpy.array (optional)
            An N-dimensional array containing current values. Default is None that means self.I.
        V: numpy.array (optional)
            An N-dimensional array containing voltage values. Default is None that means self.V.
        s: float (optional)
            Smoothing factor of the derivative. Default is 10.
        Ir: bool (optional)
            Condition, if retrapping currents are returned, too. Default is False.
        tol_offset: float (optional)
            Voltage offset tolerance that limits the superconducting branch around the voltage offset <self.V_offset>. Default is 20e-6.
        window: int (optional)
            Window around the jump, where the voltage is evaluated and classified as 'superconducting branch'. Default is 5 that considers two values below and 2 values above the jump.
        peak_finder: function (optional)
            Peak finding algorithm. Default is scipy.signal.find_peaks
        kwargs:
            Keyword arguments forwarded to the peak finding algorithm <peak_finder>.

        Returns
        -------
        I_cs: numpy.array
            Critical current values.
        I_rs: numpy.array (optional)
            Retrapping current values.
        properties: dict
            Properties of all found peaks (not only I_c and I_r, but also further jumps), such as corresponding currents, voltages, differential resistances, indices as well as returns of the used peak finding algorithm.

        Examples
        --------
        >>> I_cs, props = ivc.get_Ic_dft(prominence=1)
        >>> if ivc.scan_dim == 1:
        >>>     Is = np.array(list(map(lambda p1D: p1D['I'], props)))  # has shape (number of sweeps, number of peaks)
        >>> elif ivc.scan_dim == 2:
        >>>     Is = np.array(list(map(lambda p2D: list(map(lambda p1D: p1D['I'], p2D)), props)))  # has shape (number of sweeps, number of x-values, number of peaks)
        >>> elif ivc.scan_dim == 3:
        >>>     Is = np.array(list(map(lambda p3D: list(map(lambda p2D: list(map(lambda p1D: p1D['I'], p2D)), p3D)), props)))  # has shape (number of sweeps, number of y-values, number of x-values, number of peaks)
        """
        def _get_deriv_dft(V_corr):
            V_fft = np.fft.fft(V_corr)  # Fourier transform of V from time to frequency domain
            f = np.fft.fftfreq(V.shape[-1])  # frequency values
            kernel = 1j * np.fft.fft(f * np.exp(-s * f ** 2))  # smoothed derivation function, how it would look like in time domain (with which V is convolved in the time domain)
            V_fft_smooth = 1j * f * np.exp(-s * f ** 2) * V_fft  # Fourier transform of a Gaussian smoothed derivation of V in the frequency domain
            dV_smooth = np.fft.ifft(V_fft_smooth)  # inverse Fourier transform of the smoothed derivation of V from reciprocal to time domain
            return dV_smooth
        def _peak_finder(x, **_kwargs):
            ans = peak_finder(x, **_kwargs)
            if np.array_equal(ans[0], []):  # no peaks found
                return [np.array([False]), {}]
            else:
                return ans
        if len(V.shape)-1 == 0: # single trace used for in situ fit
            V_corr = V - np.linspace(start=V[0], stop=V[-1], num=V.shape[-1], axis=0)  # adjust offset slope
            dV_smooth = _get_deriv_dft(V_corr)
            peaks = _peak_finder(dV_smooth, **kwargs)
            print(len(peaks), peaks)
            try:
                return I[peaks[0]]
            except IndexError:  # if no peak found return np.nan
                return np.nan
        if I is None:
            I = self.I
        if V is None:
            V = self.V
        if peak_finder is sig.find_peaks and 'prominence' not in kwargs.keys():
            kwargs['prominence'] = 1e-5
        if peak_finder is sig.find_peaks_cwt and 'widths' not in kwargs.keys():
            kwargs['widths'] = np.arange(10)
        ''' differentiate and smooth in the frequency domain '''
        if self.scan_dim == 1:
            V_corr = V - np.linspace(start=V[:, 0], stop=V[:, -1], num=V.shape[-1], axis=1)  # adjust offset slope
        elif self.scan_dim == 2:
            V_corr = V - np.linspace(start=V[:, :, 0], stop=V[:, :, -1], num=V.shape[-1], axis=2)  # adjust offset slope
        elif self.scan_dim == 3:
            V_corr = V - np.linspace(start=V[:, :, :, 0], stop=V[:, :, :, -1], num=V.shape[-1], axis=3)  # adjust offset slope
        else:
            raise ValueError('Scan dimension must be in {1, 2, 3}')
        dV_smooth = _get_deriv_dft()
        ''' peak detection '''
        if self.scan_dim == 1:
            peaks = np.array(list(map(lambda dV_smooth1D:
                                      _peak_finder(np.abs(dV_smooth1D), **kwargs),
                                      dV_smooth)))
        elif self.scan_dim == 2:
            peaks = np.array(list(map(lambda dV_smooth2D:
                                      list(map(lambda dV_smooth1D:
                                               _peak_finder(np.abs(dV_smooth1D), **kwargs),
                                               dV_smooth2D)),
                                      dV_smooth)))
        elif self.scan_dim == 3:
            peaks = np.array(list(map(lambda dV_smooth3D:
                                      list(map(lambda dV_smooth2D:
                                               list(map(lambda dV_smooth1D:
                                                        _peak_finder(np.abs(dV_smooth1D), **kwargs),
                                                        dV_smooth2D)),
                                               dV_smooth3D)),
                                      dV_smooth)))
        else:
            raise ValueError('Scan dimension must be in {1, 2, 3}')
        return self._classify_jump(I=I, V=V, Y=dV_smooth, peaks=peaks, tol_offset=tol_offset, window=window, Ir=Ir)

    def _classify_jump(self, I, V, Y, peaks, tol_offset=20e-6, window=5, Ir=False):
        """
        Classifies voltage jumps as critical currents, retrapping currents of none of those.

        Parameters
        ----------
        I: numpy.array
            An N-dimensional array containing current values.
        V: numpy.array
            An N-dimensional array containing voltage values.
        Y: numpy.array
            An N-dimensional array containing data, whose peaks are already determined.
        peaks numpy.array
            An N-dimensional array containing indices and properties of peaks that are already determined, as obtained by e.g. scipy.signal.find_peaks()
        Ir: bool (optional)
            Condition, if retrapping currents are returned, too. Default is False
        tol_offset: float (optional)
            Voltage offset tolerance that limits the superconducting branch around the voltage offset <self.V_offset>. Default is 20e-6.
        window: int (optional)
            Window around the jump, where the voltage is evaluated and classified as 'superconducting branch'. Default is 5 that considers two values below and 2 values above the jump.

        Returns
        -------
        I_cs: numpy.array
            Critical current values.
        I_rs: numpy.array (optional)
            Retrapping current values.
        properties: dict
            Properties of all found peaks (not only I_c and I_r, but also further jumps), such as corresponding currents, voltages, differential resistances, indices as well as returns of the used peak finding algorithm.
        """
        Y_name = [key for key, val in sys._getframe().f_back.f_locals.items() if np.array_equal(val, Y)][0]
        if self.V_offset is None and self.sweeptype in [0, 1]:  # voltage offset to identify superconducting branch
            self.get_offset(x=V, y=I)
        if self.sweeptype == 0:  # halfswing
            V_c, I_c, peaks_c = np.copy(V), np.copy(I), np.copy(peaks)
            V_r, I_r, peaks_r = np.copy(V), np.copy(I), np.copy(peaks)
        elif self.sweeptype == 1:  # 4quadrants
            V_c, I_c, peaks_c = np.copy(V[::2]), np.copy(I[::2]), np.copy(peaks[::2])
            V_r, I_r, peaks_r = np.copy(V[1::2]), np.copy(I[1::2]), np.copy(peaks[1::2])
        else:  # custom sweeptype
            def f(ind1D, prop1D, I1D, V1D, Y1D):
                try:
                    return {**prop1D,
                            **{k: v for k, v in zip(('I', 'V', Y_name, 'index'),
                                                    (I1D[ind1D], V1D[ind1D], Y1D[ind1D], ind1D))}}
                except IndexError:  # if no peak found return np.nan
                    return {k: v for k, v in zip(('I', 'V', Y_name, 'index'),
                                                 (np.array([np.nan]), np.array([np.nan]), np.array([np.nan]), np.array([np.nan])))}
            if self.scan_dim == 1:
                return np.array(list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                         f(ind1D, prop1D, I1D, V1D, Y1D),
                                         *list(zip(*peaks)), I, V, Y)))
            elif self.scan_dim == 2:
                return np.array(list(map(lambda peaks2D, I2D, V2D, Y2D:
                                         list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                                  f(ind1D, prop1D, I1D, V1D, Y1D),
                                                  *list(zip(*peaks2D)), I2D, V2D, Y2D)),
                                         peaks, I, V, Y)))
            elif self.scan_dim == 3:
                return np.array(list(map(lambda peaks3D, I3D, V3D, Y3D:
                                         list(map(lambda peaks2D, I2D, V2D, Y2D:
                                                  list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                                           f(ind1D, prop1D, I1D, V1D, Y1D),
                                                           *list(zip(*peaks2D)), I2D, V2D, Y2D)),
                                                  peaks3D, I3D, V3D, Y3D)),
                                         peaks, I, V, Y)))
            else:
                raise NotImplementedError('No algorithm implemented for custom sweeptype and scan_dim > 3.')
        if self.scan_dim == 1:
            ''' critical current '''
            masks_c = map(lambda V_c1D, peak1D:
                          np.logical_and(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                        np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)),
                                         np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                       np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)))),
                          V_c, peaks_c)
            I_cs = np.array(list(map(lambda I_c1D, peak1D, masks_c1D:
                                     I_c1D[peak1D[0][masks_c1D][0]],
                                     I_c, peaks_c, masks_c)),
                            dtype=float)
            ''' retrapping current '''
            masks_r = map(lambda V_r1D, peak1D:
                          np.logical_and(np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                       np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset))),
                                         np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                        np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset))),
                          V_r, peaks_r)
            I_rs = np.array(list(map(lambda I_r1D, peak1D, masks_r1D:
                                     I_r1D[peak1D[0][masks_r1D][0]+1],
                                     I_r, peaks_r, masks_r)),
                            dtype=float)
            ''' properties '''
            properties = np.array(list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                           {**prop1D,
                                            **{k: v for k, v in zip(('I', 'V', Y_name, 'index'),
                                                                    (I1D[ind1D], V1D[ind1D], Y1D[ind1D], ind1D))}},
                                           *list(zip(*peaks)), I, V, Y)))
        elif self.scan_dim == 2:
            ''' critical current '''
            masks_c = map(lambda V_c2D, peaks_c2D:
                          map(lambda V_c1D, peak1D: np.logical_and(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                  np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)),
                                                                   np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                                 np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)))),
                              V_c2D, peaks_c2D),
                          V_c, peaks_c)
            I_cs = np.array(list(map(lambda I_c2D, peaks_c2D, masks_c2D:
                                     list(map(lambda I_c1D, peak1D, masks_c1D:
                                              I_c1D[peak1D[0][masks_c1D][0]],
                                              I_c2D, peaks_c2D, masks_c2D)),
                                     I_c, peaks_c, masks_c)),
                            dtype=float)
            ''' retrapping current '''
            masks_r = map(lambda V_r2D, peaks_r2D:
                          map(lambda V_r1D, peak1D: np.logical_and(np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                                 np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset + self.V_offset))),
                                                                   np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                  np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset))),
                              V_r2D, peaks_r2D),
                          V_r, peaks_r)
            I_rs = np.array(list(map(lambda I_r2D, peaks_r2D, masks_r2D:
                                     list(map(lambda I_r1D, peaks_r1D, masks_r1D:
                                              I_r1D[peaks_r1D[0][masks_r1D][0]+1],
                                              I_r2D, peaks_r2D, masks_r2D)),
                                     I_r, peaks_r, masks_r)),
                            dtype=float)
            ''' properties '''
            properties = np.array(list(map(lambda peaks2D, I2D, V2D, Y2D:
                                           list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                                    {**prop1D,
                                                     **{k: v for k, v in zip(('I', 'V', Y_name, 'index'),
                                                                             (I1D[ind1D], V1D[ind1D], Y1D[ind1D], ind1D))}},
                                                    *list(zip(*peaks2D)), I2D, V2D, Y2D)),
                                           peaks, I, V, Y)))
        elif self.scan_dim == 3:
            ''' critical current '''
            masks_c = map(lambda V_c3D, peaks_c3D:
                          map(lambda V_c2D, peaks_c2D:
                              map(lambda V_c1D, peak1D: np.logical_and(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                      np.mean(V_c1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)),
                                                                       np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                                     np.mean(V_c1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset)))),
                                  V_c2D, peaks_c2D),
                              V_c3D, peaks_c3D),
                          V_c, peaks_c)
            I_cs = np.array(list(map(lambda I_c3D, peaks_c3D, masks_c3D:
                                     list(map(lambda I_c2D, peaks_c2D, masks_c2D:
                                              list(map(lambda I_c1D, peak1D, masks_c1D:
                                                       I_c1D[peak1D[0][masks_c1D][0]],
                                                       I_c2D, peaks_c2D, masks_c2D)),
                                              I_c3D, peaks_c3D, masks_c3D)),
                                     I_c, peaks_c, masks_c)),
                            dtype=float)
            ''' retrapping current '''
            masks_r = map(lambda V_r3D, peaks_r3D:
                          map(lambda V_r2D, peaks_r2D:
                              map(lambda V_r1D, peak1D: np.logical_and(np.logical_not(np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                                     np.mean(V_r1D[peak1D[0]-np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset + self.V_offset))),
                                                                       np.logical_and((-tol_offset+self.V_offset) <= np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0),
                                                                                      np.mean(V_r1D[peak1D[0]+np.tile([np.arange(int(window)//2)+1], [len(peak1D[0]), 1]).T], axis=0) <= (+tol_offset+self.V_offset))),
                                  V_r2D, peaks_r2D),
                              V_r3D, peaks_r3D),
                          V_r, peaks_r)
            I_rs = np.array(list(map(lambda I_r3D, peaks_r3D, masks_r3D:
                                     list(map(lambda I_r2D, peaks_r2D, masks_r2D:
                                              list(map(lambda I_r1D, peak1D, masks_r1D:
                                                       I_r1D[peak1D[0][masks_r1D][0]],
                                                       I_r2D, peaks_r2D, masks_r2D)),
                                              I_r3D, peaks_r3D, masks_r3D)),
                                     I_r, peaks_r, masks_r)),
                            dtype=float)
            properties = np.array(list(map(lambda peaks3D, I3D, V3D, Y3D:
                                           list(map(lambda peaks2D, I2D, V2D, Y2D:
                                                    list(map(lambda ind1D, prop1D, I1D, V1D, Y1D:
                                                             {**prop1D,
                                                              **{k: v for k, v in zip(('I', 'V', Y_name, 'index'),
                                                                                      (I1D[ind1D], V1D[ind1D], Y1D[ind1D], ind1D))}},
                                                             *list(zip(*peaks2D)), I2D, V2D, Y2D)),
                                                    peaks3D, I3D, V3D, Y3D)),
                                           peaks, I, V, Y)))
        else:
            raise ValueError('Scan dimension must be in {1, 2, 3}')
        if Ir:
            return I_cs, I_rs, properties
        else:
            return I_cs, properties