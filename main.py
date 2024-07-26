import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path='config/.env')
token = os.getenv('DISCORD_TOKEN')
guild_ids_str = os.getenv('GUILD_IDS')

# Convert guild_ids_str to a list of integers
try:
    guild_ids = [int(id) for id in guild_ids_str.split(',')]
except ValueError:
    raise ValueError("GUILD_IDS must be a comma-separated list of integers.")


intents = discord.Intents.default()
intents.message_content = True  

bot = commands.Bot( command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            await bot.tree.sync(guild=guild)
            print(f'Synced commands to guild {guild_id}')
    print(f'We have logged in as {bot.user}')
    
async def load_cogs():
    await bot.load_extension('cogs.sheets_cog')
    print("loaded extension ")


async def main():
    async with bot:
        print("start bot")
        await load_cogs()
        
        await bot.start(token)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())