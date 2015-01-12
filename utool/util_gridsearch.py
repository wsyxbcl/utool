""" module for gridsearch helper """
from __future__ import absolute_import, division, print_function
from collections import namedtuple, OrderedDict
from utool import util_class
from utool import util_inject
from utool import util_dict
import six
print, print_, printDBG, rrr, profile = util_inject.inject(__name__, '[gridsearch]')


DimensionBasis = namedtuple('DimensionBasis', ('dimension_name', 'dimension_point_list'))


def testdata_grid_search():
    """
    test data function for doctests
    """
    import utool as ut
    grid_basis = [
        ut.DimensionBasis('p', [.5, .8, .9, 1.0]),
        ut.DimensionBasis('K', [2, 3, 4, 5]),
        ut.DimensionBasis('clip_fraction', [.1, .2, .5, 1.0]),
    ]
    gridsearch = ut.GridSearch(grid_basis, label='testdata_gridsearch')
    for cfgdict in gridsearch:
        tp_score = cfgdict['p'] + (cfgdict['K'] ** .5)
        tn_score = (cfgdict['p'] * (cfgdict['K'])) / cfgdict['clip_fraction']
        gridsearch.append_result(tp_score, tn_score)
    return gridsearch


@six.add_metaclass(util_class.ReloadingMetaclass)
class GridSearch(object):
    """
    helper for executing iterations and analyzing the results of a grid search

    Example:
        >>> # ENABLE_DOCTEST
        >>> grid_basis = [
        ...     ut.DimensionBasis('p', [.5, .8, .9, 1.0]),
        ...     ut.DimensionBasis('K', [2, 3, 4, 5]),
        ...     ut.DimensionBasis('clip_fraction', [.1, .2, .5, 1.0]),
        ... ]
        >>> gridsearch = ut.GridSearch(grid_basis, label='testdata_gridsearch')
        >>> for cfgdict in gridsearch:
        ...    tp_score = cfgdict['p'] + (cfgdict['K'] ** .5)
        ...    tn_score = (cfgdict['p'] * (cfgdict['K'])) / cfgdict['clip_fraction']
        ...    gridsearch.append_result(tp_score, tn_score)
    """
    def __init__(gridsearch, grid_basis, label=None):
        gridsearch.label = label
        gridsearch.grid_basis = grid_basis
        gridsearch.tp_score_list = []
        gridsearch.tn_score_list = []
        gridsearch.score_diff_list = []
        cfgdict_iter = grid_search_generator(grid_basis)
        gridsearch.cfgdict_list = list(cfgdict_iter)
        gridsearch.num_configs = len(gridsearch.cfgdict_list)
        gridsearch.score_lbls  = ['score_diff', 'tp_score', 'tn_score']

    def append_result(gridsearch, tp_score, tn_score):
        """ for use in iteration """
        diff = tp_score - tn_score
        gridsearch.score_diff_list.append(diff)
        gridsearch.tp_score_list.append(tp_score)
        gridsearch.tn_score_list.append(tn_score)

    def __iter__(gridsearch):
        for cfgdict in gridsearch.cfgdict_list:
            yield cfgdict

    def __len__(gridsearch):
        return gridsearch.num_configs

    def get_score_list_and_lbls(gridsearch):
        """ returns result data """
        score_list  = [gridsearch.score_diff_list,
                       gridsearch.tp_score_list,
                       gridsearch.tn_score_list]
        score_lbls = gridsearch.score_lbls
        return score_list, score_lbls

    def get_param_list_and_lbls(gridsearch):
        """ returns input data """
        import utool as ut
        param_name_list = ut.get_list_column(gridsearch.grid_basis, 0)
        params_vals = [list(six.itervalues(dict_)) for dict_ in gridsearch.cfgdict_list]
        param_vals_list = list(zip(*params_vals))
        return param_name_list, param_vals_list

    def get_sorted_columns_and_labels(gridsearch, score_lbl='score_diff'):
        """ returns sorted input and result data """
        import utool as ut
        # Input Parameters
        param_name_list, param_vals_list = gridsearch.get_param_list_and_lbls()
        # Result Scores
        score_list, score_lbls = gridsearch.get_score_list_and_lbls()

        score_vals = score_list[score_lbls.index(score_lbl)]
        sortby_func = ut.make_sortby_func(score_vals, reverse=True)

        score_name_sorted = score_lbls
        param_name_sorted = param_name_list
        score_list_sorted = list(map(sortby_func, score_list))
        param_vals_sorted = list(map(sortby_func, param_vals_list))
        collbl_tup = (score_name_sorted, param_name_sorted,
                      score_list_sorted, param_vals_sorted)
        return collbl_tup

    def get_csv_results(gridsearch, max_lines=None, score_lbl='score_diff'):
        """
        Make csv text describing results

        Args:
            max_lines (int): add top num lines to the csv. No limit if None.
            score_lbl (str): score label to sort by

        Returns:
            str: result data in csv format

        CommandLine:
            python -m utool.util_gridsearch --test-get_csv_results

        Example:
            >>> # DISABLE_DOCTEST
            >>> from utool.util_gridsearch import *  # NOQA
            >>> import utool as ut
            >>> import plottool as pt
            >>> # build test data
            >>> score_lbl = 'score_diff'
            >>> gridsearch = testdata_grid_search()
            >>> csvtext = gridsearch.get_csv_results(10, score_lbl)
            >>> print(csvtext)
            >>> result = ut.hashstr(csvtext)
            >>> print(result)
            60yptleiwo@lk@24
        """
        import utool as ut
        collbl_tup = gridsearch.get_sorted_columns_and_labels(score_lbl)
        (score_name_sorted, param_name_sorted,
         score_list_sorted, param_vals_sorted) = collbl_tup

        # Build CSV
        column_lbls = score_name_sorted + param_name_sorted
        column_list = score_list_sorted + param_vals_sorted

        if max_lines is not None:
            column_list = [ut.listclip(col, max_lines) for col in column_list]
        header_raw_fmtstr = ut.codeblock(
            '''
            import utool as ut
            from utool import DimensionBasis
            title = 'Grid Search Results CSV'
            label = {label}
            grid_basis = {grid_basis_str}
            ''')
        fmtdict = dict(
            grid_basis_str=ut.list_str(gridsearch.grid_basis),
            label=gridsearch.label
        )
        header_raw = header_raw_fmtstr.format(**fmtdict)
        header     = ut.indent(header_raw, '# >>> ')
        precision = 3
        csvtext = ut.make_csv_table(column_list, column_lbls, header, precision=precision)
        return csvtext

    def get_rank_cfgdict(gridsearch, rank=0, score_lbl='score_diff'):
        import utool as ut
        collbl_tup = gridsearch.get_sorted_columns_and_labels(score_lbl)
        (score_name_sorted, param_name_sorted,
         score_list_sorted, param_vals_sorted) = collbl_tup
        rank_vals = ut.get_list_column(param_vals_sorted, rank)
        rank_cfgdict = dict(zip(param_name_sorted, rank_vals))
        return rank_cfgdict

    def get_dimension_stats(gridsearch, param_lbl, score_lbl='score_diff'):
        r"""
        Returns result stats about a specific parameter

        Args:
            param_lbl (str); paramter to get stats about
            score_lbl (str): score label to sort by

        Returns:
            dict: param2_score_stats
        """
        import utool as ut
        score_list, score_lbls = gridsearch.get_score_list_and_lbls()
        param_name_list, param_vals_list = gridsearch.get_param_list_and_lbls()
        param_vals = param_vals_list[param_name_list.index(param_lbl)]
        score_vals = score_list[score_lbls.index(score_lbl)]
        #sortby_func = ut.make_sortby_func(score_vals, reverse=True)
        #build_conflict_dict(param_vals, score_vals)
        param2_scores = ut.group_items(score_vals, param_vals)
        param2_score_stats = {
            param: ut.get_stats(scores)
            for param, scores in six.iteritems(param2_scores)
        }
        #print(ut.dict_str(param2_score_stats))
        return param2_score_stats

    def get_dimension_stats_str(gridsearch, param_lbl, score_lbl='score_diff'):
        r"""
        Returns a result stat string about a specific parameter
        """
        import utool as ut
        exclude_keys = ['nMin', 'nMax']
        param2_score_stats = gridsearch.get_dimension_stats(param_lbl)
        param2_score_stats_str = {
            param: ut.get_stats_str(stat_dict=stat_dict, exclude_keys=exclude_keys)
            for param, stat_dict in six.iteritems(param2_score_stats)}
        param_stats_str = 'stats(' + param_lbl + ') = ' + ut.dict_str(param2_score_stats_str)
        return param_stats_str

    def plot_dimension(gridsearch, param_lbl, score_lbl='score_diff',
                       **kwargs):
        r"""
        Plots result statistics about a specific parameter

        Args:
            param_lbl (str);
            score_lbl (str):

        CommandLine:
            python -m utool.util_gridsearch --test-plot_dimension
            python -m utool.util_gridsearch --test-plot_dimension --show

        Example:
            >>> # DISABLE_DOCTEST
            >>> from utool.util_gridsearch import *  # NOQA
            >>> import plottool as pt
            >>> # build test data
            >>> gridsearch = testdata_grid_search()
            >>> param_lbl = 'p'
            >>> score_lbl = 'score_diff'
            >>> self = gridsearch
            >>> self.plot_dimension('p', score_lbl, fnum=1, pnum=(1, 3, 1))
            >>> self.plot_dimension('K', score_lbl, fnum=1, pnum=(1, 3, 2))
            >>> self.plot_dimension('clip_fraction', score_lbl, fnum=1, pnum=(1, 3, 3))
            >>> pt.show_if_requested()
        """
        import plottool as pt
        param2_score_stats = gridsearch.get_dimension_stats(param_lbl, score_lbl)
        title = param_lbl + ' vs ' + score_lbl
        fig = pt.interval_stats_plot(param2_score_stats, x_label=param_lbl,
                                     y_label=score_lbl, title=title, **kwargs)
        return fig


def grid_search_generator(grid_basis=[], *args, **kwargs):
    r"""
    Iteratively yeilds individual configuration points
    inside a defined basis.

    Args:
        grid_basis (list): a list of 2-component tuple. The named tuple looks
            like this:

    CommandLine:
        python -m utool.util_gridsearch --test-grid_search_generator

    Example:
        >>> # ENABLE_DOCTEST
        >>> from utool.util_gridsearch import *  # NOQA
        >>> import utool as ut
        >>> # build test data
        >>> grid_basis = [
        ... DimensionBasis('dim1', [.1, .2, .3]),
        ... DimensionBasis('dim2', [.1, .4, .5]),
        ... ]
        >>> args = tuple()
        >>> kwargs = {}
        >>> # execute function
        >>> point_list = list(grid_search_generator(grid_basis))
        >>> # verify results
        >>> column_lbls = ut.get_list_column(grid_basis, 0)
        >>> column_list  = ut.get_list_column(grid_basis, 1)
        >>> first_vals = ut.get_list_column(ut.get_list_column(grid_basis, 1), 0)
        >>> column_types = list(map(type, first_vals))
        >>> header = 'grid search'
        >>> result = ut.make_csv_table(column_list, column_lbls, header, column_types)
        >>> print(result)
        grid search
        # num_rows=3
        #   dim1,  dim2
            0.10,  0.10
            0.20,  0.40
            0.30,  0.50

    """
    grid_basis_ = grid_basis + list(args) + list(kwargs.items())
    grid_basis_dict = OrderedDict(grid_basis_)
    grid_point_iter = util_dict.iter_all_dict_combinations_ordered(grid_basis_dict)
    for grid_point in grid_point_iter:
        yield grid_point


if __name__ == '__main__':
    """
    CommandLine:
        python -m utool.util_gridsearch
        python -m utool.util_gridsearch --allexamples
        python -m utool.util_gridsearch --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
