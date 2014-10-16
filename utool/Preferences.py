"""
FIXME: This class is very old, convoluted, and coupled.
It really needs to be rewritten efficiently.
the __setattr__ __getattr__ stuff needs to be redone, and
DynStruct needs to go away.
"""
from __future__ import absolute_import, division, print_function
import six
from six.moves import cPickle
try:
    import numpy as np
except ImportError as ex:
    pass
from .DynamicStruct import DynStruct
from .util_dbg import printex
from .util_type import is_str, is_dict, try_cast
from . import util_inject
from . import util_type
print, print_, printDBG, rrr, profile = util_inject.inject(__name__, '[pref]')

# ---
# GLOBALS
# ---
PrefNode = DynStruct


def printDBG(msg):
    #print('[PREFS] '+msg)
    pass


# ---
# Classes
# ---
class PrefInternal(DynStruct):
    def __init__(_intern, name, doc, default, hidden, fpath, depeq, choices):
        super(PrefInternal, _intern).__init__(child_exclude_list=[])
        # self._intern describes this node
        _intern.name    = name     # A node has a name
        _intern.doc     = doc      # A node has a name
        _intern.value   = default  # A node has a value
        _intern.hidden  = hidden   # A node can be hidden
        _intern.fpath   = fpath    # A node is cached to
        _intern.depeq   = depeq    # A node depends on
        _intern._frozen_type = None     # A node's value type
        # Some preferences are constrained to a list of choices
        if choices is not None:
            _intern.value = PrefChoice(choices, default)

    def get_type(_intern):
        if _intern._frozen_type is not None:
            return _intern._frozen_type
        else:
            return type(_intern.value)

    def freeze_type(_intern):
        _intern._frozen_type = _intern.get_type()


class PrefTree(DynStruct):
    def __init__(_tree, parent):
        super(PrefTree, _tree).__init__(child_exclude_list=[])
        # self._tree describes node's children and the parents
        # relationship to them
        _tree.parent               = parent  # Children have parents
        _tree.hidden_children      = []  # Children can be hidden
        _tree.child_list           = []  # There can be many children
        _tree.child_names          = []  # Each child has a name
        _tree.num_visible_children = 0   # Statistic
        _tree.aschildx             = 0   # This node is the x-th child


class PrefChoice(DynStruct):
    def __init__(self, choices, default):
        super(PrefChoice, self).__init__(child_exclude_list=[])
        self.choices = choices
        self.sel = 0
        self.change_val(default)

    def change_val(self, new_val):
        # Try to select by index
        if isinstance(new_val, int):
            self.sel = new_val
        # Try to select by value
        elif isinstance(new_val, six.string_types):
            self.sel = self.choices.index(new_val)
        else:
            raise('Exception: Unknown newval=%r' % new_val)
        if self.sel < 0 or self.sel > len(self.choices):
            raise Exception('self.sel=%r is not in the self.choices=%r '
                            % (self.sel, self.choices))

    def combo_val(self):
        return self.choices[self.sel]

    def get_tuple(self):
        return (self.sel, self.choices)


class Pref(PrefNode):
    """
    Structure for Creating Preferences.
    Caveats: When using a value call with ['valname'] to be safe
    Features:
    * Can be saved and loaded.
    * Can be nested
    * Dynamically add/remove
    """
    def __init__(self,
                 default=PrefNode,  # Default value for a Pref is to be itself
                 doc='empty docs',  # Documentation for a preference
                 hidden=False,      # Is a hidden preference?
                 choices=None,      # A list of choices
                 depeq=None,        # List of tuples representing dependencies
                 fpath='',          # Where to save to
                 name='root',       # Name of this node
                 parent=None):      # Reference to parent Pref
        """
        Creates a pref struct that will save itself to pref_fpath if
        available and have init all members of some dictionary
        """
        super(Pref, self).__init__(child_exclude_list=['_intern', '_tree'])
        # Private internal structure
        self._intern = PrefInternal(name, doc, default, hidden, fpath, depeq, choices)
        self._tree = PrefTree(parent)
        #if default is PrefNode:
        #    printDBG('----------')
        #    printDBG('new Pref(default=PrefNode)')

    def get_type(self):
        return self._intern.get_type()

    def ensure_attr(self, attr, default):
        if not hasattr(self, attr):
            setattr(self, attr, default)

    # -------------------
    # Attribute Setters
    def toggle(self, key):
        """ Toggles a boolean key """
        val = self[key]
        assert isinstance(val, bool), 'key[%r] = %r is not a bool' % (key, val)
        self.pref_update(key, not val)

    def change_combo_val(self, new_val):
        """
        Checks to see if a selection is a valid index or choice of a combo
        preference
        """
        choice_obj = self._intern.value
        assert isinstance(self._intern.value, PrefChoice), 'must be a choice'
        return choice_obj.get_tuple()

    def __overwrite_child_attr(self, name, attr):
        #printDBG( "overwrite_attr: %s.%s = %r" % (self._intern.name, name, attr))
        # get child node to "overwrite"
        row = self._tree.child_names.index(name)
        child = self._tree.child_list[row]
        if isinstance(attr, Pref):
            # Do not break pointers when overwriting a Preference
            if issubclass(attr._intern.value, PrefNode):
                # Main Branch Logic
                for (key, val) in six.iteritems(attr):
                    child.__setattr__(key, val)
            else:
                self.__overwrite_child_attr(name, attr.value())
        else:  # Main Leaf Logic:
            #assert(not issubclass(child._intern.type, PrefNode), #(self.full_name() + ' Must be a leaf'))
            # Keep user-readonly map up to date with internals
            if isinstance(child._intern.value, PrefChoice):
                child.change_combo_val(attr)
            else:
                child_type = child._intern.get_type()
                attr_type  = type(attr)
                if child_type is not attr_type:
                    #print('WARNING TYPE DIFFERENCE! %r, %r' % (child_type, attr_type))
                    attr = try_cast(attr, child_type, attr)
                child._intern.value = attr
            self.__dict__[name] = child.value()

    def __new_attr(self, name, attr):
        """
        On a new child attribute:
            1) Check to see if it is wrapped by a Pref object
            2) If not do so, if so add it to the tree structure
        """
        if isinstance(attr, Pref):
            # Child attribute already has a Pref wrapping

            #printDBG( 'new_attr: %s.%s = %r' % (self._intern.name, name, attr.value()))
            new_childx = len(self._tree.child_names)
            # Children know about parents
            attr._tree.parent = self     # Give child parent
            attr._intern.name = name     # Give child name
            if attr._intern.depeq is None:
                attr._intern.depeq = self._intern.depeq  # Give child parent dependencies
            if attr._intern.hidden:
                self._tree.hidden_children.append(new_childx)
                self._tree.hidden_children.sort()
            # Used for QTIndexing
            attr._intern.aschildx = new_childx
            # Parents know about children
            self._tree.child_names.append(name)  # Add child to tree
            self._tree.child_list.append(attr)
            self.__dict__[name] = attr.value()   # Add child value to dict
        else:
            # The child attribute is not wrapped. Wrap with Pref and readd.
            pref_attr = Pref(default=attr)
            self.__new_attr(name, pref_attr)

    # Attributes are children
    def __setattr__(self, name, attr):
        """
        Called when an attribute assignment is attempted. This is called instead
        of the normal mechanism (i.e. store the value in the instance
        dictionary). name is the attribute name, value is the value to be
        assigned to it.

        If __setattr__() wants to assign to an instance attribute, it should not
        simply execute self.name = value  this would cause a recursive call to
        itself.  Instead, it should insert the value in the dictionary of
        instance attributes, e.g., self.__dict__[name] = value. For new-style
        classes, rather than accessing the instance dictionary, it should call
        the base class method with the same name, for example,
        object.__setattr__(self, name, value).
        'Wraps child attributes in a Pref object if not already done'
        """
        # No wrapping for private vars: _printable_exclude, _intern, _tree
        if name.find('_') == 0:
            return super(DynStruct, self).__setattr__(name, attr)
        # Overwrite if child exists
        if name in self._tree.child_names:
            self.__overwrite_child_attr(name, attr)
        else:
            self.__new_attr(name, attr)

    # -------------------
    # Attribute Getters
    def value(self):
        # Return the wrapper in all its glory
        if self._intern.value == PrefNode:
            return self
        # Return basic types
        elif isinstance(self._intern.value, PrefChoice):
            return self._intern.value.combo_val()
        else:
            return self._intern.value  # TODO AS REFERENCE

    def __getattr__(self, name):
        """
        Called when an attribute lookup has not found the attribute in the usual
        places
        (i.e. it is not an instance attribute nor is it found in the class tree
        for self).
        name is the attribute name.
        This method should return the (computed) attribute value or raise an
        AttributeError exception.
        Get a child from this parent called as last resort.
        Allows easy access to internal prefs
        """
        if name.find('_') == 0:
            # Names that start with underscore actually belong to the Pref object
            return super(PrefNode, self).__getitem__[name]
        if len(name) > 9 and name[-9:] == '_internal':
            # internal names belong to the internal structure
            attrx = self._tree.child_names.index(name[:-9])
            return self._tree.child_list[attrx]
        #print(self._internal.name)
        #print(self._tree)
        try:
            if six.PY2:
                return super(PrefNode, self).__getitem__[name]
            else:
                try:
                    base_self1 = super(PrefNode, self)
                    #base_self2 = super(DynStruct, self)
                    #base_self3 = super()
                    #import utool
                    #utool.embed()
                    return base_self1[name]
                except Exception as ex:
                    print(ex)
                    print('base_self1 = %r' % (base_self1,))
                    #print('base_self2 = %r' % (base_self2,))
                    #print('base_self3 = %r' % (base_self3,))
                    print('name = %r' % (name,))
                    raise
        except Exception as ex:
            if name == 'traid_names':
                # HACK FOR IPYTHON
                pass
            else:
                import utool
                utool.printex(ex, 'Pref object missing named attribute', keys=['self._intern.name', 'name'])
                raise AttributeError('Pref object is missing named attribute: name=%r'  % name)
                #raise

    def iteritems(self):
        """
        Wow this class is messed up. I had to overwrite items when
        moving to python3, just because I haden't called it yet
        """
        for (key, val) in six.iteritems(self.__dict__):
            if key in self._printable_exclude:
                continue
            yield (key, val)

    def items(self):
        """
        Wow this class is messed up. I had to overwrite items when
        moving to python3, just because I haden't called it yet
        """
        for (key, val) in six.iteritems(self.__dict__):
            if key in self._printable_exclude:
                continue
            yield (key, val)

    #----------------
    # Disk caching
    def to_dict(self, split_structs_bit=False):
        """ Converts prefeters to a dictionary.
        Children Pref can be optionally separated """
        pref_dict = {}
        struct_dict = {}
        for (key, val) in six.iteritems(self):
            if split_structs_bit and isinstance(val, Pref):
                struct_dict[key] = val
                continue
            pref_dict[key] = val
        if split_structs_bit:
            return (pref_dict, struct_dict)
        return pref_dict

    def save(self):
        'Saves prefs to disk in dict format'
        if self._intern.fpath in ['', None]:
            if self._tree.parent is not None:
                #printDBG('[save] Can my parent save me?')  # ...to disk
                return self._tree.parent.save()
            #printDBG('[save] I cannot be saved. I have no parents.')
            return False
        with open(self._intern.fpath, 'w') as f:
            print('[pref] Saving to ' + self._intern.fpath)
            pref_dict = self.to_dict()
            cPickle.dump(pref_dict, f)
        return True

    def load(self):
        #printDBG('[pref.load()]')
        """ Read pref dict stored on disk. Overwriting current values. """
        #if not os.path.exists(self._intern.fpath):
        #    msg = '[pref] fpath=%r does not exist' % (self._intern.fpath)
        #    #printDBG(msg)
        #    return msg
        try:
            with open(self._intern.fpath, 'r') as f:
                #printDBG('load: %r' % self._intern.fpath)
                pref_dict = cPickle.load(f)
        except EOFError as ex1:
            printex(ex1, 'did not load pref fpath=%r correctly' %
                    self._intern.fpath, iswarning=True)
            #warnings.warn(msg)
            raise
            #return msg
        except ImportError as ex2:
            printex(ex2, 'did not load pref fpath=%r correctly' %
                    self._intern.fpath, iswarning=True)
            #warnings.warn(msg)
            raise
            #return msg
        if not is_dict(pref_dict):
            raise Exception('Preference file is corrupted')
        self.add_dict(pref_dict)
        return True

    #----------------------
    # String representation
    def __str__(self):
        if self._intern.value != PrefNode:
            ret = super(PrefNode, self).__str__()
            #.replace('\n    ', '')
            ret += '\nLEAF ' + repr(self._intern.name) + ':' + repr(self._intern.value)
            return ret
        else:
            ret = repr(self._intern.value)
            return ret

    def full_name(self):
        'returns name all the way up the tree'
        if self._tree.parent is None:
            return self._intern.name
        return self._tree.parent.full_name() + '.' + self._intern.name

    def get_printable(self, type_bit=True, print_exclude_aug=[]):
        # Remove unsatisfied dependencies from the printed structure
        further_aug = print_exclude_aug[:]
        for child_name in self._tree.child_names:
            depeq = self[child_name + '_internal']._intern.depeq
            if depeq is not None and depeq[0].value() != depeq[1]:
                further_aug.append(child_name)
        return super(Pref, self).get_printable(type_bit, print_exclude_aug=further_aug)

    def customPrintableType(self, name):
        if name in self._tree.child_names:
            row = self._tree.child_names.index(name)
            #child = self._tree.child_list[row]  # child node to "overwrite"
            _typestr = type(self._tree.child_list[row]._intern.value)
            if is_str(_typestr):
                return _typestr

    def pref_update(self, key, new_val):
        """ Changes a preference value and saves it to disk """
        print('Update and save pref from: %s=%r, to: %s=%r' %
              (key, str(self[key]), key, str(new_val)))
        self.__setattr__(key, new_val)
        return self.save()

    def update(self, **kwargs):
        #print('Updating Preference: kwargs = %r' % (kwargs))
        self_keys = set(self.__dict__.keys())
        for key, val in six.iteritems(kwargs):
            if key in self_keys:
                #print('update: key=%r, %r' % (key, val))
                #if type(val) == types.ListType:
                    #val = val[0]
                self.__setattr__(key, val)

    # Method for QTWidget
    def createQWidget(self):
        # moving gui code away from utool
        try:
            #from utool._internal.PreferenceWidget import EditPrefWidget
            from guitool.PreferenceWidget import EditPrefWidget
            editpref_widget = EditPrefWidget(self)
            editpref_widget.show()
            return editpref_widget
        except ImportError as ex:
            printex(ex, 'Cannot create preference widget. Is guitool and PyQt 4/5 Installed')
            raise

    def qt_get_parent(self):
        return self._tree.parent

    def qt_parents_index_of_me(self):
        return self._tree.aschildx

    def qt_get_child(self, row):
        row_offset = (np.array(self._tree.hidden_children) <= row).sum()
        return self._tree.child_list[row + row_offset]

    def qt_row_count(self):
        return len(self._tree.child_list) - len(self._tree.hidden_children)

    def qt_col_count(self):
        return 2

    def qt_get_data(self, column):
        if column == 0:
            return self._intern.name
        data = self.value()
        if isinstance(data, Pref):  # Recursive Case: Pref
            data = ''
        elif data is None:
            # Check for a get of None
            data = 'None'
        return data

    def qt_is_editable(self):
        uneditable_hack = ['feat_type']
        self._intern.depeq
        if self._intern.name in uneditable_hack:
            return False
        if self._intern.depeq is not None:
            return self._intern.depeq[0].value() == self._intern.depeq[1]
        #return self._intern.value is not None
        return self._intern.value != PrefNode

    def qt_set_leaf_data(self, qvar):
        return _qt_set_leaf_data(self, qvar)


def _qt_set_leaf_data(self, qvar):
    """ Sets backend data using QVariants """
    #print('[pref] qt_set_leaf_data: qvar = %r' % qvar)
    #print('[pref] qt_set_leaf_data: _intern.name=%r' % self._intern.name)
    #print('[pref] qt_set_leaf_data: _intern.type_=%r' % self._intern.get_type())
    #print('[pref] qt_set_leaf_data: type(_intern.value)=%r' % type(self._intern.value))
    #print('[pref] qt_set_leaf_data: _intern.value=%r' % self._intern.value)
    ##print('[pref] qt_set_leaf_data: qvar.toString()=%s' % str(qvar.toString()))
    if self._tree.parent is None:
        raise Exception('[Pref.qtleaf] Cannot set root preference')
    if self.qt_is_editable():
        new_val = '[Pref.qtleaf] BadThingsHappenedInPref'
        if self._intern.value == PrefNode:
            raise Exception('[Pref.qtleaf] Qt can only change leafs')
        elif self._intern.value is None:
            # None could be a number of types
            def cast_order(var, order=[bool, int, float, str]):
                for type_ in order:
                    try:
                        ret = type_(var)
                        return ret
                    except Exception:
                        continue
            new_val = cast_order(str(qvar))
        self._intern.get_type()
        if isinstance(self._intern.value, bool):
            #new_val = bool(qvar.toBool())
            new_val = bool(qvar)
        elif isinstance(self._intern.value, int):
            #new_val = int(qvar.toInt()[0])
            new_val = int(qvar)
        # elif isinstance(self._intern.value, float):
        elif self._intern.get_type() in util_type.VALID_FLOAT_TYPES:
            #new_val = float(qvar.toDouble()[0])
            new_val = float(qvar)
        elif isinstance(self._intern.value, six.string_types):
            #new_val = str(qvar.toString())
            new_val = str(qvar)
        elif isinstance(self._intern.value, PrefChoice):
            #new_val = qvar.toString()
            new_val = str(qvar)
            if new_val.upper() == 'NONE':
                new_val = None
        else:
            try:
                #new_val = str(qvar.toString())
                type_ = self._intern.get_type()
                if type_ is not None:
                    new_val = type_(str(qvar))
                else:
                    new_val = str(qvar)
            except Exception:
                raise NotImplementedError(
                    ('[Pref.qtleaf] Unknown internal type. '
                     'type(_intern.value) = %r, '
                     '_intern.get_type() = %r, ')
                    % type(self._intern.value), self._intern.get_type())
        # Check for a set of None
        if isinstance(new_val, six.string_types):
            if new_val.upper() == 'NONE':
                new_val = None
            elif new_val.upper() == 'TRUE':
                new_val = True
            elif new_val.upper() == 'FALSE':
                new_val = False
        # save to disk after modifying data
        print('[pref] qt_set_leaf_data: new_val=%r' % new_val)
        print('[pref] qt_set_leaf_data: type(new_val)=%r' % type(new_val))
        # TODO Add ability to set a callback function when certain
        # preferences are changed.
        return self._tree.parent.pref_update(self._intern.name, new_val)
    return 'PrefNotEditable'
