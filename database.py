# Discord voice channel observer bot
# Copyright (C) 2022 Karol "digitcrusher" Łacina
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import datetime, json, logging, os, threading
import console
from common import config, parse_duration

data = {
  'events': [],
  'active_users': {},
  'available_channels': {},
  'messages_to_events': {},
  'user_states': {},
  'cache_eventc': 0,
}
should_save = False
lock = threading.RLock()

def load():
  logging.info('Loading database')
  with lock:
    try:
      def object_hook(object):
        if '__set__' in object:
          result = set()
          for item in object:
            if item != '__set__':
              try:
                result.add(int(item))
              except ValueError:
                result.add(item)
          return result
        else:
          result = {}
          for key, value in object.items():
            try:
              result[int(key)] = value
            except ValueError:
              result[key] = value
          return result
      loaded = json.load(open(config['database'], 'r'), object_hook=object_hook)

      data.update(loaded)
      global should_save
      should_save = False
    except FileNotFoundError:
      pass

def save():
  logging.info('Saving database')
  with lock:
    if os.path.exists(config['database']):
      os.replace(config['database'], config['database'] + '.old')

    class Encoder(json.JSONEncoder):
      def default(self, value):
        if isinstance(value, set):
          result = {'__set__': True}
          for item in value:
            result[item] = None
          return result
        return json.JSONEncoder.default(self, value)
    json.dump(data, open(config['database'], 'x'), cls=Encoder)

    global should_save
    should_save = False

autosave_thread = None
autosave_stop = None

def start():
  global autosave_thread, autosave_stop
  if autosave_thread or autosave_stop:
    raise Exception('The database is already started')
  logging.info('Starting database')

  load()

  autosave_stop = threading.Event()
  def autosave():
    autosave_stop.clear()
    while not autosave_stop.is_set():
      autosave_stop.wait(timeout=parse_duration(config['autosave']))
      if should_save:
        save()
  autosave_thread = threading.Thread(target=autosave)
  autosave_thread.start()

def stop():
  global autosave_thread, autosave_stop
  if not autosave_thread or not autosave_stop:
    raise Exception('The database is already stopped')
  logging.info('Stopping database')

  autosave_stop.set()
  autosave_thread.join()
  autosave_stop = None
  autosave_thread = None

def clean():
  with lock:
    events = data['events']
    data['events'] = []
    for event in events:
      if event:
        data['events'].append(event)

    data['active_users'] = {}
    data['available_channels'] = {}
    data['messages_to_events'] = {}
    data['user_states'] = {}
    data['cache_eventc'] = 0
    update_cache()

    global should_save
    should_save = True

def add_event(event):
  old = event
  event = {'time': datetime.datetime.now().astimezone().isoformat()}
  event.update(old)

  with lock:
    if event['type'] == 'user_state' and event['value'] == data['user_states'].get(event['user'], None):
      return
    data['events'].append(event)
    global should_save
    should_save = True
    update_cache()

  log_event(event)

def update_cache():
  with lock:
    # This assumes that events in the database are in chronological order.
    i = data['cache_eventc']
    while i < len(data['events']):
      event = data['events'][i]
      if not event:
        continue

      if event['type'] in ['join', 'leave']:
        guild, channel, user = event['guild'], event['channel'], event['user']
        if event['type'] == 'join':
          data['active_users'].setdefault(guild, {}).setdefault(channel, set()).add(user)
        else:
          data['active_users'][guild][channel].remove(user)

      elif event['type'] in ['create', 'delete']:
        guild, channel = event['guild'], event['channel']
        if event['type'] == 'create':
          data['available_channels'].setdefault(guild, set()).add(channel)
        else:
          data['available_channels'][guild].remove(channel)

      elif event['type'] == 'comment':
        data['messages_to_events'][event['message']] = i

      elif event['type'] == 'user_state':
        data['user_states'][event['user']] = event['value']

      data['cache_eventc'] += 1
      i += 1

    global should_save
    should_save = True

def log_event(event):
  if event['type'] == 'join':
    logging.info(f'User {event["user"]} joined voice channel {event["channel"]} in guild {event["guild"]}')
  elif event['type'] == 'leave':
    logging.info(f'User {event["user"]} left voice channel {event["channel"]} in guild {event["guild"]}')
  elif event['type'] == 'create':
    logging.info(f'Channel {event["channel"]} was created in guild {event["guild"]}')
  elif event['type'] == 'delete':
    logging.info(f'Channel {event["channel"]} was deleted in guild {event["guild"]}')
  elif event['type'] == 'comment':
    logging.info(f'User {event["author"]} added a comment {event["message"]} for voice channel {event["channel"]} in guild {event["guild"]}')
  elif event['type'] == 'user_state':
    logging.info(f'User {event["user"]} in voice channel {event["channel"]} in guild {event["guild"]} changed their state to {event["value"]}')
  else:
    raise Exception(f'Unknown event type: {repr(event["type"])}')

def delete_comment(message):
  with lock:
    if message not in data['messages_to_events']:
      return
    event = data['events'][data['messages_to_events'][message]]
    data['events'][data['messages_to_events'][message]] = None
    del data['messages_to_events'][message]
    global should_save
    should_save = True

    logging.info(f'Comment {event["message"]} by user {event["author"]} for channel {event["channel"]} in guild {event["guild"]} was deleted')

def edit_comment(message, content):
  with lock:
    if message not in data['messages_to_events']:
      return
    event = data['events'][data['messages_to_events'][message]]
    data['events'][data['messages_to_events'][message]]['content'] = content
    global should_save
    should_save = True

    logging.info(f'User {event["author"]} edited comment {event["message"]} for channel {event["channel"]} in guild {event["guild"]}')

console.begin('database')
console.register('data',  None, 'prints the database',              lambda: data)
console.register('load',  None, 'loads the database from file',     load)
console.register('save',  None, 'saves the database to file',       save)
console.register('start', None, 'starts the database',              start)
console.register('stop',  None, 'stops the database',               stop)
console.register('clean', None, 'cleans and recaches the database', clean)
console.end()
