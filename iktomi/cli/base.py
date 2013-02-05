# -*- coding: utf-8 -*-

import sys
import datetime


__all__ = ['manage']


class CommandNotFound(AttributeError): pass
class ConverterError(Exception): pass


def manage(commands, argv=None, delim=':'):
    '''
    Parses argv and runs neccessary command. Is to be used in manage.py file.

    Accept a dict with digest name as keys and instances of
    :class:`Cli<iktomi.management.commands.Cli>`
    objects as values.

    The format of command is the following::

        ./manage.py digest_name:command_name[ arg1[ arg2[...]]][ --key1=kwarg1[...]]

    where command_name is a part of digest instance method name, args and kwargs
    are passed to the method. For details, see
    :class:`Cli<iktomi.management.commands.Cli>` docs.
    '''
    argv = sys.argv if argv is None else argv
    if len(argv) > 1:
        cmd_name = argv[1]
        raw_args = argv[2:]
        args, kwargs = [], {}
        # parsing params
        for item in raw_args:
            if item.startswith('--'):
                splited = item[2:].split('=', 1)
                if len(splited) == 2:
                    k,v = splited
                elif len(splited) == 1:
                    k,v = splited[0], True
                else:
                    sys.exit('Error while parsing argument "%s"' % item)
                kwargs[k] = v
            else:
                args.append(item)

        # trying to get command instance
        if delim in cmd_name:
            digest_name, command = cmd_name.split(delim)
        else:
            digest_name = cmd_name
            command = None
        try:
            digest = commands[digest_name]
        except KeyError:
            sys.stdout.write('Commands:\n')
            for k in commands.keys():
                sys.stdout.write(str(k))
                sys.stdout.write('\n')
            sys.exit('Command "%s" not found' % digest_name)
        try:
            if command is None:
                if isinstance(digest, Cli):
                    sys.stdout.write(digest.description())
                    sys.exit('ERROR: "%s" is command digest' % digest_name)
                    return
                digest(*args, **kwargs)
            else:
                digest(command, *args, **kwargs)
        except CommandNotFound:
            sys.stdout.write(commands[digest_name].description())
            sys.exit('Command "%s:%s" not found' % (digest_name, command))
    else:
        sys.exit('Please provide any command')


class Cli(object):
    ''

    def description(self):
        '''Description outputed to console'''
        _help = self.__class__.__doc__ if self.__class__.__doc__ else ''
        for k in dir(self):
            if k.startswith('command_'):
                _help += '\n'
                cmd_doc = getattr(self, k).__doc__
                if cmd_doc:
                    _help += cmd_doc
        return _help

    def __call__(self, command_name, *args, **kwargs):
        if command_name == 'help':
            sys.stdout.write(self.__doc__)
            for k in self.__dict__.keys():
                if k.startswith('command_'):
                    sys.stdout.write(k.__doc__)
        elif hasattr(self, 'command_'+command_name):
            try:
                getattr(self, 'command_'+command_name)(*args, **kwargs)
            except ConverterError, e:
                sys.stderr.write('One of the arguments for '
                                 'command "%s" is wrong:\n' % command_name)
                sys.stderr.write(str(e))
        else:
            if self.__class__.__doc__:
                sys.stdout.write(self.__class__.__doc__)
            raise CommandNotFound()


class argument(object):
    'Decorator. Helps to define desired argument types'

    def __init__(self, arg_id, *validators, **kwargs):
        assert type(arg_id) in (int, str), \
            'First argument of argument (%r) decorator must be "str" or "int" type' % arg_id
        self.arg_id = arg_id
        self.validators = validators
        self.required = kwargs.get('required', True)

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            args = list(args)
            if isinstance(self.arg_id, int):
                try:
                    arg = args[self.arg_id]
                except IndexError:
                    raise ConverterError('Total positional args = %d, '
                        'but you apply converter for %d argument '
                        '(indexing starts from 0)' % (len(args), self.arg_id))
                arg = self.convert(arg)
                args[self.arg_id] = arg
            elif isinstance(self.arg_id, str):
                arg = kwargs.get(self.arg_id)
                if arg:
                    arg = self.convert(arg)
                    kwargs[self.arg_id] = arg
                if not arg and self.required:
                    raise ConverterError('Keyword argument "%s" is required' % self.arg_id)
            return func(*args, **kwargs)
        return wrapper

    def convert(self, arg):
        for v in self.validators:
            arg = v(arg)
        return arg

    @staticmethod
    def to_int(value):
        try:
            return int(value)
        except Exception:
            raise ConverterError('Cannot convert %r to int' % value)

    @staticmethod
    def to_date(value):
        try:
            return datetime.datetime.strptime(value, '%d/%m/%Y').date()
        except Exception:
            raise ConverterError('Cannot convert %r to date, please provide '
                                 'string in format "dd/mm/yyyy"' % value)