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
from common import config, parse_duration

data = {
  'events': [],
  'active_users': {},
  'available_channels': {},
  'messages_to_events': {},
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

autosave_stop = None
def start():
  load()

  global autosave_stop
  autosave_stop = threading.Event()
  def autosave():
    while not autosave_stop.is_set():
      autosave_stop.wait(timeout=parse_duration(config['autosave']))
      if should_save:
        save()
  autosave_thread = threading.Thread(target=autosave)
  autosave_thread.start()

def stop():
  autosave_stop.set()

def add_event(event):
  old = event
  event = {'time': datetime.datetime.now().astimezone().isoformat()}
  event.update(old)

  with lock:
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
    logging.info(f'User {event["author"]} added a comment {event["message"]} for channel {event["channel"]} in guild {event["guild"]}')
  else:
    raise Exception(f'Unknown event type: `{event["type"]}`')

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
    data['cache_eventc'] = 0
    update_cache()

    global should_save
    should_save = True

def delete_comment(message):
  with lock:
    if message in data['messages_to_events']:
      event = data['events'][data['messages_to_events'][message]]
      data['events'][data['messages_to_events'][message]] = None
      del data['messages_to_events'][message]
      global should_save
      should_save = True

      logging.info(f'Comment {event["message"]} by user {event["author"]} for channel {event["channel"]} in guild {event["guild"]} was deleted')

def edit_comment(message, content):
  with lock:
    event = data['events'][data['messages_to_events'][message]]
    data['events'][data['messages_to_events'][message]]['content'] = content
    global should_save
    should_save = True

    logging.info(f'User {event["author"]} edited comment {event["message"]} for channel {event["channel"]} in guild {event["guild"]}')
