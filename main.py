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

import discord, json, logging, os, sys, threading, time

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
  'test': 0
}
database_lock = threading.Lock()

def load_database():
  with database_lock:
    logging.info('Loading database')
    try:
      database.update(json.load(open(config['database'], 'r')))
    except FileNotFoundError:
      pass

def save_database():
  with database_lock:
    logging.info('Saving database')
    if os.path.exists(config['database']):
      os.replace(config['database'], config['database'] + '.old')
    json.dump(database, open(config['database'], 'x'))

class Client(discord.Client):
  async def on_ready(self):
    logging.info(f'Logged in as `{self.user}`')

  async def on_message(self, message):
    logging.info(f'Messsage from `{message.author}`: `{message.content}`')
    with database_lock:
      database['test'] += 1

def parse_duration(string):
  result = 0
  units = {
    's': 1,
    'm': 60,
    'h': 60 * 60,
    'd': 60 * 60 * 24,
    'y': 60 * 60 * 24 * 365,
  }
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
      save_database()
  autosave_thread = threading.Thread(target=autosave)
  autosave_thread.start()

  intents = discord.Intents.default()
  intents.message_content = True

  client = Client(intents=intents)
  client.run(config['token'])

  autosave_stop.set()
