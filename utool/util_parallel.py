"""
There are a lot of fancier things we can do here.
A good thing to do would be to keep similar function calls
and use multiprocessing.Queues for the backend.
This way we can print out progress.

"""
from __future__ import absolute_import, division, print_function
import multiprocessing
import atexit
import sys
import signal
import six
if six.PY2:
    import thread as _thread
elif six.PY3:
    import _thread
import threading
from utool._internal.meta_util_six import get_funcname
from utool import util_progress
from utool import util_time
from utool import util_arg
from utool import util_dbg
from utool import util_inject
#from utool.util_cplat import WIN32
util_inject.noinject('[parallel]')

QUIET   = util_arg.QUIET
SILENT  = util_arg.SILENT
VERBOSE = util_arg.VERBOSE
STRICT  = util_arg.STRICT

if SILENT:
    def print(msg):
        pass

__POOL__ = None
__TIME_GENERATE__   = util_arg.get_flag('--time-generate')
__NUM_PROCS__       = util_arg.get_argval('--num-procs', int, default=None)
__FORCE_SERIAL__    = util_arg.get_argflag(('--utool-force-serial', '--force-serial', '--serial'))
__SERIAL_FALLBACK__ = not util_arg.get_flag('--noserial-fallback')


BACKEND = 'multiprocessing'

if BACKEND == 'gevent':
    raise NotImplementedError('gevent cannot run on multiple cpus')
    pass
elif BACKEND == 'zeromq':
    # TODO: Implement zeromq backend
    #http://zguide.zeromq.org/py:mtserver
    raise NotImplementedError('no zeromq yet')
    pass
elif BACKEND == 'multiprocessing':
    """
    expecting
    multiprocessing.__file__ = /usr/lib/python2.7/multiprocessing/__init__.pyc
    multiprocessing.__version__ >= 0.70a1

    BUT PIP SAYS:
        INSTALLED: 2.6.2.1 (latest)

    because multiprocessing on pip is: Backport of the multiprocessing package to Python 2.4 and 2.5

    ut.editfile(multiprocessing.__file__)
    from multiprocessing.pool import ThreadPool
    """
    def new_pool(num_procs, init_worker, maxtasksperchild):
        return multiprocessing.Pool(processes=num_procs,
                                    initializer=init_worker,
                                    maxtasksperchild=maxtasksperchild)
    pass


def set_num_procs(num_procs):
    global __NUM_PROCS__
    __NUM_PROCS__ = num_procs


def in_main_process():
    """ Returns if you are executing in a multiprocessing subprocess
    Usefull to disable init print messages on windows """
    return multiprocessing.current_process().name == 'MainProcess'


def get_default_numprocs():
    if __NUM_PROCS__ is not None:
        return __NUM_PROCS__
    #if WIN32:
    #    num_procs = 3  # default windows to 3 processes for now
    #else:
    #    num_procs = max(multiprocessing.cpu_count() - 2, 1)
    num_procs = max(multiprocessing.cpu_count() - 1, 1)
    return num_procs


def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def init_pool(num_procs=None, maxtasksperchild=None):
    global __POOL__
    if num_procs is None:
        # Get number of cpu cores
        num_procs = get_default_numprocs()
    if not QUIET:
        print('[util_parallel.init_pool] initializing pool with %d processes' % num_procs)
    if num_procs == 1:
        print('[util_parallel.init_pool] num_procs=1, Will process in serial')
        __POOL__ = 1
        return
    if STRICT:
        #assert __POOL__ is None, 'pool is a singleton. can only initialize once'
        assert multiprocessing.current_process().name, 'can only initialize from main process'
    if __POOL__ is not None:
        print('[util_parallel.init_pool] close pool before reinitializing')
        return
    # Create the pool of processes
    #__POOL__ = multiprocessing.Pool(processes=num_procs, initializer=init_worker, maxtasksperchild=maxtasksperchild)
    __POOL__ = new_pool(num_procs, init_worker, maxtasksperchild)


@atexit.register
def close_pool(terminate=False):
    global __POOL__
    if __POOL__ is not None:
        if not QUIET:
            if terminate:
                print('[util_parallel] terminating pool')
            else:
                print('[util_parallel] closing pool')
        if not isinstance(__POOL__, int):
            # Must join after close to avoid runtime errors
            if terminate:
                __POOL__.terminate()
            __POOL__.close()
            __POOL__.join()
        __POOL__ = None


def _process_serial(func, args_list, args_dict={}, nTasks=None):
    """
    Serial process map
    """
    if nTasks is None:
        nTasks = len(args_list)
    result_list = []
    mark_prog, end_prog = util_progress.progress_func(
        max_val=nTasks, lbl=get_funcname(func) + ': ')
    mark_prog(0)
    # Execute each task sequentially
    for count, args in enumerate(args_list):
        result = func(*args, **args_dict)
        result_list.append(result)
        mark_prog(count)
    end_prog()
    return result_list


def _process_parallel(func, args_list, args_dict={}, nTasks=None):
    """
    Parallel process map
    """
    # Define progress observers
    if nTasks is None:
        nTasks = len(args_list)
    num_tasks_returned_ptr = [0]
    mark_prog, end_prog = util_progress.progress_func(
        max_val=nTasks, lbl=get_funcname(func) + ': ')
    def _callback(result):
        mark_prog(num_tasks_returned_ptr[0])
        sys.stdout.flush()
        num_tasks_returned_ptr[0] += 1
    # Send all tasks to be executed asynconously
    apply_results = [__POOL__.apply_async(func, args, args_dict, _callback)
                     for args in args_list]
    # Wait until all tasks have been processed
    while num_tasks_returned_ptr[0] < nTasks:
        #print('Waiting: ' + str(num_tasks_returned_ptr[0]) + '/' + str(nTasks))
        pass
    end_prog()
    # Get the results
    result_list = [ap.get() for ap in apply_results]
    return result_list


def _generate_parallel(func, args_list, ordered=True, chunksize=1,
                       prog=True, verbose=True, nTasks=None):
    """
    Parallel process generator
    """
    prog = prog and verbose
    if nTasks is None:
        nTasks = len(args_list)
    if chunksize is None:
        chunksize = max(1, nTasks // (__POOL__._processes ** 2))
    if verbose:
        print('[util_parallel._generate_parallel] executing %d %s tasks using %d processes with chunksize=%r' %
                (nTasks, get_funcname(func), __POOL__._processes, chunksize))
    #assert isinstance(__POOL__, multiprocessing.Pool),\
    #        '%r __POOL__ = %r' % (type(__POOL__), __POOL__,)
    if ordered:
        generator = __POOL__.imap(func, args_list, chunksize)
    else:
        generator = __POOL__.imap_unordered(func, args_list, chunksize)
    try:
        if prog:
            # New way of doing progress
            prog_generator = util_progress.ProgressIter(
                generator, nTotal=nTasks, lbl=get_funcname(func) + ': ')
            for result in prog_generator:
                yield result
        else:
            # No Progress
            for result in generator:
                yield result
    except Exception as ex:
        util_dbg.printex(ex, 'Parallel Generation Failed!', '[utool]')
        print('__SERIAL_FALLBACK__ = %r' % __SERIAL_FALLBACK__)
        if __SERIAL_FALLBACK__:
            for result in _generate_serial(func, args_list, prog=prog,
                                           verbose=verbose, nTasks=nTasks):
                yield result
        else:
            raise
    #close_pool()


def _generate_serial(func, args_list, prog=True, verbose=True, nTasks=None):
    """ internal serial generator  """
    if nTasks is None:
        nTasks = len(args_list)
    if verbose:
        print('[util_parallel._generate_serial] executing %d %s tasks in serial' %
                (nTasks, get_funcname(func)))
    prog = prog and verbose and nTasks > 1
    if prog:
        # New way of doing progress
        prog_generator = util_progress.ProgressIter(
            args_list, nTotal=nTasks, lbl=get_funcname(func) + ': ')
        for args in prog_generator:
            result = func(args)
            yield result
    else:
        # No Progress
        for args in args_list:
            result = func(args)
            yield result
    #for count, args in enumerate(args_list):
    #    if prog:
    #        mark_prog(count)
    #    result = func(args)
    #    yield result
    #if prog:
    #    end_prog()


def ensure_pool(warn=False):
    try:
        assert __POOL__ is not None, 'must init_pool() first'
    except AssertionError as ex:
        if warn:
            print('(WARNING) AssertionError: ' + str(ex))
        init_pool()


def generate(func, args_list, ordered=True, force_serial=__FORCE_SERIAL__,
             chunksize=1, prog=True, verbose=True, nTasks=None):
    """

    Args:
        func (function): function to apply each argument to
        args_list (list or iter): sequence of tuples which are args for each function call
        ordered (bool):
        force_serial (bool):
        chunksize (int):
        prog (bool):
        verbose (bool):
        nTasks (int): optional (must be specified if args_list is an iterator)

    Returns:
        generator which yeilds result of applying func to args in args_list

    CommandLine:
        python -m utool.util_parallel --test-generate

    Example:
        >>> # SLOW_DOCTEST
        >>> import utool as ut
        >>> num = 8700  # parallel is slower for smaller numbers
        >>> flag_generator0 = ut.generate(ut.is_prime, range(0, num), force_serial=True)
        >>> flag_list0 = list(flag_generator0)
        >>> flag_generator1 = ut.generate(ut.is_prime, range(0, num))
        >>> flag_list1 = list(flag_generator1)
        >>> assert flag_list0 == flag_list1

    """
    if nTasks is None:
        nTasks = len(args_list)
    if nTasks == 0:
        if VERBOSE and verbose:
            print('[util_parallel.generate] submitted 0 tasks')
        return iter([])
    if VERBOSE and verbose:
        print('[util_parallel.generate] ordered=%r' % ordered)
        print('[util_parallel.generate] force_serial=%r' % force_serial)
    force_serial_ = nTasks == 1 or force_serial
    if not force_serial_:
        ensure_pool()
    if __TIME_GENERATE__:
        tt = util_time.tic(get_funcname(func))
    if force_serial_ or isinstance(__POOL__, int):
        if VERBOSE and verbose:
            print('[util_parallel.generate] generate_serial')
        return _generate_serial(func, args_list, prog=prog, nTasks=nTasks)
    else:
        if VERBOSE and verbose:
            print('[util_parallel.generate] generate_parallel')
        return _generate_parallel(func, args_list, ordered=ordered,
                                  chunksize=chunksize, prog=prog,
                                  verbose=verbose, nTasks=nTasks)
    if __TIME_GENERATE__:
        util_time.toc(tt)


def process(func, args_list, args_dict={}, force_serial=__FORCE_SERIAL__,
            nTasks=None):
    """
    Use ut.generate rather than ut.process

    Args:
        func (func):
        args_list (list or iter):
        args_dict (dict):
        force_serial (bool):

    Returns:
        result of parallel map(func, args_list)

    CommandLine:
        python -m utool.util_parallel --test-process

    Example:
        >>> # SLOW_DOCTEST
        >>> import utool as ut
        >>> num = 8700  # parallel is slower for smaller numbers
        >>> flag_generator0 = ut.process(ut.is_prime, zip(range(0, num)), force_serial=True)
        >>> flag_list0 = list(flag_generator0)
        >>> flag_generator1 = ut.process(ut.is_prime, zip(range(0, num)), force_serial=False)
        >>> flag_list1 = list(flag_generator1)
        >>> assert flag_list0 == flag_list1
    """

    ensure_pool()
    if nTasks is None:
        nTasks = len(args_list)
    if __POOL__ == 1 or force_serial:
        if not QUIET:
            print('[util_parallel] executing %d %s tasks in serial' %
                  (nTasks, get_funcname(func)))
        result_list = _process_serial(func, args_list, args_dict, nTasks=nTasks)
    else:
        if not QUIET:
            print('[util_parallel] executing %d %s tasks using %d processes' %
                  (nTasks, get_funcname(func), __POOL__._processes))
        result_list = _process_parallel(func, args_list, args_dict, nTasks=nTasks)
    return result_list


def spawn_background_process(func, *args, **kwargs):
    """
    Run a function in the background
    (like rebuilding some costly data structure)

    References:
        http://stackoverflow.com/questions/1196074/starting-a-background-process-in-python
        http://stackoverflow.com/questions/15063963/python-is-thread-still-running

    Args:
        func (function):

    CommandLine:
        python -m utool.util_parallel --test-spawn_background_process

    Example:
        >>> # DISABLE_DOCTEST
        >>> from utool.util_parallel import *  # NOQA
        >>> import utool as ut
        >>> import time
        >>> from os.path import join
        >>> # build test data
        >>> fname = 'test_bgfunc_output.txt'
        >>> dpath = ut.get_app_resource_dir('utool')
        >>> ut.ensuredir(dpath)
        >>> fpath = join(dpath, fname)
        >>> # ensure file is not around
        >>> sleep_time = 1
        >>> ut.delete(fpath)
        >>> assert not ut.checkpath(fpath, verbose=True)
        >>> def backgrond_func(fpath, sleep_time):
        ...     import utool as ut
        ...     import time
        ...     print('[BG] Background Process has started')
        ...     time.sleep(sleep_time)
        ...     print('[BG] Background Process is writing')
        ...     ut.write_to(fpath, 'background process')
        ...     print('[BG] Background Process has finished')
        ...     #raise AssertionError('test exception')
        >>> # execute function
        >>> func = backgrond_func
        >>> args = (fpath, sleep_time)
        >>> kwargs = {}
        >>> print('[FG] Spawning process')
        >>> threadid = ut.spawn_background_process(func, *args, **kwargs)
        >>> assert threadid.is_alive() is True, 'thread should be active'
        >>> print('[FG] Spawned process. threadid=%r' % (threadid,))
        >>> # background process should not have finished yet
        >>> assert not ut.checkpath(fpath, verbose=True)
        >>> print('[FG] Waiting to check')
        >>> time.sleep(sleep_time + .1)
        >>> print('[FG] Finished waiting')
        >>> # Now the file should be there
        >>> assert ut.checkpath(fpath, verbose=True)
        >>> assert threadid.is_alive() is False, 'process should have died'
    """
    proc_obj = multiprocessing.Process(target=func, args=args, kwargs=kwargs)
    #proc_obj.isAlive = proc_obj.is_alive
    proc_obj.start()
    return proc_obj


def spawn_background_thread(func, *args, **kwargs):
    #threadobj = IMPLEMENTATION_NUM
    thread_obj = threading.Thread(target=func, args=args, kwargs=kwargs)
    thread_obj.start()
    return thread_obj


def _spawn_background_thread0(func, *args, **kwargs):
    thread_id = _thread.start_new_thread(func, args, kwargs)
    return thread_id


if __name__ == '__main__':
    """
    CommandLine:
        python -m utool.util_parallel
        python -m utool.util_parallel --allexamples
    """
    #import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
