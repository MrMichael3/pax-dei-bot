import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import asyncio

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import SheetsCog from the correct module
from cogs.sheets_cog import SheetsCog

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(dotenv_path='config/.env')

# Retrieve the bot token and sheet ID from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')
SHEET_ID = os.getenv('SPREADSHEET_ID')

if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")

if SHEET_ID is None:
    raise ValueError("SHEET_ID environment variable is not set.")

# Define intents
intents = discord.Intents.default()
intents.message_content = True  # Enable if your bot needs to read message content
# Configure other intents as needed

# Create a bot instance with intents
bot = commands.Bot(command_prefix='!', intents=intents)

async def update_sheet():
    try:
        sheets_cog = SheetsCog(bot)
        await sheets_cog.load_sheet(SHEET_ID)
        logger.info('Sheet updated successfully')
    except Exception as e:
        logger.error(f'Error updating sheet: {e}')

async def main():
    try:
        await update_sheet()
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
