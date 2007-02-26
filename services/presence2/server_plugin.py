# Copyright (C) 2007, Red Hat, Inc.
# Copyright (C) 2007, Collabora Ltd.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import gobject
from sugar import profile
from sugar import util
from buddyiconcache import BuddyIconCache
import logging

from telepathy.client import ConnectionManager, ManagerRegistry, Connection, Channel
from telepathy.interfaces import (
    CONN_MGR_INTERFACE, CONN_INTERFACE, CHANNEL_TYPE_CONTACT_LIST, CHANNEL_INTERFACE_GROUP, CONN_INTERFACE_ALIASING,
    CONN_INTERFACE_AVATARS, CONN_INTERFACE_PRESENCE)
from telepathy.constants import (
    CONNECTION_HANDLE_TYPE_NONE, CONNECTION_HANDLE_TYPE_CONTACT,
    CONNECTION_STATUS_CONNECTED, CONNECTION_STATUS_DISCONNECTED, CONNECTION_STATUS_CONNECTING,
    CONNECTION_HANDLE_TYPE_LIST, CONNECTION_HANDLE_TYPE_CONTACT,
    CONNECTION_STATUS_REASON_AUTHENTICATION_FAILED)


class ServerPlugin(gobject.GObject):
    __gsignals__ = {
        'contact-online':  (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                             ([gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT])),
        'contact-offline': (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                             ([gobject.TYPE_PYOBJECT])),
        'status':          (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                             ([gobject.TYPE_INT, gobject.TYPE_INT])),
        'avatar-updated':  (gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                             ([gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT]))
    }
    
    def __init__(self, registry):
        gobject.GObject.__init__(self)

        self._icon_cache = BuddyIconCache()

        self._registry = registry
        self._online_contacts = set() # handles of online contacts
        self._account = self._get_account_info()

        self._ever_connected = False
        self._conn = self._init_connection()

    def _get_account_info(self):
        account_info = {'server': 'olpc.collabora.co.uk'}

        pubkey = profile.get_pubkey()
        khash = util.printable_hash(util._sha_data(pubkey))
        account_info['account'] = "%s@%s" % (khash, account_info['server'])

        account_info['password'] = profile.get_private_key_hash()
        return account_info

    def _init_connection(self, register=False):
        protocol = 'jabber'

        mgr = self._registry.GetManager('gabble')

        # Search existing connections, if any, that we might be able to use
        connections = Connection.get_connections()
        conn = None
        for item in connections:
            if not item.object_path.startswith("/org/freedesktop/Telepathy/Connection/gabble/jabber/"):
                continue
            if item[CONN_INTERFACE].GetStatus() == CONNECTION_STATUS_DISCONNECTED:
                item[CONN_INTERFACE].Disconnect()
                continue
            if item[CONN_INTERFACE].GetProtocol() != protocol:
                continue
            if item[CONN_INTERFACE].GetStatus() == CONNECTION_STATUS_CONNECTED:
                self_name = self._account['account']
                test_handle = item[CONN_INTERFACE].RequestHandles(CONNECTION_HANDLE_TYPE_CONTACT, [self_name])[0]
                if item[CONN_INTERFACE].GetSelfHandle() != test_handle:
                    continue
            conn = item
            break

        if not conn:
            acct = self._account.copy()
            if register:
                acct['register'] = True

            # Create a new connection
            print acct
            name, path = mgr[CONN_MGR_INTERFACE].RequestConnection(protocol, acct)
            conn = Connection(name, path)

        conn[CONN_INTERFACE].connect_to_signal('StatusChanged', self._status_changed_cb)

        # hack
        conn._valid_interfaces.add(CONN_INTERFACE_PRESENCE)
        conn[CONN_INTERFACE_PRESENCE].connect_to_signal('PresenceUpdate',
            self._presence_update_cb)        

        return conn

    def _request_list_channel(self, name):
        handle = self._conn[CONN_INTERFACE].RequestHandles(
            CONNECTION_HANDLE_TYPE_LIST, [name])[0]
        chan_path = self._conn[CONN_INTERFACE].RequestChannel(
            CHANNEL_TYPE_CONTACT_LIST, CONNECTION_HANDLE_TYPE_LIST,
            handle, True)
        channel = Channel(self._conn._dbus_object._named_service, chan_path)
        # hack
        channel._valid_interfaces.add(CHANNEL_INTERFACE_GROUP)
        return channel

    def _connected_cb(self):
        self._ever_connected = True

        # the group of contacts who may receive your presence
        publish = self._request_list_channel('publish')
        publish_handles, local_pending, remote_pending = publish[CHANNEL_INTERFACE_GROUP].GetAllMembers()

        # the group of contacts for whom you wish to receive presence
        subscribe = self._request_list_channel('subscribe')
        subscribe_handles = subscribe[CHANNEL_INTERFACE_GROUP].GetMembers()

        if local_pending:
            # accept pending subscriptions
            #print 'pending: %r' % local_pending
            publish[CHANNEL_INTERFACE_GROUP].AddMembers(local_pending, '')

        not_subscribed = list(set(publish_handles) - set(subscribe_handles))
        self_handle = self._conn[CONN_INTERFACE].GetSelfHandle()
        self._online_contacts.add(self_handle)

        for handle in not_subscribed:
            # request subscriptions from people subscribed to us if we're not subscribed to them
            subscribe[CHANNEL_INTERFACE_GROUP].AddMembers([self_handle], '')

        # hack
        self._conn._valid_interfaces.add(CONN_INTERFACE_ALIASING)

        if CONN_INTERFACE_ALIASING in self._conn:
            aliases = self._conn[CONN_INTERFACE_ALIASING].RequestAliases(subscribe_handles)
        else:
            aliases = self._conn[CONN_INTERFACE].InspectHandles(CONNECTION_HANDLE_TYPE_CONTACT, subscribe_handles)

        #for handle, alias in zip(subscribe_handles, aliases):
        #    print alias
        #    self.buddies[handle].alias = alias

        # hack
        self._conn._valid_interfaces.add(CONN_INTERFACE_AVATARS)

        self._conn[CONN_INTERFACE_AVATARS].connect_to_signal('AvatarUpdated', self._avatar_updated_cb)
        #if CONN_INTERFACE_AVATARS in self._conn:
        #    tokens = self._conn[CONN_INTERFACE_AVATARS].RequestAvatarTokens(subscribe_handles)

        #    #for handle, token in zip(subscribe_handles, tokens):
        #    for handle in subscribe_handles:
        #        avatar, mime_type = self._conn[CONN_INTERFACE_AVATARS].RequestAvatar(handle)
        #        self.buddies[handle].avatar = ''.join(map(chr, avatar))

        #        import gtk
        #        window = gtk.Window()
        #        window.set_title(self.buddies[handle].alias)
        #        loader = gtk.gdk.PixbufLoader()
        #        loader.write(self.buddies[handle].avatar)
        #        loader.close()
        #        image = gtk.Image()
        #        image.set_from_pixbuf(loader.get_pixbuf())
        #        window.add(image)
        #        window.show_all()

    def _status_changed_cb(self, state, reason):
        gobject.idle_add(self._status_changed_cb2, state, reason)

    def _status_changed_cb2(self, state, reason):
        if state == CONNECTION_STATUS_CONNECTING:
            print 'connecting: %r' % reason
        elif state == CONNECTION_STATUS_CONNECTED:
            print 'connected: %r' % reason
            self.emit('status', state, int(reason))
            self._connected_cb()
        elif state == CONNECTION_STATUS_DISCONNECTED:
            print 'disconnected: %r' % reason
            self.emit('status', state, int(reason))
            if reason == CONNECTION_STATUS_REASON_AUTHENTICATION_FAILED and \
                    not self._ever_connected:
                # Hmm; probably aren't registered on the server, try reconnecting
                # and registering
                del self._conn
                self._conn = self._init_connection(register=True)
                self.start()
        return False

    def start(self):
        # If the connection is already connected query initial contacts
        conn_status = self._conn[CONN_INTERFACE].GetStatus()
        if conn_status == CONNECTION_STATUS_CONNECTED:
            self._connected_cb()
            subscribe = self._request_list_channel('subscribe')
            subscribe_handles = subscribe[CHANNEL_INTERFACE_GROUP].GetMembers()
            self._conn[CONN_INTERFACE_PRESENCE].RequestPresence(subscribe_handles)
        elif conn_status == CONNECTION_STATUS_CONNECTING:
            pass
        else:
            self._conn[CONN_INTERFACE].Connect()

    def disconnect(self):
        self._conn[CONN_INTERFACE].Disconnect()

    def _contact_go_offline(self, handle):
        jid = self._conn[CONN_INTERFACE].InspectHandles(CONNECTION_HANDLE_TYPE_CONTACT, [handle])[0]
        print jid, "offline"

        self._online_contacts.remove(handle)
        self.emit("contact-offline", handle)

    def _contact_go_online(self, handle):
        jid = self._conn[CONN_INTERFACE].InspectHandles(CONNECTION_HANDLE_TYPE_CONTACT, [handle])[0]
        print jid, "online"

        # TODO: use the OLPC interface to get the key
        key = handle

        self._online_contacts.add(handle)
        self.emit("contact-online", handle, key)

    def _presence_update_cb(self, presence):
        for handle in presence:
            timestamp, statuses = presence[handle]

            name = self._conn[CONN_INTERFACE].InspectHandles(CONNECTION_HANDLE_TYPE_CONTACT, [handle])[0]
            online = handle in self._online_contacts

            for status, params in statuses.items():
                if not online and status in ["available", "away", "brb", "busy", "dnd", "xa"]:
                    self._contact_go_online(handle)
                elif online and status in ["offline", "invisible"]:
                    self._contact_go_offline(handle)

    def _avatar_updated_cb(self, handle, new_avatar_token):
        jid = self._conn[CONN_INTERFACE].InspectHandles(CONNECTION_HANDLE_TYPE_CONTACT, [handle])[0]

        icon = self._icon_cache.get_icon(jid, new_avatar_token)

        if not icon:
            # cache miss
            avatar, mime_type = self._conn[CONN_INTERFACE_AVATARS].RequestAvatar(handle)
            icon = ''.join(map(chr, avatar))
            self._icon_cache.store_icon(jid, new_avatar_token, icon)

        self.emit("avatar-updated", handle, icon)
