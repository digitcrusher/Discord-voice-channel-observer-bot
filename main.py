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

import discord, nest_asyncio, sys
nest_asyncio.apply()

import bot, common, database
from common import options

# TODO: add gatherings
# TODO: add a command prompt
# TODO: add generating activity reports
# TODO: add documentation

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
  common.load_config()
  database.start()
  bot.run()
  database.stop()
