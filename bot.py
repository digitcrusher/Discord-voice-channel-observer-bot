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

import asyncio, discord, logging
from copy import deepcopy

import database
from common import config

# This code assumes that the bot can see all channels regardless of permissions.

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

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

def scan_active_users(reason):
  logging.info(f'Scanning active users with reason `{reason}`')
  with database.lock:
    active_users = deepcopy(database.data['active_users'])

    for guild in client.guilds:
      for channel in guild.voice_channels:
        for member in channel.members:
          database.add_event({
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
            database.add_event({
              'type': 'join',
              'guild': guild.id,
              'channel': channel.id,
              'user': member.id,
              'cause': 'scan.' + reason,
            })

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

def scan_available_channels(reason):
  logging.info(f'Scanning available channels with reason `{reason}`')

  presence_channelc = 0
  with database.lock:
    available_channels = deepcopy(database.data['available_channels'])

    for guild in client.guilds:
      for channel in guild.voice_channels:
        if channel.id in available_channels.get(guild.id, set()):
          available_channels[guild.id].remove(channel.id)
        else:
          database.add_event({
            'type': 'create',
            'guild': guild.id,
            'channel': channel.id,
            'cause': 'scan.' + reason,
          })
        presence_channelc += 1

    for guild, channels in available_channels.items():
      for channel in channels:
        database.add_event({
          'type': 'delete',
          'guild': guild,
          'channel': channel,
          'cause': 'scan.' + reason,
        })

  activity = discord.Activity(name=f'{presence_channelc} channels', type=discord.ActivityType.watching)
  asyncio.run(client.change_presence(activity=activity))

@client.event
async def on_ready():
  logging.info(f'Logged in as `{client.user}`')
  # This lock and the one in on_guild_join partially prevent situations where
  # a user leaves immediately after the channel scan and their previous presence
  # in the channel isn't registered.
  with database.lock:
    # The following order may cause a leave event following a delete event.
    scan_available_channels('bot_ready')
    scan_active_users('bot_ready')

@client.event
async def on_voice_state_update(member, before, after):
  event = {
    'type': None,
    'guild': None,
    'channel': None,
    'user': member.id,
    'cause': 'event.user',
  }

  if not after.channel:
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
    if before.channel:
      event['type'] = 'leave'
      event['guild'] = before.channel.guild.id
      event['channel'] = before.channel.id
      if after.afk:
        event['cause'] = 'event.afk'
      database.add_event(event)

    database.add_event(user_state_event)

    event['type'] = 'join'
    event['guild'] = after.channel.guild.id
    event['channel'] = after.channel.id
    database.add_event(event)
  else:
    database.add_event(user_state_event)

@client.event
async def on_guild_channel_create(channel):
  if isinstance(channel, discord.VoiceChannel):
    database.add_event({
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
    database.add_event({
      'type': 'delete',
      'guild': channel.guild.id,
      'channel': channel.id,
      'cause': 'event',
    })

@client.event
async def on_guild_join(guild):
  with database.lock:
    scan_available_channels('guild')
    scan_active_users('guild')

@client.event
async def on_guild_remove(guild):
  scan_active_users('guild')
  scan_available_channels('guild')

@client.event
async def on_message(message):
  if message.author == message.guild.me:
    return

  content = message.content.lstrip()
  if not content.startswith(f'<@{client.user.id}>'):
    return
  content = content.removeprefix(f'<@{client.user.id}>').strip()

  if not content or message.author.voice == None:
    await message.add_reaction('❌')
    return

  database.add_event({
    'type': 'comment',
    'guild': message.guild.id,
    'channel': message.author.voice.channel.id,
    'author': message.author.id,
    'message_channel': message.channel.id,
    'message': message.id,
    'content': content,
  })
  await message.add_reaction('✅')

@client.event
async def on_raw_message_edit(payload):
  content = payload.data.get('content', '').lstrip().removeprefix(f'<@{client.user.id}>').strip()
  database.edit_comment(payload.message_id, content)

@client.event
async def on_raw_message_delete(payload):
  database.delete_comment(payload.message_id)

@client.event
async def on_raw_message_bulk_delete(payload):
  for message in payload.message_ids:
    database.delete_comment(message)

def run():
  client.run(config['token'])
