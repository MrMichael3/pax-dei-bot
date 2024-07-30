import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

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
        self.sheet_calculations = None
        self.data_cache = None
        self.suggestions_cache = None
        self.calculations_cache = None
        
    async def load_sheet(self, sheet_id):
        
        try:
            google_client = await call_google_api()
            self.sheet_all_items = google_client.open_by_key(sheet_id).worksheet('Alle Items')
            self.sheet_suggestions = google_client.open_by_key(sheet_id).worksheet('Anpassungen')
            self.sheet_calculations = google_client.open_by_key(sheet_id).worksheet('Berechnungen')
            logger.info("Loaded sheets")
            self.data_cache = self.sheet_all_items.get_all_values()
            self.suggestions_cache = self.sheet_suggestions.get_all_values()
            self.calculations_cache = self.sheet_calculations.get_all_values()
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
        await interaction.response.defer()
        await self.load_sheet(sheet_id)
        await interaction.followup.send('Die Liste wurde aktualisiert')
    
        
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
            timestamp = datetime.now().strftime("%d.%m.%y")
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


    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    @discord.app_commands.command(name='neues-item', description='Schlägt ein fehlendes Item vor.')
    @discord.app_commands.describe(item="Name des fehlenden Gegenstandes")
    async def new_item_suggestion(self, interaction: discord.Interaction, item: str):
        if self.data_cache is None:
            await self.load_sheet(sheet_id)

        try:
            # Validate item
            item_names = [row[0] for row in self.data_cache[1:]]
            if item in item_names:
                await interaction.response.send_message(f'**{item}** ist bereits in der Liste.')
                return
            # Validate item in new items cache
            suggested_items = [row[1] for row in self.suggestions_cache[1:]]  # Items in column H
            if item in suggested_items:
                await interaction.response.send_message(f'**{item}** wurde bereits vorgeschlagen.')
                return
            # Append new item suggestion to the sheet
            timestamp = datetime.now().strftime("%d.%m.%y")
            user = interaction.user.name
            suggestion_row = [timestamp, item, user]
            self.sheet_suggestions.append_row(suggestion_row, table_range='G:I')
            # Update new items cache
            self.suggestions_cache.append([timestamp, item, user])

            await interaction.response.send_message(f'Der Gegenstand **{item}** wird geprüft und sobald möglich der Liste hinzugefügt. Danke für die Meldung. Nutze den Befehl um weitere Gegenstände zu melden.')
            logger.info(f'New item {item} suggested by {user}')
            
        except Exception as e:
            logger.error(f'Error processing new item suggestion command: {e}')
            await interaction.response.send_message('Es gab einen Fehler bei der Verarbeitung des Befehls.')


    @discord.app_commands.guilds(*[discord.Object(id=guild_id) for guild_id in guild_ids])
    @discord.app_commands.command(name='rezept', description='Zeigt das Rezept eines Gegenstandes an.')
    @discord.app_commands.describe(item="Name des Gegenstandes")
    @discord.app_commands.autocomplete(item=item_autocomplete)
    async def recipe(self, interaction: discord.Interaction, item: str):
        if self.data_cache is None or self.calculations_cache is None:
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
            margins = [
                float(row[2].replace('€', '').replace(',', '.').strip().replace('%', ''))
                if row[2].replace('€', '').replace(',', '.').strip().replace('%', '').replace('.', '', 1).isdigit()
                else 0
                for row in data[1:]
            ] 

            # Find the item row in calculations sheet
            item_row = None
            item_column = None
            for row in self.calculations_cache:
                if row[3] == item:
                    item_row = row
                    item_column = "D"
                    break
                elif row[17] == item:
                    item_row = row
                    item_column = "R"
                    break
                elif row[32] == item:
                    item_row = row
                    item_column = "AG"
                    break

            if not item_row:
                await interaction.response.send_message(f'Kein Rezept für {item} gefunden.')
                return

            ingredients = []
            production_time = 0        
            if(item_column == "D"):
                start = 5
                production_time = item_row[14]
                for i in range(0,7,2):  # Up to 4 ingredients
                    ingredient = item_row[start  + i ]               
                    quantity = item_row[start  + i + 1]
                    if ingredient and quantity:
                        ingredients.append((ingredient, quantity))
            elif(item_column == "R"):
                start = 19
                for i in range(0,9,2):  # Up to 5 ingredients
                    ingredient = item_row[start  + i ]           
                    quantity = item_row[start  + i + 1]
                    if ingredient and quantity:
                        ingredients.append((ingredient, quantity))
            elif(item_column == "AG"):
                start = 34
                for i in range(0,17,2):  # Up to 9 ingredients
                    ingredient = item_row[start  + i ]
                    quantity = item_row[start  + i + 1]
                    if ingredient and quantity:
                        ingredients.append((ingredient, quantity))
                    
            # Find price of the item
            index = item_names.index(item)
            item_price = prices[index]
            margin = margins[index]
            taler_icon = self.get_custom_emoji()
            # Create an embed
            embed = discord.Embed(title=f"Rezept für {item}", color=discord.Color.blue())
            embed.add_field(name=f"Preis: {item_price} {taler_icon}", value=f"Marge: {margin}%", inline=False)
            if production_time:
                embed.set_footer(text=f"Herstellungszeit: {production_time} min")
            embed.add_field(name="Zutaten", value="\n".join(f"{qty}x **{ing}**" for ing, qty in ingredients), inline=False)
           

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f'Error processing recipe command: {e}')
            await interaction.response.send_message('Es gab einen Fehler bei der Verarbeitung des Befehls.')

async def setup(bot: commands.Bot):
    try:
        sheets_cog = SheetsCog(bot)
        await sheets_cog.load_sheet(sheet_id)
        await bot.add_cog(sheets_cog)
        logger.info('SheetsCog loaded and Google Sheet loaded successfully.')
    except Exception as e:
        logger.error(f'Error loading SheetsCog: {e}')