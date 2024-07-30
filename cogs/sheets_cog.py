import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

# TODO: Funktion /item [name] vorschlagen -> speichert den Vorschlag in einer Liste im Sheet
# TODO: Funktion /Preisanpassung [Preis] -> Du möchtest das der Preis x% günstiger/teurer wird? Bestätigen mit Buttons, speichert den Vorschlag in einer Liste im Sheet
# TODO: Funktion /Rezept [item] -> Zeigt im embeded alle Zutaten an
# TODO: Funktion /Rezeptfehler melden [item] [Erklärung] -> Speichert Eintrag in einer Liste im Sheet


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

# taler icon
taler_icon_server_id = os.getenv('ICON_TALER_SERVER_ID')
taler_icon_name = os.getenv('ICON_TALER_NAME')

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
        self.sheet_all_items = None
        self.sheet_suggestions = None
        self.data_cache = None
        
    async def load_sheet(self, sheet_id):
        
        try:
            google_client = await call_google_api()
            self.sheet_all_items = google_client.open_by_key(sheet_id).worksheet('Alle Items')
            self.sheet_suggestions = google_client.open_by_key(sheet_id).worksheet('Anpassungen')
            logger.info("Loaded sheets")
            self.data_cache = self.sheet_all_items.get_all_values()
        except Exception as e:
            logger.error(f'Error loading sheet: {e}')
    
    
    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
            if self.data_cache is None:
                await self.load_sheet(sheet_id)
            try:
                
                item_names = [row[0] for row in self.data_cache[1:]]  # Items in column A

                # Filter and provide auto-complete choices
                choices = [discord.app_commands.Choice(name=item, value=item) for item in item_names if current.lower() in item.lower()]
                return [choice for choice in choices if 1 <= len(choice.name) <= 100][:25]  # Limit the number of choices to 25
            except Exception as e:
                logger.error(f'Error during auto-complete: {e}')
                return []
    
    @staticmethod
    def format_number(num):
        return f"{num:.2f}" if num % 1 else f"{int(num)}"
    
    @staticmethod
    def format_margin(marge):
        return f'{int(marge)}' if marge.is_integer() else f'{marge}'
    
    
    def get_custom_emoji(self):
        guild = self.bot.get_guild(int(taler_icon_server_id))
        if guild:
            for emoji in guild.emojis:
                if str(emoji) == str(taler_icon_name):
                    return str(emoji)                
            return "Taler"
        return None
    
    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    @discord.app_commands.command(name='update', description='Lädt die aktuelle Preise des Google Sheets. Muss nach manuellen Preisänderungen ausgeführt werden.')
    async def update(self, interaction:discord.Interaction):
        await self.load_sheet(sheet_id)
        await interaction.response.send_message('Die Liste wurde aktualisiert')
    
        
    @discord.app_commands.autocomplete(name=item_autocomplete)
    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    @discord.app_commands.command(name="suche", description="sucht einen Gegenstand und gibt den Listenpreis an")
    @discord.app_commands.describe(name="Name des gesuchten Gegenstandes", menge="Optional: gewünschte Menge", marge="Optional: gewünschte Marge in Prozent")
    async def search(self, interaction:discord.Interaction, name:str, menge:int = 1, marge: float = None):
        if self.data_cache is None:
            await self.load_sheet(sheet_id)
        try:
            data = self.data_cache
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
            standard_margin = margins[index]

            # custom margin
            if marge is not None:
                marge_decimal = marge / 100
                item_price = item_price / (1+standard_margin / 100) * (1+marge_decimal)
            show_price = self.format_number(item_price)
            
            taler_icon = self.get_custom_emoji()
            
                
            if menge > 1:
                if marge is None:
                    formatted_marge = self.format_margin(standard_margin)
                    if standard_margin == 0:
                        await interaction.response.send_message(f'{menge} {name} kosten **{show_price} {taler_icon}**')
                    else:
                        await interaction.response.send_message(f'{menge} {name} kosten **{show_price} {taler_icon}** bei einer Standardmarge von {formatted_marge}%')
                else:
                    formatted_marge = self.format_margin(marge)
                    if marge == 0:
                        await interaction.response.send_message(f'{menge} {name} kosten **{show_price} {taler_icon}** bei 0% Marge')
                    else:
                        await interaction.response.send_message(f'{menge} {name} kosten **{show_price} {taler_icon}** bei einer Marge von {formatted_marge}%')
            else:
                if marge is None:
                    formatted_marge = self.format_margin(standard_margin)
                    if standard_margin == 0:
                        await interaction.response.send_message(f'{menge} {name} kostet **{show_price} {taler_icon}**')
                    else:
                        await interaction.response.send_message(f'{menge} {name} kostet **{show_price} {taler_icon}** bei einer Standardmarge von {formatted_marge}%')
                else:
                    formatted_marge = self.format_margin(marge)
                    if marge == 0:
                        await interaction.response.send_message(f'{menge} {name} kostet **{show_price} {taler_icon}** bei 0% Marge')
                    else:
                        await interaction.response.send_message(f'{menge} {name} kostet **{show_price} {taler_icon}** bei einer Marge von {formatted_marge}%')
  
            logger.info(f'Found item {name} with amount {menge} for the price of {show_price}')
        except Exception as e:
            logger.error(f'Error processing search command: {e}')
            await interaction.response.send_message('Es gab einen Fehler bei der Verarbeitung des Befehls.')
    
    
    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    @discord.app_commands.describe(item="Name des Gegenstandes", neuer_preis="Neuer Preisvorschlag")
    @discord.app_commands.command(name="preisanpassung", description="Schlage eine Preisänderung vor")
    @discord.app_commands.autocomplete(item=item_autocomplete)
    async def price_suggestion(self, interaction:discord.Interaction, item: str, neuer_preis: float):
        if self.data_cache is None:
            await self.load_sheet(sheet_id)
        
        try:
            data = self.data_cache
            item_names = [row[0] for row in data[1:]]
            if item not in item_names:
                await interaction.response.send_message(f'Item {item} ist nicht in der Liste. Mit dem Command "/item-vorschlagen" kannst du fehlende Items melden.')
                return
            prices = [
                float(row[1].replace('€', '').replace('.', '').replace(',', '.').strip())
                if row[1].replace('€', '').replace('.', '').replace(',', '').strip().replace('.', '', 1).isdigit()
                else 0
                for row in data[1:]
            ]
            timestamp = datetime.now().strftime("%d.%m.%Y")
            index = item_names.index(item)
            old_price = prices[index]
            user = interaction.user.name
            suggestion_row = [timestamp,item, old_price, neuer_preis, user]
            self.sheet_suggestions.append_row(suggestion_row,table_range='A:E')
            taler_icon = self.get_custom_emoji()
            await interaction.response.send_message(f'Preisanpassung für **{item}** von {old_price}{taler_icon} auf **{neuer_preis}{taler_icon}** vorgeschlagen. Der Stadtrat schaut sich die Vorschläge regelmässig an und nimmt wenn nötig, Änderungen an den Preisen vor.')
            logger.info(f'Price adjustment for {item} suggested by {user}: {old_price} -> {neuer_preis}')
        except Exception as e:
            logger.error(f'Error processing price adjustment command: {e}')
            await interaction.response.send_message('Es gab einen Fehler bei der Verarbeitung des Befehls.')






async def setup(bot: commands.Bot):
    try:
        sheets_cog = SheetsCog(bot)
        await sheets_cog.load_sheet(sheet_id)
        await bot.add_cog(sheets_cog)
        logger.info('SheetsCog loaded and Google Sheet loaded successfully.')
    except Exception as e:
        logger.error(f'Error loading SheetsCog: {e}')