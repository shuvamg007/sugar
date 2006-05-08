#!/usr/bin/env python

import dbus
import dbus.service
import dbus.glib

import pygtk
pygtk.require('2.0')
import gtk

import geckoembed

import sys

try:
	import activity
	from sugar_globals import *
except ImportError:
	from sugar import activity
	from sugar.sugar_globals import *

class AddressToolbar(gtk.Toolbar):
	def __init__(self):
		gtk.Toolbar.__init__(self)

		address_item = AddressItem(self.__open_address_cb)		
		self.insert(address_item, 0)
		address_item.show()

	def __open_address_cb(self, address):
		BrowserShell.get_instance().open_browser(address)

class AddressItem(gtk.ToolItem):
	def __init__(self, callback):
		gtk.ToolItem.__init__(self)
	
		address_entry = AddressEntry(callback)
		self.add(address_entry)
		address_entry.show()

class AddressEntry(gtk.HBox):
	def __init__(self, callback):
		gtk.HBox.__init__(self)

		self.callback = callback
		self.folded = True
		
		label = gtk.Label("Open")
		self.pack_start(label, False)
		label.show()
		
		self.button = gtk.Button()
		self.button.set_relief(gtk.RELIEF_NONE)
		self.button.connect("clicked", self.__button_clicked_cb)
		self.pack_start(self.button, False)
		self.button.show()
		
		self.entry = gtk.Entry()
		self.entry.connect("activate", self.__activate_cb)
		self.pack_start(self.entry, False)
		self.entry.show()

		self._update_folded_state()
	
	def _update_folded_state(self):
		if self.folded:
			image = gtk.Image()
			image.set_from_file(data_dir + "/unfold.png")
			self.button.set_image(image)
			image.show()

			self.entry.hide()
		else:
			image = gtk.Image()
			image.set_from_file(data_dir + "/fold.png")
			self.button.set_image(image)
			image.show()

			self.entry.show()
			self.entry.grab_focus()
	
	def get_folded(self):
		return self.folded
	
	def set_folded(self, folded):
		self.folded = not self.folded
		self._update_folded_state()		
	
	def __button_clicked_cb(self, button):
		self.set_folded(not self.get_folded())

	def __activate_cb(self, entry):
		self.callback(entry.get_text())
		self.set_folded(True)

class NavigationToolbar(gtk.Toolbar):
	def __init__(self, embed):
		gtk.Toolbar.__init__(self)
		self.embed = embed
		
		self.set_style(gtk.TOOLBAR_ICONS)
		
		self.back = gtk.ToolButton(gtk.STOCK_GO_BACK)
		self.back.connect("clicked", self.__go_back_cb)
		self.insert(self.back, -1)
		self.back.show()

		self.forward = gtk.ToolButton(gtk.STOCK_GO_FORWARD)
		self.forward.connect("clicked", self.__go_forward_cb)
		self.insert(self.forward, -1)
		self.forward.show()

		self.reload = gtk.ToolButton(gtk.STOCK_REFRESH)
		self.reload.connect("clicked", self.__reload_cb)
		self.insert(self.reload, -1)
		self.reload.show()

		separator = gtk.SeparatorToolItem()
		self.insert(separator, -1)
		separator.show()

		share = gtk.ToolButton("Share")
		share.connect("clicked", self.__share_cb)
		self.insert(share, -1)
		share.show()

		separator = gtk.SeparatorToolItem()
		self.insert(separator, -1)
		separator.show()
		
		address_item = AddressItem(self.__open_address_cb)		
		self.insert(address_item, -1)
		address_item.show()

		self._update_sensitivity()

		self.embed.connect("location", self.__location_changed)

	def _update_sensitivity(self):
		self.back.set_sensitive(self.embed.can_go_back())
		self.forward.set_sensitive(self.embed.can_go_forward())
		
	def __go_back_cb(self, button):
		self.embed.go_back()
	
	def __go_forward_cb(self, button):
		self.embed.go_forward()
		
	def __reload_cb(self, button):
		self.embed.reload()

	def __share_cb(self, button):
		pass

	def __location_changed(self, embed):
		self._update_sensitivity()

	def __open_address_cb(self, address):
		self.embed.load_address(address)

class BrowserActivity(activity.Activity):
	def __init__(self, uri):
		activity.Activity.__init__(self)
		self.uri = uri
	
	def activity_on_connected_to_shell(self):
		self.activity_set_ellipsize_tab(True)
		self.activity_set_can_close(True)
		self.activity_set_tab_text("Web Page")
		self.activity_set_tab_icon_name("web-browser")
		self.activity_show_icon(True)

		vbox = gtk.VBox()

		self.embed = geckoembed.Embed()
		self.embed.connect("title", self.__title_cb)
		vbox.pack_start(self.embed)
		
		self.embed.show()
		self.embed.load_address(self.uri)
		
		nav_toolbar = NavigationToolbar(self.embed)
		vbox.pack_start(nav_toolbar, False)
		nav_toolbar.show()

		plug = self.activity_get_gtk_plug()		
		plug.add(vbox)
		plug.show()

		vbox.show()
	
	def get_embed(self):
		return self.embed
	
	def __title_cb(self, embed):
		self.activity_set_tab_text(embed.get_title())

	def activity_on_close_from_user(self):
		self.activity_shutdown()

class WebActivity(activity.Activity):
	def __init__(self):
		activity.Activity.__init__(self)
	
	def activity_on_connected_to_shell(self):
		self.activity_set_tab_text("Web Browser")
		self.activity_set_tab_icon_name("web-browser")
		self.activity_show_icon(True)

		vbox = gtk.VBox()
			
		self.embed = geckoembed.Embed()
		self.embed.connect("open-address", self.__open_address);		
		vbox.pack_start(self.embed)
		self.embed.show()

		address_toolbar = AddressToolbar()
		vbox.pack_start(address_toolbar, False)
		address_toolbar.show()
		
		plug = self.activity_get_gtk_plug()		
		plug.add(vbox)
		plug.show()

		vbox.show()
		
		self.embed.load_address("http://www.google.com")
		
	def __open_address(self, embed, uri, data=None):
		if uri.startswith("http://www.google.com"):
			return False
		else:
			BrowserShell.get_instance().open_browser(uri)
			return True

	def activity_on_disconnected_from_shell(self):
		gtk.main_quit()
		gc.collect()

class BrowserShell(dbus.service.Object):
	instance = None

	def get_instance():
		if not BrowserShell.instance:
			BrowserShell.instance = BrowserShell()
		return BrowserShell.instance
		
	get_instance = staticmethod(get_instance)

	def __init__(self):
		session_bus = dbus.SessionBus()
		bus_name = dbus.service.BusName('com.redhat.Sugar.Browser', bus=session_bus)
		object_path = '/com/redhat/Sugar/Browser'

		dbus.service.Object.__init__(self, bus_name, object_path)

		self.__browsers = []

	def open_web_activity(self):
		web_activity = WebActivity()
		web_activity.activity_connect_to_shell()

	@dbus.service.method('com.redhat.Sugar.BrowserShell')
	def get_links(self):
		links = []
		for browser in self.__browsers:
			embed = browser.get_embed()
			link = {}
			link['title'] = embed.get_title()
			link['address'] = embed.get_address()
			links.append(link)
		return links

	@dbus.service.method('com.redhat.Sugar.BrowserShell')
	def open_browser(self, uri):
		browser = BrowserActivity(uri)
		self.__browsers.append(browser)
		browser.activity_connect_to_shell()

def main():
	BrowserShell.get_instance().open_web_activity()
	
	try:
		gtk.main()
	except KeyboardInterrupt:
		pass

if __name__=="__main__":
		main()
