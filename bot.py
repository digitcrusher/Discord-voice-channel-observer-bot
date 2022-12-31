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

import asyncio, discord, io, logging, threading
from copy import deepcopy

import console, database, report
from common import config, parse_duration

# IDEA: Transcripts

# This code assumes that the bot can see all channels regardless of permissions.

client = None
start_event = threading.Event()
stop_event = threading.Event()

def run():
  start()
  try:
    while True:
      start_event.wait()
      stop_event.clear()

      intents = discord.Intents.default()
      intents.message_content = True

      global client
      client = Client(intents=intents)
      asyncio.run(client.start(config['token'])) # The Client object is useless after this.
      client = None

      start_event.clear()
      if not stop_event.is_set():
        break
  except KeyboardInterrupt:
    pass

def start():
  if start_event.is_set():
    raise Exception('The bot is already started')
  logging.info('Starting bot')
  start_event.set()

def stop():
  if stop_event.is_set():
    raise Exception('The bot is already stopped')
  logging.info('Stopping bot')
  stop_event.set()
  asyncio.run_coroutine_threadsafe(client.close(), client.loop)

def voice_state_to_flags(state):
  result = set()
  if state.afk:         result.add('afk')
  if state.self_mute:   result.add('mute.user')
  if state.mute:        result.add('mute.guild')
  if state.self_deaf:   result.add('deafen.user')
  if state.deaf:        result.add('deafen.guild')
  if state.self_stream: result.add('stream')
  if state.self_video:  result.add('video')
  return result

class Client(discord.Client):
  async def scan(self, reason):
    logging.info(f'Scanning active users and available channels with reason {repr(reason)}')

    self.presence_channelc = 0
    with database.lock:
      active_users = deepcopy(database.data['active_users'])
      available_channels = deepcopy(database.data['available_channels'])

      delayed = []
      for guild in self.guilds:
        database.data['guild_names'][guild.id] = guild.name

        for channel in guild.voice_channels:
          if channel.id in available_channels.get(guild.id, set()):
            available_channels[guild.id].remove(channel.id)
          else:
            delayed.append({
              'type': 'create',
              'guild': guild.id,
              'channel': channel.id,
              'cause': 'scan.' + reason,
            })
          database.data['channel_guilds'][channel.id] = channel.guild.id
          database.data['channel_names'][channel.id] = channel.name
          self.presence_channelc += 1

          for member in channel.members:
            delayed.append({
              'type': 'user_state',
              'guild': guild.id,
              'channel': channel.id,
              'user': member.id,
              'value': voice_state_to_flags(member.voice),
              'cause': 'scan.' + reason,
            })
            if member.id in active_users.get(guild.id, {}).get(channel.id, {}):
              active_users[guild.id][channel.id].remove(member.id)
            else:
              delayed.append({
                'type': 'join',
                'guild': guild.id,
                'channel': channel.id,
                'user': member.id,
                'cause': 'scan.' + reason,
              })
            database.data['user_names'][member.id] = str(member)

      for guild, channels in active_users.items():
        for channel, users in channels.items():
          for user in users:
            database.add_event({
              'type': 'leave',
              'guild': guild,
              'channel': channel,
              'user': user,
              'cause': 'scan.' + reason,
            })

      for guild, channels in available_channels.items():
        for channel in channels:
          database.add_event({
            'type': 'delete',
            'guild': guild,
            'channel': channel,
            'cause': 'scan.' + reason,
          })

      for event in delayed:
        database.add_event(event)

      database.should_save = True

    await self.update_presence()

  async def update_presence(self):
    activity = discord.Activity(name=f'{self.presence_channelc} channels', type=discord.ActivityType.watching)
    await self.change_presence(activity=activity)

  async def on_ready(self):
    logging.info(f'Logged in as {repr(str(self.user))}')
    await self.scan('bot_ready')

  async def on_voice_state_update(self, member, before, after):
    database.data['user_names'][member.id] = str(member)
    database.should_save = True

    event = {
      'type': None,
      'guild': None,
      'channel': None,
      'user': member.id,
      'cause': 'event',
    }

    if after.channel is None:
      event['type'] = 'leave'
      event['guild'] = before.channel.guild.id
      event['channel'] = before.channel.id
      database.add_event(event)
      return

    user_state_event = {
      'type': 'user_state',
      'guild': after.channel.guild.id,
      'channel': after.channel.id,
      'user': member.id,
      'value': voice_state_to_flags(after),
      'cause': 'event',
    }

    if before.channel != after.channel:
      if before.channel is not None:
        event['type'] = 'leave'
        event['guild'] = before.channel.guild.id
        event['channel'] = before.channel.id
        database.add_event(event)

      database.add_event(user_state_event)

      event['type'] = 'join'
      event['guild'] = after.channel.guild.id
      event['channel'] = after.channel.id
      database.add_event(event)
    else:
      database.add_event(user_state_event)

  async def on_guild_channel_create(self, channel):
    if isinstance(channel, discord.VoiceChannel):
      database.add_event({
        'type': 'create',
        'guild': channel.guild.id,
        'channel': channel.id,
        'cause': 'event',
      })
      database.data['channel_guilds'][channel.id] = channel.guild.id
      database.data['channel_names'][channel.id] = channel.name
      database.should_save = True

      self.presence_channelc += 1
      await self.update_presence()

  async def on_guild_channel_delete(self, channel):
    if isinstance(channel, discord.VoiceChannel):
      # Ideally, we'd like to know when leave events are caused by channel
      # deletion. Discord unfortunately doesn't provide us with such information,
      # so we would have to set recent leave events' causes to event.delete here.
      database.add_event({
        'type': 'delete',
        'guild': channel.guild.id,
        'channel': channel.id,
        'cause': 'event',
      })

      self.presence_channelc -= 1
      await self.update_presence()

  async def on_guild_channel_update(self, before, after):
    if isinstance(after, discord.VoiceChannel):
      database.data['channel_names'][after.id] = after.name
      database.should_save = True

  async def on_guild_join(self, guild):
    await self.scan('guild')

  async def on_guild_remove(self, guild):
    await self.scan('guild')

  async def on_guild_update(self, before, after):
    database.data['guild_names'][after.id] = after.name
    database.should_save = True

  async def on_message(self, message):
    if message.author == self.user:
      return

    content = message.content.strip()
    if not isinstance(message.channel, discord.DMChannel):
      if not content.startswith(f'<@{self.user.id}>'):
        return
      content = content.removeprefix(f'<@{self.user.id}>').lstrip()

    # IDEA: Recognize natural language questions
    report_channel = None
    if not content and isinstance(message.channel, discord.VoiceChannel):
      report_channel = message.channel.id
    elif content.startswith('<#') and content.endswith('>'):
      inside = content.removeprefix('<#').removesuffix('>')
      if inside == inside.strip().lstrip('+-'):
        try:
          report_channel = int(inside)
        except ValueError:
          pass

    if report_channel is not None:
      channel = self.get_channel(report_channel)
      if channel is not None and channel.permissions_for(message.author).view_channel:
        with io.StringIO(report.generate(report_channel)) as file:
          await message.reply(file=discord.File(file, 'report.html'))
      else:
        await message.add_reaction('❓')

    elif content and isinstance(message.author, discord.Member) and message.author.voice is not None:
      try:
        database.add_event({
          'type': 'comment',
          'guild': message.guild.id,
          'channel': message.author.voice.channel.id,
          'user': message.author.id,
          'message_channel': message.channel.id,
          'message': message.id,
          'content': content,
        })
      except database.Throttled:
        await message.add_reaction('⏳')
      else:
        await message.add_reaction('✅')

    elif not content:
      await message.reply(f'''\
Hi there, <@{message.author.id}>!
I'm a Discord bot that monitors activity in voice channels on this server. To generate an activity report that you can then download and open in your web browser, you can either:
- mention me in that voice channel's chat,
- DM me the voice channel's mention, or
- mention me and then the voice channel in the same message in any channel.
To mention a voice channel you have to copy its ID and put it inside `<#` and `>`. You can also comment on an ongoing meeting as one of its participants by mentioning me and then writing the comment's contents in the same message. Please note that everyone's ability to submit comments is limited to once every {parse_duration(config['comment_cooldown'])} seconds.

Please direct all questions and feedback to my author's DMs - digitcrusher#8454. I'm licensed under the AGPL-3.0-or-later and you can view my original source code on https://github.com/digitcrusher/Discord-voice-channel-observer-bot''', suppress_embeds=True)

    else:
      await message.add_reaction('❌')

  async def on_raw_message_edit(self, payload):
    content = payload.data.get('content', '').lstrip().removeprefix(f'<@{self.user.id}>').strip()
    database.edit_comment(payload.message_id, content)

  async def on_raw_message_delete(self, payload):
    database.delete_comment(payload.message_id)

  async def on_raw_message_bulk_delete(self, payload):
    for message in payload.message_ids:
      database.delete_comment(message)

console.begin('bot')
console.register('start', None, 'starts the bot',                            start)
console.register('stop',  None, 'stops the bot',                             stop)
console.register('scan',  None, 'scans active users and available channels', lambda: asyncio.run(client.scan('console')))
console.end()
