#!/usr/bin/env python
from __future__ import absolute_import, division, print_function
import utool
import os
from os.path import basename
from utool._internal import util_importer


def makeinit(module_path):
    module_name = basename(module_path)
    IMPORT_TUPLES = util_importer.make_import_tuples(module_path)
    initstr = util_importer.make_initstr(module_name, IMPORT_TUPLES)
    print('### __init__.py ###')
    print(initstr)


if __name__ == '__main__':
    module_path = utool.unixpath(os.getcwd())
    makeinit(module_path)
    print('# autogenerated __init__.py for: %r' % module_path)
