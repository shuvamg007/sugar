import sys
import logging
import traceback
from cStringIO import StringIO

import dbus
import gobject

__sugar_shell = None
__console_id = None

class Handler(logging.Handler):
	def __init__(self, shell, console_id):
		logging.Handler.__init__(self)

		self._console_id = console_id
		self._shell = shell
		self._messages = []

	def _log(self):
		for message in self._messages:
			self._shell.log(self._console_id, message)
		self._messages = []
		return False

	def emit(self, record):
		self._messages.append(record.msg)
		if len(self._messages) == 1:
			gobject.idle_add(self._log)

def __exception_handler(typ, exc, tb):
	trace = StringIO()
	traceback.print_exception(typ, exc, tb, None, trace)

	__sugar_shell.log(__console_id, trace.getvalue())

def start(console_id, shell = None):
	root_logger = logging.getLogger('')
	root_logger.setLevel(logging.DEBUG)
	
	if shell == None:
		bus = dbus.SessionBus()
		proxy_obj = bus.get_object('com.redhat.Sugar.Shell', '/com/redhat/Sugar/Shell')
		shell = dbus.Interface(proxy_obj, 'com.redhat.Sugar.Shell')

	root_logger.addHandler(Handler(shell, console_id))

	global __sugar_shell
	global __console_id

	__sugar_shell = shell
	__console_id = console_id
	sys.excepthook = __exception_handler
