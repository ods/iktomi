'''
Data classes representing references to files in model objects. Manager class
for common operations with files. Manager encapsulate knowledge on where and
how to store transient and persistent files.
'''

import os
import cgi
import errno
from ...utils import cached_property


def _get_file_content(f):
    # XXX FieldStorage has no read()?
    if isinstance(f, cgi.FieldStorage):
        return f.value
    return f.read()


class BaseFile(object):

    def __init__(self, root, name):
        '''@root depends on environment of application and @name uniquely
        identifies the file.'''
        self.root = root
        self.name = name

    @property
    def path(self):
        return os.path.join(self.root, self.name)

    @cached_property
    def size(self):
        try:
            return os.path.getsize(self.full_path)
        # Return None for non-existing file.
        # There can be OSError or IOError (depending on Python version?), both
        # are derived from EnvironmentError having errno property.
        except EnvironmentError, exc:
            if exc.errno!=errno.ENOENT:
                raise

    def __repr__(self):
        return '{}({!r})'.format(type(self).__name__, self.name)


class TransientFile(BaseFile):
    pass


class PersistentFile(BaseFile):
    pass


class FileManager(object):

    def __init__(self, transient_root, persistent_root):
        self.transient_root = transient_root
        self.persistent_root = persistent_root

    def delete(self, file_obj):
        # XXX Is this right place again?
        #     BC "delete file if exist and ignore errors" would be used in many
        #     places, I think...
        if os.path.isfile(file_obj.path):
            try:
                os.unlink(file_obj.full_path)
            except OSError:
                pass

    def _copy_file(self, inp, path, length=None):
        # works for ajax file upload
        # XXX implement/debug for FieldStorage and file
        with open(path, 'wb') as fp:
            pos, bufsize = 0, 100000
            while pos < length:
                bufsize = min(bufsize, length-pos)
                data = inp.read(bufsize)
                fp.write(data)
                pos += bufsize

    def create_transient(self, input_stream, original_name, length=None):
        '''Create TransientFile and file on FS from given input stream and 
        original file name.'''
        ext = os.path.splitext(original_name)[1]
        transient = self.new_transient(ext)
        if not os.path.isdir(self.transient_root):
            os.makedirs(self.base_path)

        self._copy_file(input_stream, transient.path, length=length)
        return transient

    def new_transient(self, ext=''):
        '''Creates empty TransientFile with random name and given extension.
        File on FS is not created'''
        name = os.urandom(8).encode('hex') + ext
        return TransientFile(self.transient_root, name)

    def get_transient(self, name):
        '''Restores TransientFile object with given name.
        Should be used when form is submitted with file name and no file'''
        # security checks: basically no folders are allowed
        assert not ('/' in name or '\\' in name)
        transient = TransientFile(self.transient_root, name)
        if not os.path.isfile(transient.path):
            raise OSError('Transient file has been lost',
                          errno=errno.ENOENT,
                          filename=transient.path)
        return transient

    def get_persistent(self, name):
        assert name and not ('..' in name or name[0] in '~/')
        persistent = PersistentFile(self.persistent_root, name)
        return persistent

    def store(self, transient_file, persistent_name):
        '''Makes PersistentFile from TransientFile'''
        persistent_file = PersistentFile(self.persistent_root, persistent_name)
        os.rename(transient_file.path, persistent_file.path)
        return persistent_file


def filesessionmaker(sessionmaker, file_manager):
    u'''Wrapper of session maker adding link to a FileManager instance
    to session.::
        
        file_manager = FileManager(cfg.TRANSIENT_ROOT,
                                              cfg.PERSISTENT_ROOT)
        filesessionmaker(sessionmaker(…), file_manager)
    '''
    def session_maker(*args, **kwargs):
        session = sessionmaker(*args, **kwargs)
        # XXX in case we want to use session manager somehow bound 
        #     to request environment. For example, to generate user-specific
        #     URLs.
        #session.file_manager = \
        #        kwargs.get('file_manager', file_manager)
        session.file_manager = file_manager
        return session
    return session_maker



