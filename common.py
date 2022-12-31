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

import json, logging

options = {
  'config': 'config.json'
}

config = {
  'token': None,                                         # Your Discord bot's token
  'database': 'database.json',                           # The path to the database file
  'autosave': '1m',                                      # The regular time interval at which the database will be automatically saved if needed
  'console_host': 'localhost',                           # These two are very much self-explanatory
  'console_port': 4123,
  'console_hello': 'Discord voice channel observer bot', # The name that will be displayed in "… says hello!" after connecting to the console
  'console_timeout': '1m',                               # The time after the last received command after which the connection to the console will be automatically closed
  'meeting_interval': '5m',                              # The minimum time interval after the last user has left a channel required for a user joining to be considered the start of a new meeting
  'meeting_userc': 2,                                    # The minimum number of participants required for a meeting to be included in a report
  'comment_cooldown': '1m',                              # The time a user has to wait to be able to submit a comment again
}

def load_config():
  logging.info('Loading config')
  try:
    with open(options['config'], 'r') as file:
      config.update(json.load(file))
  except FileNotFoundError:
    raise Exception(f'Config not found: {repr(options["config"])}')

def save_config():
  logging.info('Saving config')
  with open(options['config'], 'w') as file:
    json.dump(config, file, indent=2)

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
      raise Exception(f'Invalid duration: {repr(string)}')
  return result
