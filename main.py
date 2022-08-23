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

import discord, json, logging, sys

options = {
  'config': 'config.json'
}

config = {
  'token': None
}

def load_config():
  try:
    config.update(json.load(open(options['config'], 'r')))
  except FileNotFoundError:
    raise Exception(f'Config not found: `{options["config"]}`')

class Client(discord.Client):
  async def on_ready(self):
    logging.info(f'Logged in as `{self.user}`')

  async def on_message(self, message):
    logging.info(f'Messsage from `{message.author}`: `{message.content}`')

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
    i += 1

  load_config()

  discord.utils.setup_logging()

  intents = discord.Intents.default()
  intents.message_content = True

  client = Client(intents=intents)
  client.run(config['token'])
