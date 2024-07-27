import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv
import logging

# TODO: Funktion /item [name] vorschlagen -> speichert den Vorschlag in einer Liste im Sheet
# TODO: Funktion /Preisanpassung [Preis] -> Du möchtest das der Preis x% günstiger/teurer wird? Bestätigen mit Buttons, speichert den Vorschlag in einer Liste im Sheet
# TODO: Funktion /Rezept [item] -> Zeigt im embeded alle Zutaten an
# TODO: Funktion /Rezeptfehler melden [item] [Erklärung] -> Speichert Eintrag in einer Liste im Sheet
# TODO: Eingabe von Marge ändern damit es einfacher verständlich ist
# TODO: Das Icon für Taler verwenden


# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv(dotenv_path='config/.env')
#guild_id = int(os.getenv('GUILD_ID'))
# Get and verify environment variables
guild_ids_env = os.getenv('GUILD_IDS')
if guild_ids_env is None:
    raise ValueError("GUILD_IDS environment variable is not set.")

try:
    guild_ids = [int(id) for id in guild_ids_env.split(',')]
except ValueError:
    raise ValueError("GUILD_IDS must be a comma-separated list of integers.")
sheet_id = os.getenv('SPREADSHEET_ID')

async def call_google_api():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_path = 'config/credentials.json'
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        logger.info('Google Sheets client authenticated')
        return client
    except Exception as e:
        logger.error(f'Google Sheets authentication failed: {e}')
        raise

 

class SheetsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheet = None
        
    async def load_sheet(self, sheet_id):
        
        try:
            google_client = await call_google_api()
            self.sheet = google_client.open_by_key(sheet_id).worksheet('Alle Items')
            logger.info("Loaded sheet 'Alle Items'")
        except Exception as e:
            logger.error(f'Error loading sheet: {e}')
    
    
    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
            try:
                data = self.sheet.get_all_values()
                item_names = [row[0] for row in data[1:]]  # Items in column A

                # Filter and provide auto-complete choices
                choices = [discord.app_commands.Choice(name=item, value=item) for item in item_names if current.lower() in item.lower()]
                return [choice for choice in choices if 1 <= len(choice.name) <= 100][:25]  # Limit the number of choices to 25
            except Exception as e:
                logger.error(f'Error during auto-complete: {e}')
                return []
    
    @staticmethod
    def format_number(num):
        return f"{num:.2f}" if num % 1 else f"{int(num)}"
    
        
    @discord.app_commands.autocomplete(name=item_autocomplete)
    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    #@discord.app_commands.guilds(discord.Object(id=guild_id))   
    @discord.app_commands.command(name="suche", description="sucht einen Gegenstand und gibt den Listenpreis an")
    @discord.app_commands.describe(name="Name des gesuchten Gegenstandes", menge="Optional: gewünschte Menge", marge="Optional: gewünschte Marge")
    async def search(self, interaction:discord.Interaction, name:str, menge:int = 1, marge: float = None):
        try:
            data = self.sheet.get_all_values()
            item_names = [row[0] for row in data[1:]] # items in column A
            prices = [
                float(row[1].replace('€', '').replace('.', '').replace(',', '.').strip())
                if row[1].replace('€', '').replace('.', '').replace(',', '').strip().replace('.', '', 1).isdigit()
                else 0
                for row in data[1:]
            ]  # Prices in column B
            margins = [
                float(row[2].replace('€', '').replace(',', '.').strip().replace('%', ''))
                if row[2].replace('€', '').replace(',', '.').strip().replace('%', '').replace('.', '', 1).isdigit()
                else 0
                for row in data[1:]
            ]  # margins in column C
           
            # find item
            if name not in item_names:
                await interaction.response.send_message(f'Item {name} ist nicht in der Liste. Mit dem Command "/item-vorschlagen" kannst du fehlende Items melden')
                return
        
            index = item_names.index(name)
            item_price = prices[index]
            print(item_price)
            standard_margin = margins[index]
        
            # custom margin
            if marge is not None:
                item_price = item_price / (1+standard_margin) * (1+marge)
                print(f'Marge von {name}  von {standard_margin} auf {marge} geändert!')
            item_price = item_price * menge
            show_price = self.format_number(item_price)
            if menge > 1:
                await interaction.response.send_message(f'{menge} {name} kosten **{show_price} Taler**')
            else:
                await interaction.response.send_message(f'{menge} {name} kostet **{show_price} Taler**')
  
            logger.info(f'Found item {name} with amount {menge} for the price of {show_price}')
        except Exception as e:
            logger.error(f'Error processing search command: {e}')
            await interaction.response.send_message('Es gab einen Fehler bei der Verarbeitung des Befehls.')
    
    
    






async def setup(bot: commands.Bot):
    try:
        sheets_cog = SheetsCog(bot)
        await sheets_cog.load_sheet(sheet_id)
        await bot.add_cog(sheets_cog)
        logger.info('SheetsCog loaded and Google Sheet loaded successfully.')
    except Exception as e:
        logger.error(f'Error loading SheetsCog: {e}')