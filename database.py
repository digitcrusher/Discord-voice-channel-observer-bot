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

import json, logging, os, threading
from datetime import datetime

import console
from common import config, parse_duration

data = {
  'events': [],
  'active_users': {},
  'available_channels': {},
  'message_to_event': {},
  'user_last_comment_times': {},
  'user_states': {},
  'cache_eventc': 0,
  'guild_names': {},
  'channel_guilds': {},
  'channel_names': {},
  'user_names': {},
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
      with open(config['database'], 'r') as file:
        loaded = json.load(file, object_hook=object_hook)

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
    with open(config['database'], 'x') as file:
      json.dump(data, file, cls=Encoder)

    global should_save
    should_save = False

autosave_thread = None
autosave_stop = None

def start():
  global autosave_thread, autosave_stop
  if autosave_thread is not None or autosave_stop is not None:
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
  if autosave_thread is None or autosave_stop is None:
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
      if event is not None:
        data['events'].append(event)

    data['active_users'] = {}
    data['available_channels'] = {}
    data['message_to_event'] = {}
    data['user_last_comment_times'] = {}
    data['user_states'] = {}
    data['cache_eventc'] = 0
    update_cache()

    global should_save
    should_save = True

class Throttled(Exception):
  pass

def add_event(event):
  old = event
  event = {'time': datetime.now().astimezone().isoformat()}
  event.update(old)

  with lock:
    if event['type'] == 'user_state' and event['user'] in data['user_states'] and event['value'] == data['user_states'][event['user']]:
      return
    elif event['type'] == 'comment' and event['user'] in data['user_last_comment_times']:
      time = datetime.fromisoformat(event['time'])
      last_comment = datetime.fromisoformat(data['user_last_comment_times'][event['user']])
      cooldown = parse_duration(config['comment_cooldown'])
      if (time - last_comment).total_seconds() < cooldown:
        raise Throttled()

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
      if event is None:
        continue

      if event['type'] in {'join', 'leave'}:
        guild, channel, user = event['guild'], event['channel'], event['user']
        if event['type'] == 'join':
          data['active_users'].setdefault(guild, {}).setdefault(channel, set()).add(user)
        else:
          data['active_users'][guild][channel].remove(user)

      elif event['type'] in {'create', 'delete'}:
        guild, channel = event['guild'], event['channel']
        if event['type'] == 'create':
          data['available_channels'].setdefault(guild, set()).add(channel)
        else:
          data['available_channels'][guild].remove(channel)

      elif event['type'] == 'comment':
        data['message_to_event'][event['message']] = i
        data['user_last_comment_times'][event['user']] = event['time']

      elif event['type'] == 'user_state':
        data['user_states'][event['user']] = event['value']

      data['cache_eventc'] += 1
      i += 1

    global should_save
    should_save = True

def log_event(event):
  guild = event.get('guild', None)
  if guild in data['guild_names']:
    guild = repr(data['guild_names'][guild])

  channel = event.get('channel', None)
  if channel in data['channel_names']:
    channel = repr(data['channel_names'][channel])

  user = event.get('user', None)
  if user in data['user_names']:
    user = repr(data['user_names'][user])

  if event['type'] == 'join':
    logging.info(f'User {user} joined channel {channel} in guild {guild}')
  elif event['type'] == 'leave':
    logging.info(f'User {user} left channel {channel} in guild {guild}')
  elif event['type'] == 'create':
    logging.info(f'Channel {channel} was created in guild {guild}')
  elif event['type'] == 'delete':
    logging.info(f'Channel {channel} was deleted in guild {guild}')
  elif event['type'] == 'comment':
    logging.info(f'User {user} added a comment {event["message"]} for channel {channel} in guild {guild}')
  elif event['type'] == 'user_state':
    logging.info(f'User {user} in channel {channel} in guild {guild} changed their state to {event["value"]}')
  elif event['type'] == '_delete_comment':
    logging.info(f'Comment {event["message"]} by user {user} for channel {channel} in guild {guild} was deleted')
  elif event['type'] == '_edit_comment':
    logging.info(f'User {user} edited comment {event["message"]} for channel {channel} in guild {guild}')
  else:
    raise Exception(f'Unknown event type: {repr(event["type"])}')

def delete_comment(message):
  with lock:
    if message not in data['message_to_event']:
      return
    event = data['events'][data['message_to_event'][message]]
    data['events'][data['message_to_event'][message]] = None
    del data['message_to_event'][message]
    global should_save
    should_save = True

    event['type'] = '_delete_comment'
    log_event(event)

def edit_comment(message, content):
  with lock:
    if message not in data['message_to_event']:
      return
    event = data['events'][data['message_to_event'][message]]
    event['content'] = content
    global should_save
    should_save = True

    event = event.copy()
    event['type'] = '_edit_comment'
    log_event(event)

console.begin('database')
console.register('data',  None, 'prints the database',              lambda: data)
console.register('load',  None, 'loads the database from file',     load)
console.register('save',  None, 'saves the database to file',       save)
console.register('start', None, 'starts the database',              start)
console.register('stop',  None, 'stops the database',               stop)
console.register('clean', None, 'cleans and recaches the database', clean)
console.end()
