#!/usr/bin/env python3
#
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

import asyncio, datetime, discord, json, logging, nest_asyncio, os, sys, threading
from copy import deepcopy
nest_asyncio.apply()

# TODO: add comments
# TODO: add gatherings
# TODO: add a command prompt
# TODO: add generating activity reports
# TODO: add documentation

options = {
  'config': 'config.json'
}

config = {
  'token': None,
  'database': 'database.json',
  'autosave': '1m',
}

def load_config():
  logging.info('Loading config')
  try:
    config.update(json.load(open(options['config'], 'r')))
  except FileNotFoundError:
    raise Exception(f'Config not found: `{options["config"]}`')



database = {
  'events': [],
  'active_users': {},
  'available_channels': {},
}
should_save_database = False
database_lock = threading.RLock()

def load_database():
  logging.info('Loading database')
  with database_lock:
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

      database.update(loaded)
      global should_save_database
      should_save_database = False
    except FileNotFoundError:
      pass

def save_database():
  logging.info('Saving database')
  with database_lock:
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
    json.dump(database, open(config['database'], 'x'), cls=Encoder)

    global should_save_database
    should_save_database = False

def add_event(event):
  old = event
  event = {'time': datetime.datetime.now().astimezone().isoformat()}
  event.update(old)

  with database_lock:
    database['events'].append(event)
    update_cache_with(event)
    global should_save_database
    should_save_database = True

  log_event(event)

def update_cache_with(event):
  with database_lock:
    if event['type'] in ['join', 'leave']:
      guild, channel, user = event['guild'], event['channel'], event['user']
      if event['type'] == 'join':
        database['active_users'].setdefault(guild, {}).setdefault(channel, set()).add(user)
      else:
        database['active_users'][guild][channel].remove(user)

    elif event['type'] in ['create', 'delete']:
      guild, channel = event['guild'], event['channel']
      if event['type'] == 'create':
        database['available_channels'].setdefault(guild, set()).add(channel)
      else:
        database['available_channels'][guild].remove(channel)

    global should_save_database
    should_save_database = True

def log_event(event):
  if event['type'] == 'join':
    logging.info(f'User {event["user"]} joined voice channel {event["channel"]} in guild {event["guild"]}')
  elif event['type'] == 'leave':
    logging.info(f'User {event["user"]} left voice channel {event["channel"]} in guild {event["guild"]}')
  elif event['type'] == 'create':
    logging.info(f'Channel {event["channel"]} has been created in guild {event["guild"]}')
  elif event['type'] == 'delete':
    logging.info(f'Channel {event["channel"]} has been deleted in guild {event["guild"]}')

def rebuild_cache():
  with database_lock:
    database['active_users'] = {}
    database['available_channels'] = {}

    # This assumes that events in the database are in chronological order.
    for event in database['events']:
      update_cache_with(event)

    global should_save_database
    should_save_database = True

def scan_active_users(reason):
  logging.info(f'Scanning active users with reason `{reason}`')
  with database_lock:
    active_users = deepcopy(database['active_users'])

    for guild in client.guilds:
      for channel in guild.voice_channels:
        for user in channel.members:
          if user.id in active_users.get(guild.id, {}).get(channel.id, {}):
            active_users[guild.id][channel.id].remove(user.id)
          else:
            add_event({
              'type': 'join',
              'guild': guild.id,
              'channel': channel.id,
              'user': user.id,
              'cause': 'scan.' + reason,
            })

    for guild, channels in active_users.items():
      for channel, users in channels.items():
        for user in users:
          add_event({
            'type': 'leave',
            'guild': guild,
            'channel': channel,
            'user': user,
            'cause': 'scan.' + reason,
          })

def scan_available_channels(reason):
  logging.info(f'Scanning available channels with reason `{reason}`')

  presence_channelc = 0
  with database_lock:
    available_channels = deepcopy(database['available_channels'])

    for guild in client.guilds:
      for channel in guild.voice_channels:
        if channel.id in available_channels.get(guild.id, set()):
          available_channels[guild.id].remove(channel.id)
        else:
          add_event({
            'type': 'create',
            'guild': guild.id,
            'channel': channel.id,
            'cause': 'scan.' + reason,
          })
        presence_channelc += 1

    for guild, channels in available_channels.items():
      for channel in channels:
        add_event({
          'type': 'delete',
          'guild': guild,
          'channel': channel,
          'cause': 'scan.' + reason,
        })

  activity = discord.Activity(name=f'{presence_channelc} channels', type=discord.ActivityType.watching)
  asyncio.run(client.change_presence(activity=activity))



intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# The code below assumes that the bot can see all channels regardless of permissions.

@client.event
async def on_ready():
  logging.info(f'Logged in as `{client.user}`')
  # This lock and the one in on_guild_join partially prevent situations where
  # a user leaves immediately after the channel scan and their previous presence
  # in the channel isn't registered.
  with database_lock:
    # The following order may cause a leave event following a delete event.
    scan_available_channels('bot_ready')
    scan_active_users('bot_ready')

@client.event
async def on_message(message):
  logging.info(f'Messsage from `{message.author}`: `{message.content}`')

@client.event
async def on_voice_state_update(member, before, after):
  event = {
    'type': None,
    'guild': member.guild.id,
    'channel': None,
    'user': member.id,
    'cause': 'event.user',
  }

  if not after.channel:
    event['type'] = 'leave'
    event['channel'] = before.channel.id

  elif before.channel != after.channel:
    if before.channel:
      event['type'] = 'leave'
      event['channel'] = before.channel.id
      if after.afk:
        event['cause'] = 'event.afk'
      add_event(event)

    event['type'] = 'join'
    event['channel'] = after.channel.id

  add_event(event)

@client.event
async def on_guild_channel_create(channel):
  if isinstance(channel, discord.VoiceChannel):
    add_event({
      'type': 'create',
      'guild': channel.guild.id,
      'channel': channel.id,
      'cause': 'event',
    })

@client.event
async def on_guild_channel_delete(channel):
  if isinstance(channel, discord.VoiceChannel):
    # Ideally, we'd like to know when leave events are caused by channel
    # deletion. Discord unfortunately doesn't provide us with such information,
    # so we would have to set recent leave events' causes to event.delete here.
    add_event({
      'type': 'delete',
      'guild': channel.guild.id,
      'channel': channel.id,
      'cause': 'event',
    })

@client.event
async def on_guild_join(guild):
  with database_lock:
    scan_available_channels('guild')
    scan_active_users('guild')

@client.event
async def on_guild_remove(guild):
  scan_active_users('guild')
  scan_available_channels('guild')



def parse_duration(string):
  units = {
    's': 1,
    'm': 60,
    'h': 60 * 60,
    'd': 60 * 60 * 24,
    'y': 60 * 60 * 24 * 365,
  }
  result = 0
  value = ''
  for c in string + ' ':
    if c.isdigit() or c == '.':
      value += c
    elif c in units and value:
      result += units[c] * (float(value) if '.' in value else int(value))
      value = ''
    elif c.isspace():
      if value:
        result += units['s'] * (float(value) if '.' in value else int(value))
        value = ''
    else:
      raise Exception(f'Invalid duration: `{string}`')
  return result

if __name__ == '__main__':
  i = 0
  args = sys.argv[1:]
  while i < len(args):
    if args[i] in ['-c', '--config']:
      try:
        i += 1
        options['config'] = args[i]
      except IndexError:
        raise Exception(f'Expected a path to config after `{args[i - 1]}`')
    else:
      raise Exception(f'Unknown option: `{args[i]}`')
    i += 1

  discord.utils.setup_logging()

  load_config()
  load_database()

  autosave_stop = threading.Event()
  def autosave():
    while not autosave_stop.is_set():
      autosave_stop.wait(timeout=parse_duration(config['autosave']))
      if should_save_database:
        save_database()
  autosave_thread = threading.Thread(target=autosave)
  autosave_thread.start()

  client.run(config['token'])

  autosave_stop.set()
