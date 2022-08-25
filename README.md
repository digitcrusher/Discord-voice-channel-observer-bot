# Discord voice channel observer bot

Just as the name suggests, this is a Discord bot that monitors voice channels and gives reports on activity in them. You can invite my instance of the bot using [this invite link](https://discord.com/api/oauth2/authorize?client_id=1011553207031431168&permissions=1150016&scope=bot).

## Setup

1. Make sure you have Python 3 installed.
2. Install discord.py, which you can do with `pip3 install -r requirements.txt`.
3. Put your bot's token in `config.json`.
4. Run `./main.py`.
5. Enjoy.

The bot will save its data in `database.json` and `database.json.old`. You can connect to its console using `telnet localhost 4123`.
