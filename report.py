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

import html, typing as ty
from datetime import datetime, timedelta
from dataclasses import dataclass

import console, database
from common import config, parse_duration

@dataclass
class DisplayState:
  mute: bool
  deafen: bool
  stream: bool
  video: bool

  def __init__(self, user_state):
    self.mute = 'mute.user' in user_state or 'mute.guild' in user_state
    self.deafen = 'deafen.user' in user_state or 'deafen.guild' in user_state
    self.stream = 'stream' in user_state
    self.video = 'video' in user_state

@dataclass
class Sub:
  begin: datetime
  end: datetime
  display_state: set[DisplayState]

@dataclass
class Comment:
  time: datetime
  url: str
  content: str

@dataclass
class Bar:
  is_open: bool
  subs: list[Sub]
  comments: list[Comment]

  @property
  def begin(self):
    return self.subs[0].begin

  @property
  def end(self):
    return self.subs[-1].end

  @begin.setter
  def begin(self, value):
    self.subs[0].begin = value

  @end.setter
  def end(self, value):
    self.subs[-1].end = value

@dataclass
class Column:
  user: int
  name: str
  bars: list[Bar]

@dataclass
class Meeting:
  begin: datetime
  end: datetime
  channel: int
  columns: list[Column]

# We really don't care if the database is modified while generating a report
# and it ends up being corrupted, so we don't lock the database here.
def get_meetings(channel):
  result = []

  columns = {}
  begin_time = None
  end_time = None
  open_barc = 0

  def flush():
    nonlocal columns, open_barc

    if len(columns) >= 2:
      columns = list(columns.values())

      nonlocal end_time
      if open_barc > 0:
        end_time = datetime.now().astimezone()
      for column in columns:
        if not column.bars[-1].end:
          column.bars[-1].end = end_time

      def key(column):
        result = timedelta()
        for bar in column.bars:
          for sub in bar.subs:
            result += sub.end - sub.begin
        return result
      columns.sort(key=key, reverse=True)

      nonlocal result
      result.append(Meeting(begin_time, end_time, channel, columns))

    columns = {}
    open_barc = 0

  def begin_bar(user, time, display_state):
    if user not in columns:
      columns[user] = Column(user, database.data['user_names'].get(user, str(user)), [])
    columns[user].bars.append(Bar(True, [Sub(time, None, display_state)], []))
    nonlocal open_barc
    open_barc += 1

  def end_bar(user, time):
    columns[user].bars[-1].is_open = False
    columns[user].bars[-1].end = time
    nonlocal open_barc
    open_barc -= 1

  def add_sub(user, time, display_state):
    columns[user].bars[-1].subs[-1].end = time
    columns[user].bars[-1].subs.append(Sub(time, None, display_state))

  def add_comment(user, time, url, content):
    columns[user].bars[-1].comments.append(Comment(time, url, content))

  display_states = {}
  for event in database.data['events']:
    if not event:
      continue

    type = event['type']
    if type == 'user_state':
      new = DisplayState(event['value'])
      if new == display_states.get(event['user'], None):
        continue
      display_states[event['user']] = new

    if event['channel'] != channel or type not in {'join', 'leave', 'comment', 'user_state'}:
      continue

    time = datetime.fromisoformat(event['time'])
    interval = timedelta(seconds=parse_duration(config['meeting_interval']))
    if not columns or (open_barc == 0 and time > end_time + interval):
      flush()
      begin_time = time
      end_time = time

    user = event['user']
    if type == 'join':
      begin_bar(user, time, display_states[user])
    elif type == 'leave':
      end_bar(user, time)
    elif type == 'comment':
      add_comment(user, time, f'https://discord.com/channels/{event["guild"]}/{event["message_channel"]}/{event["message"]}', event['content'])
    elif type == 'user_state':
      if user in columns and not columns[user].bars[-1].end:
        add_sub(user, time, display_states[user])
    end_time = time
  flush()

  return result

def generate(channel):
  result = '<!DOCTYPE html>\n'
  result += '<html>\n'
  result += '<head>\n'
  result += '<meta charset="UTF-8">\n'
  result += '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
  result += '<style>\n'
  result += open('report.css', 'r').read()
  result += '</style>\n'
  result += '<script>\n'
  result += open('report.js', 'r').read()
  result += '</script>\n'
  result += '</head>\n'
  result += '<body>\n'

  url = ''
  if channel in database.data['channel_guilds']:
    url = f'https://discord.com/channels/{database.data["channel_guilds"][channel]}/{channel}'
  name = channel
  if channel in database.data['channel_names']:
    name = f'<q>{html.escape(database.data["channel_names"][channel])}</q>'
  result += '<header>\n'
  result += f'<h1>Activity report for voice channel <a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a></h1>\n'
  result += '</header>\n'

  result += '<main id="timeline">\n'
  result += '<div id="indicator"></div>\n'

  meetings = get_meetings(channel)
  prev_meeting_end = None
  for meeting in meetings:
    result += f'<div class="meeting-heading" data-begin="{(prev_meeting_end or meeting.begin).timestamp()}" data-end="{meeting.begin.timestamp()}">'
    result += f'<h2>Meeting on <time datetime="{meeting.begin}" data-timestamp="{meeting.begin.timestamp()}">{meeting.begin}</time></h2>'
    result += '</div>\n'
    prev_meeting_end = meeting.end

    result += f'<div class="meeting" data-begin="{meeting.begin.timestamp()}" data-end="{meeting.end.timestamp()}">\n'

    for i, column in enumerate(meeting.columns):
      hue = i * 360 / len(meeting.columns)
      result += f'<div class="column" style="--hue: {hue};" title="{html.escape(column.name)}">\n'

      prev_bar_end = meeting.begin
      for bar in column.bars:
        offset = (bar.begin - prev_bar_end).total_seconds()
        result += f'<div class="bar" style="margin-top: {offset}px;">'
        prev_bar_end = bar.end

        for comment in bar.comments:
          offset = (comment.time - bar.begin).total_seconds()
          result += f'<div class="comment" style="margin-top: {offset}px;" data-timestamp="{comment.time.timestamp()}" title="Commented on {comment.time}">'
          result += '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M4.79805 3C3.80445 3 2.99805 3.8055 2.99805 4.8V15.6C2.99805 16.5936 3.80445 17.4 4.79805 17.4H7.49805V21L11.098 17.4H19.198C20.1925 17.4 20.998 16.5936 20.998 15.6V4.8C20.998 3.8055 20.1925 3 19.198 3H4.79805Z"></path></svg>'
          result += f'<a href="{comment.url}" target="_blank" rel="noopener noreferrer">{html.escape(comment.content)}</a>'
          result += '</div>'

        class_ = 'subs open' if bar.is_open else 'subs'
        result += f'<div class="{class_}">'

        prev_class = None
        for sub in bar.subs:
          class_ = 'afk' if sub.display_state.deafen and not sub.display_state.stream and not sub.display_state.video else ''
          if class_ == prev_class:
            prev_class = class_
            class_ += ' repeated'
          else:
            prev_class = class_
          height = (sub.end - sub.begin).total_seconds()
          result += f'<div class="{class_}" style="height: {height}px;">'

          if height >= 24: # Tied to --icon-size
            if sub.display_state.mute:
              result += '<div title="Muted"><svg viewBox="0 0 24 24"><path d="M6.7 11H5C5 12.19 5.34 13.3 5.9 14.28L7.13 13.05C6.86 12.43 6.7 11.74 6.7 11Z" fill="currentColor"></path><path d="M9.01 11.085C9.015 11.1125 9.02 11.14 9.02 11.17L15 5.18V5C15 3.34 13.66 2 12 2C10.34 2 9 3.34 9 5V11C9 11.03 9.005 11.0575 9.01 11.085Z" fill="currentColor"></path><path d="M11.7237 16.0927L10.9632 16.8531L10.2533 17.5688C10.4978 17.633 10.747 17.6839 11 17.72V22H13V17.72C16.28 17.23 19 14.41 19 11H17.3C17.3 14 14.76 16.1 12 16.1C11.9076 16.1 11.8155 16.0975 11.7237 16.0927Z" fill="currentColor"></path><path d="M21 4.27L19.73 3L3 19.73L4.27 21L8.46 16.82L9.69 15.58L11.35 13.92L14.99 10.28L21 4.27Z" fill="currentColor"></path></svg></div>'
            if sub.display_state.deafen:
              result += '<div title="Deafened"><svg viewBox="0 0 24 24"><path d="M6.16204 15.0065C6.10859 15.0022 6.05455 15 6 15H4V12C4 7.588 7.589 4 12 4C13.4809 4 14.8691 4.40439 16.0599 5.10859L17.5102 3.65835C15.9292 2.61064 14.0346 2 12 2C6.486 2 2 6.485 2 12V19.1685L6.16204 15.0065Z" fill="currentColor"></path><path d="M19.725 9.91686C19.9043 10.5813 20 11.2796 20 12V15H18C16.896 15 16 15.896 16 17V20C16 21.104 16.896 22 18 22H20C21.105 22 22 21.104 22 20V12C22 10.7075 21.7536 9.47149 21.3053 8.33658L19.725 9.91686Z" fill="currentColor"></path><path d="M3.20101 23.6243L1.7868 22.2101L21.5858 2.41113L23 3.82535L3.20101 23.6243Z" fill="currentColor"></path></svg></div>'
            if sub.display_state.video:
              result += '<div title="Video"><svg viewBox="0 0 24 24"><path fill="currentColor" d="M21.526 8.149C21.231 7.966 20.862 7.951 20.553 8.105L18 9.382V7C18 5.897 17.103 5 16 5H4C2.897 5 2 5.897 2 7V17C2 18.104 2.897 19 4 19H16C17.103 19 18 18.104 18 17V14.618L20.553 15.894C20.694 15.965 20.847 16 21 16C21.183 16 21.365 15.949 21.526 15.851C21.82 15.668 22 15.347 22 15V9C22 8.653 21.82 8.332 21.526 8.149Z"></path></svg></div>'
            if sub.display_state.stream:
              result += '<div title="Streaming"><svg viewBox="0 0 24 24"><path fill="currentColor" fill-rule="evenodd" clip-rule="evenodd" d="M2 4.5C2 3.397 2.897 2.5 4 2.5H20C21.103 2.5 22 3.397 22 4.5V15.5C22 16.604 21.103 17.5 20 17.5H13V19.5H17V21.5H7V19.5H11V17.5H4C2.897 17.5 2 16.604 2 15.5V4.5ZM13.2 14.3375V11.6C9.864 11.6 7.668 12.6625 6 15C6.672 11.6625 8.532 8.3375 13.2 7.6625V5L18 9.6625L13.2 14.3375Z"></path></svg></div>'

          result += '</div>'
        result += '</div>\n'

        result += '</div>\n'
      result += '</div>\n'
    result += '</div>\n'
  result += '</main>\n'

  result += '<footer>\n'
  result += '<h2>Raw events</h2>\n'
  result += '<pre id="raw-events">\n'
  for event in database.data['events']:
    if event and event['channel'] == channel:
      result += str(event) + '\n'
  result += '</pre>\n'
  result += '</footer>\n'

  result += '</body>\n'
  result += '</html>\n'
  return result

def op_generate(arg):
  open('report.html', 'w').write(generate(int(arg)))

console.begin('report')
console.register('generate', '<channel>', 'generates a channel activity report and saves it to report.html', op_generate)
console.end()
