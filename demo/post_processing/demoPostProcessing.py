import copy
import json
import pathlib
import re

import matplotlib.pyplot as plt

from pysrc.auxiliary.core.GRID import GRID
from pysrc.auxiliary.core.SHC import SHC
from pysrc.auxiliary.load_file.LoadGIA import LoadGIA
from pysrc.auxiliary.load_file.LoadL2LowDeg import LoadLowDegree
from pysrc.auxiliary.load_file.LoadNoah import get_TWS_series
from pysrc.auxiliary.load_file.LoadShp import ShpToMask
from pysrc.auxiliary.preference.EnumClasses import L2LowDegreeFileID, L2InstituteType, L2Release, SHCDecorrelationType, \
    SHCFilterType, LeakageMethod, GIAModel, BasinName, SHCDecorrelationSlidingWindowType, L2ProductType
from pysrc.auxiliary.scripts.MatchConfigWithEnums import match_config
from pysrc.auxiliary.tools.FileTool import FileTool
from pysrc.auxiliary.tools.MathTool import MathTool
from pysrc.auxiliary.tools.TimeTool import TimeTool
from pysrc.post_processing.GIA_correction.GIACorrectionSpectral import GIACorrectionSpectral
from pysrc.post_processing.Love_number.LoveNumber import LoveNumber
from pysrc.post_processing.convert_field_physical_quantity.ConvertSHC import ConvertSHC, FieldPhysicalQuantity
from pysrc.auxiliary.load_file.LoadL2SH import LoadL2SH, load_SH_simple
from pysrc.auxiliary.scripts.PlotGrids import plot_grids
from pysrc.post_processing.filter.DDK import DDK, DDKFilterType
from pysrc.post_processing.filter.GetSHCFilter import get_shc_decorrelation, get_shc_filter
from pysrc.post_processing.leakage.Addictive import Addictive
from pysrc.post_processing.leakage.BaseModelDriven import ModelDriven
from pysrc.post_processing.leakage.BufferZone import BufferZone
from pysrc.post_processing.leakage.DataDriven import DataDriven
from pysrc.post_processing.leakage.ForwardModeling import ForwardModeling
from pysrc.post_processing.leakage.GetLeakageDeductor import get_leakage_deductor
from pysrc.post_processing.leakage.Iterative import Iterative
from pysrc.post_processing.leakage.Multiplicative import Multiplicative

from pysrc.post_processing.harmonic.Harmonic import Harmonic

import datetime

from pysrc.post_processing.leakage.Scaling import Scaling
from pysrc.post_processing.leakage.ScalingGrid import ScalingGrid
from pysrc.post_processing.replace_low_deg.ReplaceLowDegree import ReplaceLowDegree


class PostProcessingConfig:
    def __init__(self):
        self.__begin_date = datetime.date(2005, 1, 1)
        self.__end_date = datetime.date(2015, 12, 31)
        self.__basin = BasinName.Amazon

        self.__GRACE_institute = L2InstituteType.CSR
        self.__GRACE_release = L2Release.RL06

        self.__lmax = 60

        self.__grid_space = 1

        self.__replace_low_degree_coefficients = ('degree1', 'c20', 'c30')
        self.__low_degree_degree1_file_id = L2LowDegreeFileID.TN13
        self.__low_degree_c20_file_id = L2LowDegreeFileID.TN14
        self.__low_degree_c30_file_id = L2LowDegreeFileID.TN14

        self.__de_correlation_method = SHCDecorrelationType.PnMm
        self.__de_correlation_sliding_window_type = SHCDecorrelationSlidingWindowType.Wahr2006
        self.__de_correlation_params = (3, 5,)

        self.__shc_filter = SHCFilterType.Gaussian
        self.__shc_filter_params = (300,)

        self.__leakage_type = LeakageMethod.Scaling

        self.__GIA_model = GIAModel.ICE6GD

    def set_from_json(self, filepath: str or pathlib.WindowsPath or dict):
        """
        :param filepath: json filepath, or a dict loaded from json.
        """
        assert type(filepath) in (str, pathlib.WindowsPath, dict)

        if type(filepath) in (str, pathlib.WindowsPath):
            with open(filepath, 'r') as f:
                dict_from_jason = json.load(f)

        elif type(filepath) in (dict,):
            dict_from_jason = filepath

        else:
            return -1

        assert ({'begin_date',
                 'end_date',
                 'basin',
                 'GRACE_institute',
                 'GRACE_release',
                 'lmax',
                 'replace_low_degree',
                 'low_degree_degree1_file_id',
                 'low_degree_c20_file_id',
                 'low_degree_c30_file_id',
                 'de_correlation',
                 'de_correlation_sliding_window_type',
                 'de_correlation_params',
                 'shc_filter',
                 'shc_filter_params',
                 'leakage_method',
                 'GIA_model'} <= set(dict_from_jason.keys()))

        self.set_begin_date(dict_from_jason['begin_date'])
        self.set_end_date(dict_from_jason['end_date'])
        self.set_lmax(dict_from_jason['lmax'])
        self.set_replace_low_degree_coefficients(dict_from_jason['replace_low_degree'])
        self.set_de_correlation_params(dict_from_jason['de_correlation_params'])

        self.set_shc_filter_params(dict_from_jason['shc_filter_params'])

        enum_classes = [
            L2InstituteType, L2Release, L2LowDegreeFileID, L2LowDegreeFileID, L2LowDegreeFileID,
            SHCDecorrelationType, SHCDecorrelationSlidingWindowType, SHCFilterType, LeakageMethod, GIAModel
        ]

        json_keys = [
            'GRACE_institute', 'GRACE_release', 'low_degree_degree1_file_id', 'low_degree_c20_file_id',
            'low_degree_c30_file_id', 'de_correlation', 'de_correlation_sliding_window_type', 'shc_filter',
            'leakage_method', 'GIA_model'
        ]

        setting_functions = [
            self.set_GRACE_institute, self.set_GRACE_release, self.set_degree1_file_id,
            self.set_c20_file_id, self.set_c30_file_id, self.set_de_correlation_method,
            self.set_de_correlation_sliding_window_mode, self.set_shc_filter_method, self.set_leakage_method,
            self.set_GIA_model
        ]

        if dict_from_jason['basin'] in BasinName.__members__.keys():
            enum_classes.append(BasinName)
            json_keys.append('basin')
            setting_functions.append(self.set_basin)

        else:
            self.set_basin(pathlib.Path(dict_from_jason['basin']))

        match_config(dict_from_jason, json_keys, enum_classes, setting_functions)

        return self

    def export_json(self, filepath: str or pathlib.WindowsPath):
        pass

    def set_begin_date(self, d):

        if type(d) is datetime.date:
            self.__begin_date = d

        elif type(d) is str:
            re_match = re.match(r'(\d{4})-(\d{1,2})-*(\d{1,2})*', d)
            year, month, day = re_match.groups()
            if day is None:
                day = 1

            self.__begin_date = datetime.date(int(year), int(month), int(day))

        else:
            return -1

        return self

    def get_begin_date(self):
        return self.__begin_date

    def set_end_date(self, d):

        if type(d) is datetime.date:
            self.__end_date = d

        elif type(d) is str:
            re_match = re.match(r'(\d{4})-(\d{1,2})-*(\d{1,2})*', d)
            year, month, day = re_match.groups()

            if day is None:
                day = TimeTool.get_the_final_day_of_this_month(datetime.date(int(year), int(month), 1)).day

            self.__end_date = datetime.date(int(year), int(month), int(day))

        else:
            return -1

        return self

    def get_end_date(self):
        return self.__end_date

    def set_basin(self, basin: BasinName or pathlib.WindowsPath or str):
        """
        :param basin: a preset BasinName class or a pathlib.WindowsPath or str that describes a relative filepath.
                    if a path, it should be a spherical harmonic coefficient file to describe the kernel, or a shpfile,
                    and the filepath should be related to '*project_dir*/'
        """
        self.__basin = basin

        return self

    def get_basin(self):
        return self.__basin

    def set_GRACE_institute(self, institute: L2InstituteType or str):
        assert type(institute) in (L2InstituteType, str)
        if type(institute) is L2InstituteType:
            self.__GRACE_institute = institute
        else:
            self.__GRACE_institute = L2InstituteType[institute]

        return self

    def get_GRACE_institute(self):
        return self.__GRACE_institute

    def set_GRACE_release(self, release: L2Release):
        self.__GRACE_release = release

        return self

    def get_GRACE_release(self):
        return self.__GRACE_release

    def set_lmax(self, lmax: int):
        self.__lmax = lmax

        return self

    def get_lmax(self):
        return int(self.__lmax)

    def set_grid_space(self, gs: int):
        self.__grid_space = gs

        return self

    def get_grid_space(self):
        return self.__grid_space

    def set_replace_low_degree_coefficients(self, replace_coefficients):
        """
        :param replace_coefficients: a tuple that contains (or not) "degree1", "c20", "c30".
        """
        self.__replace_low_degree_coefficients = replace_coefficients

        return self

    def get_replace_low_degree_coefficients(self):
        return self.__replace_low_degree_coefficients

    def set_degree1_file_id(self, file_id: L2LowDegreeFileID):
        self.__low_degree_degree1_file_id = file_id

        return self

    def get_degree1_file_id(self):
        return self.__low_degree_degree1_file_id

    def set_c20_file_id(self, file_id: L2LowDegreeFileID):
        self.__low_degree_c20_file_id = file_id

        return self

    def get_c20_file_id(self):
        return self.__low_degree_c20_file_id

    def set_c30_file_id(self, file_id: L2LowDegreeFileID):
        self.__low_degree_c30_file_id = file_id

        return self

    def get_c30_file_id(self):
        return self.__low_degree_c30_file_id

    def set_de_correlation_method(self, method: SHCDecorrelationType):
        self.__de_correlation_method = method

        return self

    def get_de_correlation_method(self):
        return self.__de_correlation_method

    def set_de_correlation_params(self, params: tuple):
        """
        :param params: (n, m) for PnMm method;
                    (n, m, window length) for sliding window (stable) method;
                    (n, m, minimize window length, A, K) for sliding window (Wahr2006) method;
        """
        self.__de_correlation_params = params

        return self

    def get_de_correlation_params(self):
        return self.__de_correlation_params

    def set_de_correlation_sliding_window_mode(self, method: SHCDecorrelationSlidingWindowType):
        self.__de_correlation_sliding_window_type = method

        return self

    def get_de_correlation_sliding_window_mode(self):
        return self.__de_correlation_sliding_window_type

    def set_shc_filter_method(self, method: SHCFilterType):
        self.__shc_filter = method

        return self

    def get_shc_filter_method(self):
        return self.__shc_filter

    def set_shc_filter_params(self, params: tuple):
        """
        :param params: (radius[km], ) for Gaussian,
                    (radius_1[km], radius_2[km]) for Fan,
                    (radius_1[km], radius_2[km], m_0) for AnisotropicGaussianHan,
                    (DDKFilterType, ) for DDK
        """

        self.__shc_filter_params = params

        return self

    def get_shc_filter_params(self):
        return self.__shc_filter_params

    def set_leakage_method(self, method: LeakageMethod):
        self.__leakage_type = method

        return self

    def get_leakage_method(self):
        return self.__leakage_type

    def set_GIA_model(self, model: GIAModel):
        self.__GIA_model = model

        return self

    def get_GIA_model(self):
        return self.__GIA_model


class PostProcessing:
    def __init__(self):
        self.configuration = PostProcessingConfig()

        self.times = None
        self.time_series_ewh = []

        self.shc_GRACE = None
        self.filtered_shc = None
        self.shc_basin = None

        self.grid = None
        self.filtered_grid = None

        self.basin_map = None

        self.harmonic = None
        self.shc_filter = None

        self.auxiliary_data = {}

    def prepare(self):
        lmax = self.configuration.get_lmax()
        grid_space = self.configuration.get_grid_space()

        lat, lon = MathTool.get_global_lat_lon_range(grid_space)
        har = Harmonic(lat, lon, lmax, option=1)

        self.harmonic = har

        return self

    def load_files(self):
        self.__load_basin()
        self.__load_GRACE_shc_and_replace_low_degree()

        return self

    def __load_basin(self):

        lmax = self.configuration.get_lmax()

        basin = self.configuration.get_basin()

        if isinstance(basin, BasinName):
            basin_name = basin.name
            basin_shc_filepath = FileTool.get_project_dir() / f'data/basin_mask/{basin_name}_maskSH.dat'
            basin_clm, basin_slm = load_SH_simple(basin_shc_filepath, key='', lmcs_in_queue=(1, 2, 3, 4), lmax=lmax)
            shc_basin = SHC(basin_clm, basin_slm)

            basin_map = self.harmonic.synthesis(shc_basin).data

        elif type(basin) is pathlib.WindowsPath:
            shp_filepath = FileTool.get_project_dir() / basin

            grid_space = self.configuration.get_grid_space()

            load_shp = ShpToMask()
            load_shp.configuration.set_grid_space(grid_space)

            load_shp.configuration.set_shppath(shp_filepath)

            basin_map = load_shp.get_basin_gridmap(with_whole=True)

            basin_grid = GRID(basin_map, lat=self.harmonic.lat, lon=self.harmonic.lon)
            shc_basin = self.harmonic.analysis(basin_grid)

        else:
            return -1

        self.shc_basin = shc_basin
        self.basin_map = basin_map

        return self

    def __load_GRACE_shc_and_replace_low_degree(self, background="average"):
        """
        :param background: average, None or class SHC
        """

        '''load GRACE L2 SH products'''
        begin_date, end_date = self.configuration.get_begin_date(), self.configuration.get_end_date()
        institute = self.configuration.get_GRACE_institute()
        lmax = self.configuration.get_lmax()

        load = LoadL2SH()

        load.configuration.set_begin_date(begin_date)
        load.configuration.set_end_date(end_date)
        load.configuration.set_institute(institute)
        load.configuration.set_lmax(lmax)

        shc, dates = load.get_shc(with_dates=True)
        ave_dates_GRACE = TimeTool.get_average_dates(*dates)

        '''load and replace low degrees'''
        degree1_or_not = 'degree1' in self.configuration.get_replace_low_degree_coefficients()
        degree1_file_id = self.configuration.get_degree1_file_id()

        c20_or_not = 'c20' in self.configuration.get_replace_low_degree_coefficients()
        c20_file_id = self.configuration.get_c20_file_id()

        c30_or_not = 'c30' in self.configuration.get_replace_low_degree_coefficients()
        c30_file_id = self.configuration.get_c30_file_id()

        low_degs = {}

        if degree1_or_not:
            load_deg1 = LoadLowDegree()
            load_deg1.configuration.set_file_id(degree1_file_id).set_institute(institute)
            low_degs.update(load_deg1.get_degree1())

        if c20_or_not:
            load_c20 = LoadLowDegree()
            load_c20.configuration.set_file_id(c20_file_id)
            low_degs.update(load_c20.get_c20())

        if c30_or_not:
            load_c30 = LoadLowDegree()
            load_c30.configuration.set_file_id(c30_file_id)
            low_degs.update(load_c30.get_c30())

        rep = ReplaceLowDegree()
        rep.configuration.set_replace_deg1(degree1_or_not).set_replace_c20(c20_or_not).set_replace_c30(c30_or_not)
        rep.set_low_degrees(low_degs)

        shc = rep.apply_to(shc, dates[0], dates[1])

        '''deduct background'''
        if background is not None:
            shc.de_background(background=None if background == 'average' else background)

        self.times = ave_dates_GRACE
        self.shc_GRACE = shc

        return self

    def correct_gia(self):
        gia_model = self.configuration.get_GIA_model()
        lmax = self.configuration.get_lmax()

        load_gia = LoadGIA()
        load_gia.configuration.set_lmax(lmax)
        load_gia.configuration.set_GIA_model(gia_model)

        shc_gia_trend = load_gia.get_shc()

        gia = GIACorrectionSpectral()
        gia.configuration.set_times(self.times)
        gia.configuration.set_gia_trend(shc_gia_trend)

        self.shc_GRACE = gia.apply_to(self.shc_GRACE)

    def de_correlation(self):
        decorrelation_method = self.configuration.get_de_correlation_method()
        decorrelation_params = self.configuration.get_de_correlation_params()
        decorrelation_sliding_window_mode = self.configuration.get_de_correlation_sliding_window_mode()

        if self.filtered_shc is not None:
            shc_tobe_filtered = self.filtered_shc
        else:
            shc_tobe_filtered = self.shc_GRACE

        if decorrelation_method is None:
            shc_filtered = copy.deepcopy(shc_tobe_filtered)
        else:
            decorrelation = get_shc_decorrelation(decorrelation_method, decorrelation_params,
                                                  decorrelation_sliding_window_mode)
            shc_filtered = decorrelation.apply_to(shc_tobe_filtered)

        self.filtered_shc = shc_filtered

    def filter(self):
        shc_filter_method = self.configuration.get_shc_filter_method()
        shc_filter_params = self.configuration.get_shc_filter_params()
        lmax = self.configuration.get_lmax()

        shc_filter = get_shc_filter(shc_filter_method, shc_filter_params, lmax)

        if self.filtered_shc is not None:
            shc_filtered = shc_filter.apply_to(self.filtered_shc)

        else:
            shc_filtered = shc_filter.apply_to(self.shc_GRACE)

        self.filtered_shc = shc_filtered
        self.shc_filter = shc_filter

        return self

    def shc_to_grid(self, field_type=FieldPhysicalQuantity.EWH):
        # assert field_type == FieldPhysicalQuantity.EWH, "Only EWH is supported for now."

        lmax = self.configuration.get_lmax()

        if self.filtered_shc is not None:
            shc_tobe_processed_list = [self.shc_GRACE, self.filtered_shc]
        else:
            shc_tobe_processed_list = [self.shc_GRACE, ]

        '''convert shc quantity to ewh'''
        for i in range(len(shc_tobe_processed_list)):
            shc_tobe_processed = shc_tobe_processed_list[i]
            convert = ConvertSHC()
            convert.configuration.set_output_type(field_type)
            LN = LoveNumber()
            LN.configuration.set_lmax(lmax)
            ln = LN.get_Love_number()
            convert.configuration.set_Love_number(ln)
            shc = convert.apply_to(shc_tobe_processed)

            if i == 0:
                self.shc_GRACE = shc

            else:
                self.filtered_shc = shc

        '''harmonic synthesis to grid'''
        har = self.harmonic
        special = field_type if field_type in (
            FieldPhysicalQuantity.HorizontalDisplacementEast,
            FieldPhysicalQuantity.HorizontalDisplacementNorth) else None
        grid = har.synthesis(shc, special_type=special)

        if self.filtered_shc is not None:
            self.filtered_grid = grid
        else:
            self.grid = grid

        return self

    def correct_leakage(self):
        leakage_method = self.configuration.get_leakage_method()
        leakage = get_leakage_deductor(leakage_method)

        if isinstance(leakage, ModelDriven):
            assert self.filtered_grid is not None
            assert self.harmonic is not None

            leakage.configuration.set_harmonic(self.harmonic)
            leakage.configuration.set_filter(self.shc_filter)

            '''load noah ewh'''
            noah_model, model_times = get_TWS_series(self.configuration.get_begin_date(),
                                                     self.configuration.get_end_date())

            leakage.configuration.set_model(noah_model)
            leakage.configuration.set_model_times(model_times)

            leakage.configuration.set_GRACE_times(self.times)

            for i in range(len(self.basin_map)):
                this_basin_map = self.basin_map[i]

                leakage.configuration.set_basin(this_basin_map)
                this_basin_acreage = MathTool.get_acreage(this_basin_map)

                time_series_value = leakage.apply_to(self.filtered_grid) / this_basin_acreage
                self.time_series_ewh.append(time_series_value)

        elif type(leakage) is BufferZone:
            leakage = BufferZone()

            leakage.configuration.set_harmonic(self.harmonic)
            leakage.configuration.set_filter(self.shc_filter)

            for i in range(len(self.basin_map)):
                this_basin_map = self.basin_map[i]

                leakage.configuration.set_basin(this_basin_map)
                this_basin_acreage = MathTool.get_acreage(this_basin_map)

                time_series_value = leakage.apply_to(self.filtered_grid) / this_basin_acreage
                self.time_series_ewh.append(time_series_value)

        elif type(leakage) is ForwardModeling:
            leakage = ForwardModeling()

            leakage.configuration.set_harmonic(self.harmonic)
            leakage.configuration.set_filter(self.shc_filter)

            leakage.configuration.set_basin_conservation(FileTool.get_project_dir('data/basin_mask/Ocean_maskSH.dat'))

            for i in range(len(self.basin_map)):
                this_basin_map = self.basin_map[i]

                leakage.configuration.set_basin(this_basin_map)
                this_basin_acreage = MathTool.get_acreage(this_basin_map)

                time_series_value = leakage.apply_to(self.filtered_grid) / this_basin_acreage
                self.time_series_ewh.append(time_series_value)

        elif type(leakage) is DataDriven:
            leakage = DataDriven()

            leakage.configuration.set_harmonic(self.harmonic)
            leakage.configuration.set_filter(self.shc_filter)
            leakage.configuration.set_shc_unfiltered(self.shc_GRACE)

            for i in range(len(self.basin_map)):
                this_basin_map = self.basin_map[i]

                leakage.configuration.set_basin(this_basin_map)
                this_basin_acreage = MathTool.get_acreage(this_basin_map)

                time_series_value = leakage.apply_to(self.filtered_grid) / this_basin_acreage
                self.time_series_ewh.append(time_series_value)

        elif type(leakage) is Iterative:
            leakage = Iterative()

            leakage.configuration.set_harmonic(self.harmonic)
            leakage.configuration.set_filter(self.shc_filter)
            leakage.configuration.set_shc_unfiltered(self.shc_GRACE)

            for i in range(len(self.basin_map)):
                this_basin_map = self.basin_map[i]

                leakage.configuration.set_basin(this_basin_map)
                this_basin_acreage = MathTool.get_acreage(this_basin_map)

                time_series_value = leakage.apply_to(self.filtered_grid) / this_basin_acreage
                self.time_series_ewh.append(time_series_value)

        else:
            print("Unsupported leak correction method.")
            return -1

        return self

    def basin_average(self):
        if self.filtered_grid is not None:
            grid_tobe_processed = self.filtered_grid

        else:
            grid_tobe_processed = self.grid

        assert grid_tobe_processed is not None

        for i in range(len(self.basin_map)):
            this_basin_map = self.basin_map[i]

            this_basin_acreage = MathTool.get_acreage(this_basin_map)

            self.time_series_ewh.append(
                MathTool.global_integral(grid_tobe_processed.data * this_basin_map) / this_basin_acreage)

        return self

    def get_year_fraction(self):
        return TimeTool.convert_date_format(self.times,
                                            input_type=TimeTool.DateFormat.ClassDate,
                                            output_type=TimeTool.DateFormat.YearFraction)

    def get_ewh(self):
        if self.time_series_ewh is None:
            self.basin_average()

        return self.time_series_ewh


def demo():
    pp = PostProcessing()
    jsonpath = FileTool.get_project_dir() / 'setting/post_processing/PostProcessing.json'
    pp.configuration.set_from_json(jsonpath)

    pp.prepare()
    pp.load_files()  # load GRACE SHC, and replace low-degrees
    pp.correct_gia()  # GIA correction
    pp.de_correlation()  # de-correlation filter
    pp.filter()  # low-pass filter
    pp.shc_to_grid(field_type=FieldPhysicalQuantity.EWH)  # synthesis harmonic to (EWH) grid

    pp.basin_average()
    pp.correct_leakage()

    times = pp.get_year_fraction()
    ewh = pp.get_ewh()

    plt.plot(times, ewh[0], label='uncorrected')
    plt.plot(times, ewh[1], label='corrected')
    plt.legend()
    plt.show()


if __name__ == '__main__':
    demo()
