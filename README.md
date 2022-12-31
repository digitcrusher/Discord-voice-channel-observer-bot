# Discord voice channel observer bot

Just as the name suggests, this is a Discord bot that monitors voice channels and gives reports on activity in them. You can invite my instance of the bot using [this invite link](https://discord.com/api/oauth2/authorize?client_id=1011553207031431168&permissions=1150016&scope=bot).

![A screenshot](screenshot.png)

## Setup

1. Make sure you have Python 3 installed.
2. Install discord.py 2.x, which you can do with `pip3 install -r requirements.txt`.
3. Put your bot's token in `config.json`.
4. Set other available options in `config.json` at your will, a list of which you can find in [`common.py`](common.py#L23).
5. Run `./main.py` or `./main.py -c <path to config>`.
6. Enjoy.

By default, the bot will save its data in `database.json` and `database.json.old` and its console will be open locally on port 4123, which you can connect to using `telnet localhost 4123`.
