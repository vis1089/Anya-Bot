import os
import sys
import subprocess
import traceback
import asyncio
import requests

# Install dependencies if not present
os.system('pip install joblib')

from Imports.depend_imports import *
import Imports.depend_imports as depend_imports
from Imports.discord_imports import *
from Imports.log_imports import logger

from colorama import Fore, Style  # Import Fore and Style explicitly
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import pymongo  # Import database API
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError

from Cogs.pokemon import PokemonPredictor

class BotSetup(commands.AutoShardedBot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.members = True  # Enable member-related events and data
        super().__init__(command_prefix=commands.when_mentioned_or('...'), 
                         intents=intents, 
                         help_command=None, 
                         shard_count=3)
        self.mongoConnect = None  # Initialize the MongoDB connection attribute
        self.all_members = {}  # Store member data here

    async def on_ready(self):
        """Gather all users on startup and store them."""
        print(Fore.GREEN + f"Logged in as {self.user} (ID: {self.user.id})" + Style.RESET_ALL)
        print(Fore.BLUE + "Gathering members from all guilds..." + Style.RESET_ALL)

        # Create a list of asyncio tasks for fetching members
        fetch_tasks = [self.fetch_members(guild) for guild in self.guilds]

        # Execute all fetch tasks concurrently
        await asyncio.gather(*fetch_tasks)

        print(Fore.BLUE + "All members have been gathered and registered." + Style.RESET_ALL)

    async def fetch_members(self, guild):
        """Fetch members for a given guild and store them."""
        print(Fore.YELLOW + f"Processing Guild: {guild.name} (ID: {guild.id})" + Style.RESET_ALL)
        
        # Use a loop to fetch all members
        async for member in guild.fetch_members(limit=None):
            # Store user data in the dictionary (can be used later)
            self.all_members[member.id] = member
            print(Fore.GREEN + f"Registered Member: {member.name}#{member.discriminator}" + Style.RESET_ALL)

    async def start_bot(self):
        await self.setup()
        token = os.getenv('TOKEN')

        if not token:
            logger.error("No token found. Please set the TOKEN environment variable.")
            return

        try:
            await self.start(token)
        except KeyboardInterrupt:
            await self.close()
        except Exception as e:
            traceback_string = traceback.format_exc()
            logger.error(f"An error occurred while logging in: {e}\n{traceback_string}")
            await self.close()

    async def setup(self):
        print("\n")
        print(Fore.BLUE + "・ ── Cogs/" + Style.RESET_ALL)
        await self.import_cogs("Cogs")
        print("\n")
        print(Fore.BLUE + "・ ── Events/" + Style.RESET_ALL)
        await self.import_cogs("Events")

        print("\n")
        print(Fore.BLUE + "===== Setup Completed =====" + Style.RESET_ALL)

    async def import_cogs(self, dir_name):
        files_dir = os.listdir(dir_name)
        for filename in files_dir:
            if filename.endswith(".py"):
                print(Fore.BLUE + f"│   ├── {filename}" + Style.RESET_ALL)

                module = __import__(f"{dir_name}.{os.path.splitext(filename)[0]}", fromlist=[""])
                for obj_name in dir(module):
                    obj = getattr(module, obj_name)
                    if isinstance(obj, commands.CogMeta):
                        if obj_name == "PokemonPredictor":
                            existing_cog = self.get_cog("PokemonPredictor")
                            if existing_cog:
                                await self.remove_cog("PokemonPredictor")
                                print(Fore.RED + f"│   │   Removed {obj_name} cog" + Style.RESET_ALL)
                        else:
                            if not self.get_cog(obj_name):
                                await self.add_cog(obj(self))
                                print(Fore.GREEN + f"│   │   └── {obj_name}" + Style.RESET_ALL)

async def check_rate_limit():
    url = "https://discord.com/api/v10/users/@me"  # Example endpoint to get the current user
    headers = {
        "Authorization": f"Bot {os.getenv('TOKEN')}"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        remaining_requests = int(response.headers.get("X-RateLimit-Remaining", 1))
        rate_limit_reset_after = float(response.headers.get("X-RateLimit-Reset-After", 0))

        if remaining_requests <= 0:
            logger.error(f"Rate limit exceeded. Retry after {rate_limit_reset_after} seconds.")
            print(f"Rate limit exceeded. Please wait for {rate_limit_reset_after} seconds before retrying.")
            await asyncio.sleep(rate_limit_reset_after)
    else:
        logger.error(f"Failed to check rate limit. Status code: {response.status_code}")

async def main():
    #predictor = PokemonPredictor()
    #await predictor.initialize()  # Initialize the predictor asynchronously

    bot = BotSetup()

    try:
        await check_rate_limit()  # Check rate limits before starting the bot
        await bot.start_bot()
    except HTTPException as e:
        if e.status == 429:
            retry_after = int(e.response.headers.get("Retry-After", 0))
            logger.error(f"Rate limit exceeded. Retry after {retry_after} seconds.")
            print(f"Rate limit exceeded. Please wait for {retry_after} seconds before retrying.")
            await asyncio.sleep(retry_after)
        else:
            traceback_string = traceback.format_exc()
            logger.error(f"An error occurred: {e}\n{traceback_string}")
    except Exception as e:
        traceback_string = traceback.format_exc()
        logger.error(f"An error occurred: {e}\n{traceback_string}")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
