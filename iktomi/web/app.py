# -*- coding: utf-8 -*-

__all__ = ['Application', 'AppEnvironment']

import logging
import re
from iktomi.utils.storage import VersionedStorage, StorageFrame, storage_property
from webob.exc import HTTPException, HTTPInternalServerError, \
                      HTTPNotFound
from webob import Request
from .route_state import RouteState
from .reverse import Reverse

logger = logging.getLogger(__name__)

HOSTNAME_REGEX = re.compile("^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9])(?::\d+)?$")
IP_REGEX = re.compile("^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(?::\d+)?$")


class AppEnvironment(StorageFrame):
    '''
    Base class for `env` storage frame class.

    Can be subclassed to add extra functionality::

        class FrontEnvironment(AppEnvironment):
            cfg = cfg
            cache = memcache_client

            @cached_property
            def db(self):
                return db_maker()
    '''

    def __init__(self, request=None, root=None, _parent_storage=None, **kwargs):
        StorageFrame.__init__(self, _parent_storage=_parent_storage, **kwargs)
        self.request = request
        if request:
            self.root = root.bind_to_env(self._root_storage)
            self._route_state = RouteState(request)
        else:
            self.root = root

    def gettext(self, message):
        return message

    def ngettext(self, single, plural, count):
        return single if count == 1 else plural

    @storage_property
    def current_location(self):
        ns = getattr(self, 'namespace', '')
        url_name = getattr(self, 'current_url_name', '')
        return '.'.join(filter(None, (ns, url_name)))

    @classmethod
    def create(cls, *args, **kwargs):
        return VersionedStorage(cls, *args, **kwargs)


class Application(object):
    '''
    WSGI application made from `iktomi.web.WebHandler' instance::

        wsgi_app = Application(app, env_class=FrontEnvironment)
    '''

    env_class = AppEnvironment

    def __init__(self, handler, env_class=None):
        self.handler = handler
        if env_class is not None:
            self.env_class = env_class
        self.root = Reverse.from_handler(handler)

    def handle_error(self, env):
        '''
        Unhandled exception handler.
        You can put any logging, error warning, etc here.'''
        logger.exception('Exception for %s %s :',
                         env.request.method, env.request.url)

    def handle(self, env, data):
        '''
        Calls application and handles following cases:
            * catches `webob.HTTPException` errors.
            * catches unhandled exceptions, calls `handle_error` method
              and returns 500.
            * returns 404 if the app has returned None`.
        '''
        try:
            response = self.handler(env, data)
            if response is None:
                logger.debug('Application returned None '
                             'instead of Response object')
                response = HTTPNotFound()
        except HTTPException, e:
            response = e
        except Exception, e:
            self.handle_error(env)
            response = HTTPInternalServerError()
        return response

    def is_host_valid(self, host):
        return re.match(HOSTNAME_REGEX, host) or re.match(IP_REGEX, host)

    def __call__(self, environ, start_response):
        '''
        WSGI interface method. 
        Creates webob and iktomi wrappers and calls `handle` method.
        '''
        # validating Host header to prevent problems with url parsing
        if not self.is_host_valid(environ['HTTP_HOST']):
            logger.warning('Unusual header "Host: {}", return HTTPNotFound'\
                           .format(environ['HTTP_HOST']))
            return HTTPNotFound()(environ, start_response)
        request = Request(environ, charset='utf-8')
        env = VersionedStorage(self.env_class, request=request, root=self.root)
        data = VersionedStorage()
        response = self.handle(env, data)
        try:
            result = response(environ, start_response)
        except Exception:
            self.handle_error(env)
            result = HTTPInternalServerError()(environ, start_response)
        return result
