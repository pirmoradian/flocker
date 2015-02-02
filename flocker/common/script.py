# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""Helpers for flocker shell commands."""

import sys
import os

from twisted.internet import task
from twisted.internet.defer import Deferred, maybeDeferred
from twisted.python import usage
from twisted.python.filepath import FilePath
from twisted.python.log import (
    addObserver, removeObserver, FileLogObserver, msg)

from zope.interface import Interface

from .. import __version__


__all__ = [
    'flocker_standard_options',
    'ICommandLineScript',
    'FlockerScriptRunner',
    'main_for_service',
]


def flocker_standard_options(cls):
    """Add various standard command line options to flocker commands.

    :param type cls: The `class` to decorate.
    :return: The decorated `class`.
    """
    original_init = cls.__init__

    def __init__(self, *args, **kwargs):
        """Set the default verbosity to `0`

        Calls the original ``cls.__init__`` method finally.

        :param sys_module: An optional ``sys`` like module for use in
            testing. Defaults to ``sys``.
        """
        self._sys_module = kwargs.pop('sys_module', sys)
        self['verbosity'] = 0
        original_init(self, *args, **kwargs)
    cls.__init__ = __init__

    def opt_version(self):
        """Print the program's version and exit."""
        self._sys_module.stdout.write(__version__.encode('utf-8') + b'\n')
        raise SystemExit(0)
    cls.opt_version = opt_version

    def opt_verbose(self):
        """Turn on verbose logging."""
        self['verbosity'] += 1
    cls.opt_verbose = opt_verbose
    cls.opt_v = opt_verbose

    return cls


class ICommandLineScript(Interface):
    """A script which can be run by ``FlockerScriptRunner``."""
    def main(reactor, options):
        """
        :param reactor: A Twisted reactor.
        :param dict options: A dictionary of configuration options.
        :return: A ``Deferred`` which fires when the script has completed.
        """


class FlockerScriptRunner(object):
    """An API for running standard flocker scripts.

    :ivar ICommandLineScript script: See ``script`` of ``__init__``.
    :ivar _react: A reference to ``task.react`` which can be overridden for
        testing purposes.
    """
    _react = staticmethod(task.react)

    # Location where logs will be written, overrideable by tests:
    log_directory = FilePath(b"/var/log/flocker/")

    def __init__(self, script, options, reactor=None, sys_module=None):
        """
        :param ICommandLineScript script: The script object to be run.
        :param usage.Options options: An option parser object.
        :param sys_module: An optional ``sys`` like module for use in
            testing. Defaults to ``sys``.
        """
        self.script = script
        self.options = options
        self._reactor = reactor

        if sys_module is None:
            sys_module = sys
        self.sys_module = sys_module

    def _parse_options(self, arguments):
        """Parse the options defined in the script's options class.

        ``UsageError``s are caught and printed to `stderr` and the script then
        exits.

        :param list arguments: The command line arguments to be parsed.
        :return: A ``dict`` of configuration options.
        """
        try:
            self.options.parseOptions(arguments)
        except usage.UsageError as e:
            self.sys_module.stderr.write(unicode(self.options).encode('utf-8'))
            self.sys_module.stderr.write(
                b'ERROR: ' + e.message.encode('utf-8') + b'\n')
            raise SystemExit(1)
        return self.options

    def main(self):
        """Parse arguments and run the script's main function via ``react``."""
        observer = None
        try:
            if not self.log_directory.exists():
                self.log_directory.makedirs()
            log_path = self.log_directory.child(
                b"%s-%d.log" % (os.path.basename(self.sys_module.argv[0]),
                                os.getpid()))
            log_file = log_path.open("a")
            observer = FileLogObserver(log_file).emit
            addObserver(observer)
            msg("Arguments: %s" % (self.sys_module.argv,))
        except (OSError, IOError):
            pass

        options = self._parse_options(self.sys_module.argv[1:])
        # XXX: We shouldn't be using this private _reactor API. See
        # https://twistedmatrix.com/trac/ticket/6200 and
        # https://twistedmatrix.com/trac/ticket/7527
        self._react(self.script.main, (options,), _reactor=self._reactor)

        # Not strictly necessary, but nice cleanup for tests:
        if observer is not None:
            removeObserver(observer)
            log_file.close()


def _chain_stop_result(service, stop):
    """
    Stop a service and chain the resulting ``Deferred`` to another
    ``Deferred``.

    :param IService service: The service to stop.
    :param Deferred stop: The ``Deferred`` which will be fired when the service
        has stopped.
    """
    maybeDeferred(service.stopService).chainDeferred(stop)


def main_for_service(reactor, service):
    """
    Start a service and integrate its shutdown with reactor shutdown.

    This is useful for hooking driving an ``IService`` provider with
    ``twisted.internet.task.react``.  For example::

        from twisted.internet.task import react
        from yourapp import YourService
        react(_main_for_service, [YourService()])

    :param IReactorCore reactor: The reactor the run lifetime of which to tie
        to the given service.  When the reactor is shutdown, the service will
        be shutdown.

    :param IService service: The service to tie to the run lifetime of the
        given reactor.  It will be started immediately and made to stop when
        the reactor stops.

    :return: A ``Deferred`` which fires after the service has finished
        stopping.
    """
    service.startService()
    stop = Deferred()
    reactor.addSystemEventTrigger(
        "before", "shutdown", _chain_stop_result, service, stop)
    return stop
