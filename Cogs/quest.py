import traceback
import re
import typing
from Imports.discord_imports import *
from Data.const import Quest_Progress, error_custom_embed, primary_color, QuestEmbed, Quest_Prompt, Quest_Completed_Embed

from Imports.log_imports import *
import motor.motor_asyncio
from pymongo.errors import PyMongoError
import os



class Quest_Data(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DB_NAME = 'Quest'

        # Initialize MongoDB connection
        mongo_url = os.getenv('MONGO_URI')
        if not mongo_url:
            raise ValueError("No MONGO_URI found in environment variables")
        self.mongoConnect = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)

    async def handle_error(self, interaction, error, title):
        await error_custom_embed(self.bot, interaction, str(error), title=title)

    async def validate_input(self, **kwargs):
        for key, value in kwargs.items():
            if value is None or value == "":
                raise ValueError(f"{key} cannot be None or empty")
                
    async def find_users_in_server(self, guild_id: str):
     try:
        db = self.mongoConnect[self.DB_NAME]
        server_collection = db['Servers']
        
        # Log the query being made
        logger.debug(f"Querying for guild_id: {guild_id}")
        
        # Find the guild document by its ID
        guild_document = await server_collection.find_one({'guild_id': str(guild_id)})
        
        if guild_document:
            # Extract the members data from the guild document
            members_data = guild_document.get('members', {})
            users_in_server = list(members_data.keys())  # Extract user IDs
            
            logger.debug(f"Found {len(users_in_server)} users in server {guild_id}.")
            return users_in_server
        else:
            logger.debug(f"No guild found with ID {guild_id}.")
            return []
     except PyMongoError as e:
        logger.error(f"Error occurred while finding users in server: {e}")
        return []

    async def find_users_with_quest(self, guild_id: str, quest_id: int):
     try:
        db = self.mongoConnect[self.DB_NAME]
        server_collection = db['Servers']
        
        # Log the query being made
        logger.debug(f"Querying for guild_id: {guild_id} with quest_id: {quest_id}")
        
        # Find the guild document by its ID
        guild_document = await server_collection.find_one({'guild_id': str(guild_id)})
        
        if guild_document:
            # Extract the members data from the guild document
            members_data = guild_document.get('members', {})
            users_with_quest = []
            
            # Iterate through each user and their quests to find the specified quest
            for user_id, user_data in members_data.items():
                quests = user_data.get('quests', [])
                if any(quest['quest_id'] == quest_id for quest in quests):
                    users_with_quest.append(user_id)
            
            logger.debug(f"Found {len(users_with_quest)} users with quest ID {quest_id} in guild {guild_id}.")
            return users_with_quest
        else:
            logger.debug(f"No guild found with ID {guild_id}.")
            return []
     except PyMongoError as e:
        logger.error(f"Error occurred while finding users with quest: {e}")
        return []
    
    async def find_quests_by_user_and_server(self, user_id: str, guild_id: str, interaction=None):
        try:
            await self.validate_input(user_id=user_id, guild_id=guild_id)
            db = self.mongoConnect[self.DB_NAME]
            server_collection = db['Servers']
            server_data = await server_collection.find_one({'guild_id': guild_id})
            if server_data:
                member_data = server_data.get('members', {}).get(user_id, {})
                quests = member_data.get('quests', [])
                logger.debug(f"Found {len(quests)} quests for user {user_id} in guild {guild_id}.")
                return quests
            else:
                logger.debug("No server data found.")
                return []
        except PyMongoError as e:
            logger.error(f"Error occurred while finding quests: {e}")
            if interaction:
                await self.handle_error(interaction, e, title="Quest Finding")
            return None

    async def insert_quest(self, guild_id: str, user_id: str, quest_data: dict, interaction=None):
        try:
            quest_data['progress'] = 0  # Add progress field with default value 0
            await self.validate_input(**quest_data)
            db = self.mongoConnect[self.DB_NAME]
            server_collection = db['Servers']
            
            # Append the quest data to the appropriate spot
            await server_collection.update_one(
                {'guild_id': guild_id, f'members.{user_id}.quests': {'$not': {'$elemMatch': {'quest_id': quest_data['quest_id']}}}},
                {'$push': {f'members.{user_id}.quests': quest_data}},
                upsert=True
            )
            logger.debug(f"Inserted quest data for user {user_id} in guild {guild_id}.")
        except (ValueError, PyMongoError) as e:
            logger.error(f"Error occurred while inserting quest: {e}")
            if interaction:
                await self.handle_error(interaction, e, title="Quest Insertion")

    async def get_latest_quest_id(self, guild_id: str, user_id: str, interaction=None) -> int:
        try:
            db = self.mongoConnect[self.DB_NAME]
            server_collection = db['Servers']
            server_data = await server_collection.find_one({'guild_id': guild_id})
            if server_data:
                member_data = server_data.get('members', {}).get(user_id, {})
                quests = member_data.get('quests', [])
                latest_quest = max([quest.get('quest_id', 0) for quest in quests], default=0)
                logger.debug(f"Latest quest ID for user {user_id} in guild {guild_id}: {latest_quest}.")
                return latest_quest
            else:
                logger.debug(f"No server data found for user {user_id} in guild {guild_id}.")
                return 0
        except PyMongoError as e:
            logger.error(f"Error occurred while getting latest quest ID: {e}")
            if interaction:
                await self.handle_error(interaction, e, title="Latest Quest ID")
            return 0

    async def create_new_quest_for_all(
        self,
        guild_id: str,
        action: str,
        method: str,
        channel_id: int,
        times: int,
        content: str,
        interaction=None):
        
        try:
            logger.debug('create_new_quest_for_all has been activated')
            await self.validate_input(guild_id=guild_id, action=action, method=method, channel_id=channel_id, times=times, content=content)
            users_in_server = await self.find_users_in_server(guild_id)
            logger.debug(f"Found {len(users_in_server)} users in server.")
            
            new_quest_id = None  # Initialize new_quest_id outside the loop
            
            for user_id in users_in_server:
                latest_quest_id = await self.get_latest_quest_id(guild_id, user_id)
                new_quest_id = latest_quest_id + 1 if latest_quest_id is not None else 1
                
                quest_data = {
                    'quest_id': new_quest_id,
                    'action': action,
                    'method': method,
                    'channel_id': channel_id,
                    'times': times,
                    'content': content,
                    'progress': 0  # Initialize progress to 0
                }
                logger.debug(f"Creating quest for user_id: {user_id}, guild_id: {guild_id}, quest_data: {quest_data}")
                await self.insert_quest(guild_id, user_id, quest_data)
                logger.debug(f"Quest created for user_id: {user_id}, guild_id: {guild_id}, quest_data: {quest_data}")
            
            # Return new_quest_id after the loop
            return new_quest_id  # Return the new quest_id
        
        except Exception as e:
            logger.error(f"Error occurred while creating new quest for all users: {e}")
            if interaction:
                await self.handle_error(interaction, e, title="Quest Creation for All")
    

    async def add_user_to_server(self, user_id: str, guild_id: str):
        try:
            db = self.mongoConnect[self.DB_NAME]
            server_collection = db['Servers']
            server_data = await server_collection.find_one({'guild_id': guild_id})
            if not server_data:
                server_data = {'guild_id': guild_id, 'members': {}}

            members_data = server_data.get('members', {})
            members_data[user_id] = {'quests': []}

            await server_collection.update_one(
                {'guild_id': guild_id},
                {'$set': {'members': members_data}},
                upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Error occurred while adding user to server: {e}")

    
    async def delete_quest(self, guild_id: str, quest_id: int, interaction=None):
     try:
        db = self.mongoConnect[self.DB_NAME]
        server_collection = db['Servers']

        # Log the query being made
        logger.debug(f"Querying for guild_id: {guild_id} with quest_id: {quest_id}")

        # Find the guild document by its ID
        guild_document = await server_collection.find_one({'guild_id': str(guild_id)})

        if not guild_document:
            logger.debug(f"No guild found with ID {guild_id}.")
            return

        # Extract the members data from the guild document
        members_data = guild_document.get('members', {})

        # Loop through each member
        for member_id, member_data in members_data.items():
            # Extract quests for the current member
            quests = member_data.get('quests', [])

            # Log the current quests for the member
            logger.debug(f"Current quests for user {member_id}: {quests}")

            # Check if any quest matches the specified quest ID
            if any(quest.get('quest_id') == quest_id for quest in quests):
                logger.debug(f"Found quest with ID {quest_id} for user {member_id} in guild {guild_id}.")
                
                # Remove the quests that match the quest_id
                new_quests = [quest for quest in quests if quest.get('quest_id') != quest_id]

                # Update the guild document with the modified member data
                result = await server_collection.update_one(
                    {'guild_id': str(guild_id)},
                    {'$set': {f'members.{member_id}.quests': new_quests}}
                )

                if result.modified_count > 0:
                    logger.debug(f"Deleted quest with ID {quest_id} for user {member_id} in guild {guild_id}.")
                else:
                    logger.debug(f"Failed to delete quest with ID {quest_id} for user {member_id} in guild {guild_id}.")
            else:
                logger.debug(f"No quest with ID {quest_id} found for user {member_id} in guild {guild_id} to delete.")

     except PyMongoError as e:
        logger.error(f"Error occurred while deleting quest: {e}")
        if interaction:
            await self.handle_error(interaction, e, title="Quest Deletion")
   
    async def delete_quest_for_user(self, guild_id: str, user_id: str, quest_id: int, interaction=None):
     try:
        db = self.mongoConnect[self.DB_NAME]
        server_collection = db['Servers']

        # Log the query being made
        logger.debug(f"Querying for guild_id: {guild_id} with quest_id: {quest_id}")

        # Find the guild document by its ID
        guild_document = await server_collection.find_one({'guild_id': str(guild_id)})

        if not guild_document:
            logger.debug(f"No guild found with ID {guild_id}.")
            return

        # Extract the members data from the guild document
        members_data = guild_document.get('members', {})

        # Check if the specified user exists in the guild
        if user_id not in members_data:
            logger.debug(f"No user found with ID {user_id} in guild {guild_id}.")
            return

        # Extract quests for the specified user
        user_quests = members_data[user_id].get('quests', [])

        # Loop through the user's quests
        for quest in user_quests:
            if quest.get('quest_id') == quest_id:
                user_quests.remove(quest)
                logger.debug(f"Deleted quest with ID {quest_id} for user {user_id} in guild {guild_id}.")
                break  # No need to continue searching once the quest is deleted

        # Update the guild document with the modified member data
        await server_collection.update_one(
            {'guild_id': guild_id},
            {'$set': {f'members.{user_id}.quests': user_quests}}
        )

     except PyMongoError as e:
        logger.error(f"Error occurred while deleting quest for user: {e}")
        if interaction:
            await self.handle_error(interaction, e, title="Quest Deletion")
    
    async def update_quest_progress(self, guild_id: str, user_id: str, quest_id: int, progress: int):
        try:
            db = self.mongoConnect[self.DB_NAME]
            server_collection = db['Servers']
            
            # Update the progress of the specified quest for the user
            await server_collection.update_one(
                {'guild_id': guild_id, f'members.{user_id}.quests.quest_id': quest_id},
                {'$set': {f'members.{user_id}.quests.$.progress': progress}}
            )

            logger.debug(f"Quest {quest_id} progress updated for user {user_id} in guild {guild_id}.")
        except PyMongoError as e:
            logger.error(f"Error occurred while updating quest progress: {e}")
            raise e

class Quest_Checker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quest_data = Quest_Data(bot)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        try:
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)
            quests = await self.quest_data.find_quests_by_user_and_server(user_id, guild_id)

            if not quests:
                return

            for quest in quests:
                if quest['action'] == 'send' and quest['method'] == 'message':
                    if quest['channel_id'] == message.channel.id and quest['content'] in message.content:
                        quest['progress'] += 1
                        if quest['progress'] >= quest['times']:
                            # Quest completed
                            await self.complete_quest(guild_id, user_id, quest)
                        else:
                            # Update progress
                            await self.update_quest_progress(guild_id, user_id, quest['quest_id'], quest['progress'])

        except Exception as e:
            logger.error(f"Error occurred in on_message event: {e}")
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return
        
        try:
            guild_id = str(reaction.message.guild.id)
            user_id = str(user.id)
            quests = await self.quest_data.find_quests_by_user_and_server(user_id, guild_id)

            if not quests:
                return

            for quest in quests:
                if quest['action'] == 'react' and quest['method'] == 'reaction':
                    if quest['channel_id'] == reaction.message.channel.id and quest['content'] in str(reaction.emoji):
                        quest['progress'] += 1
                        if quest['progress'] >= quest['times']:
                            # Quest completed
                            await self.complete_quest(guild_id, user_id, quest)
                        else:
                            # Update progress
                            await self.update_quest_progress(guild_id, user_id, quest['quest_id'], quest['progress'])

        except Exception as e:
            logger.error(f"Error occurred in on_reaction_add event: {e}")
            traceback.print_exc()

    async def complete_quest(self, guild_id, user_id, quest):
        try:
            # Notify the user about the quest completion
            channel = self.bot.get_channel(quest['channel_id'])
            if channel:
              embed = await Quest_Completed_Embed.create_embed(self.bot,quest['content'], channel.mention)
              await channel.send(embed=embed)

            # Delete the completed quest for this user
            await self.quest_data.delete_quest_for_user(guild_id, user_id, quest['quest_id'])

            logger.debug(f"Quest {quest['quest_id']} completed for user {user_id} in guild {guild_id}.")

        except Exception as e:
            logger.error(f"Error occurred while completing quest: {e}")
            traceback.print_exc()

    async def update_quest_progress(self, guild_id, user_id, quest_id, progress):
        try:
            await self.quest_data.update_quest_progress(guild_id, user_id, quest_id, progress)
            logger.debug(f"Quest {quest_id} progress updated for user {user_id} in guild {guild_id}.")
        except Exception as e:
            logger.error(f"Error occurred while updating quest progress: {e}")
            traceback.print_exc()

       
class Quest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quest_data = Quest_Data(bot)

    @commands.command()
    async def quest(self, ctx):
        logger.debug("Quest command invoked.")
        try:
            user_id = str(ctx.author.id)
            guild_id = str(ctx.guild.id)
            quests = await self.quest_data.find_quests_by_user_and_server(user_id, guild_id)

            if quests:
                embed = discord.Embed(title="Quest", color=primary_color())
                for quest in quests:
                    quest_id = quest['quest_id']
                    progress = quest['progress']
                    times = quest['times']
                    action = quest['action']
                    method = quest['method']
                    content = quest['content']
                    channel = self.bot.get_channel(quest['channel_id'])
                    progress_bar = await Quest_Progress.generate_progress_bar(progress / times, self.bot)
                    embed.add_field(
                        name=" ",
                        value=f"`{quest_id}` **{action.title()} {method.title()}: `{content}` in {channel.mention}**\n{progress_bar} `{progress}/{times}`",
                        inline=False
                    )
                await ctx.send(embed=embed)
            else:
                # Get the prompt embed from Quest_Prompt
                prompt_embed = await Quest_Prompt.get_embed()
                # Send the prompt message with buttons
                await ctx.send(embed=prompt_embed, view=Quest_Button(self.bot, ctx))
        except Exception as e:
            error_message = "An error occurred while fetching quests."
            logger.error(f"{error_message}: {e}")
            traceback.print_exc()
            await error_custom_embed(self.bot, ctx, error_message, title="Quest Fetch Error")
      
class Quest_Button(discord.ui.View):
    def __init__(self, bot, ctx):
        super().__init__()
        self.ctx = ctx
        self.bot = bot
        self.quest_data = Quest_Data(bot)


    async def add_user_to_server(self, interaction):
        logger.debug("Adding user to server.")
        try:
            user_id = str(self.ctx.author.id)
            guild_id = str(self.ctx.guild.id)
            users_in_server = await self.quest_data.find_users_in_server(guild_id)
            logger.debug(f"Users in server: {users_in_server}")

            if user_id not in users_in_server:
                await self.quest_data.add_user_to_server(user_id, guild_id)
                await interaction.response.send_message("You have been added to the game!", ephemeral=True)
                await interaction.followup.edit_message(interaction.message.id, view=None)

                logger.debug("User added to the game.")
            else:
                await interaction.response.send_message("You are already part of the game!", ephemeral=True)
                await interaction.followup.edit_message(interaction.message.id, view=None)
                logger.debug("User is already part of the game.\nBut you don't have any new quest given by your admin.")
        except Exception as e:
            error_message = "An error occurred while adding user to server."
            logger.error(f"{error_message}: {e}")
            traceback.print_exc()
            await error_custom_embed(self.bot, self.ctx, error_message, title="Add User Error")

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.add_user_to_server(button)


    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed = discord.Embed(title="Quest Canceled", description="You have declined the quest.", color=discord.Color.red())
        await button.response.edit_message(embed=embed, view=None)
           
class Quest_Slash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quest_data = Quest_Data(bot)
        super().__init__()

    @app_commands.command(
        name="create_quest",
        description="Create a new quest.",
    )
    @app_commands.describe(action='The action to perform for the quest. (e.g., send, receive, react)')
    @app_commands.describe(method='The method to use for the quest. (e.g., message, reaction)')
    @app_commands.choices(action=[
        discord.app_commands.Choice(name='send', value='send'), 
        discord.app_commands.Choice(name='receive', value='receive'), 
    ])
    @app_commands.choices(method=[
        discord.app_commands.Choice(name='message', value='message'),
        discord.app_commands.Choice(name='reaction', value='reaction')
    ])
    async def create_quest(
        self,
        interaction: discord.Interaction,
        action: discord.app_commands.Choice[str],
        method: discord.app_commands.Choice[str],
        channel: discord.TextChannel,
        times: typing.Optional[int] = 1,
    ) -> None:
        try:
            guild_id = str(interaction.guild_id)
            user_id = str(interaction.user.id)
            
            # Prompt user for additional content
            await interaction.response.send_message(
                content=f"Please provide the content for the {method.name}:",
                ephemeral=True
            )
            response = await self.bot.wait_for("message", check=lambda m: m.author == interaction.user)
            content = response.content
            await response.delete()

            # Create the quest
            quest_id = await self.quest_data.create_new_quest_for_all(guild_id, action.value, method.value, channel.id, times, content, interaction)
            if quest_id is not None:
                # Create the quest embed
                embed = await QuestEmbed.create_quest_embed("Created", quest_id, action.value, method.value, channel, times=times, content=content)
                
                # Send the embed
                await interaction.followup.send(embed=embed)
                logger.debug("Quest creation successful.")
            else:
                await interaction.followup.send("Try doing `...quest`")
                logger.debug("Failed to create the quest.")
                
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            traceback.print_exc()
            await error_custom_embed(self.bot, interaction, e, title="Quest Creation")
            
            
            
            
    @app_commands.command(
        name="delete_quest",
        description="Delete a quest by its ID.",
    )
    async def delete_quest(
     self,
     interaction: discord.Interaction,
     quest_id: int) -> None:
     try:
        guild_id = interaction.guild.id
        
        # Find all users in the guild
        users_in_guild = await self.quest_data.find_users_in_server(guild_id)
        
        if not users_in_guild:
            await interaction.response.send_message("No users found in the server.", ephemeral=True)
            return
        
        quest_deleted = False

        for user_id in users_in_guild:
            # Check if the quest exists for the user
            quest_exists =  await self.quest_data.find_users_with_quest(guild_id, quest_id)
            if quest_exists:
                # Delete the quest for this user
                await self.quest_data.delete_quest(guild_id, quest_id)
                quest_deleted = True

        if quest_deleted:
            await interaction.response.send_message(f"The quest with ID {quest_id} has been deleted for all users who had it.", ephemeral=True)
        else:
            await interaction.response.send_message("The specified quest does not exist for any user.", ephemeral=True)
        
     except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        await self.quest_data.handle_error(interaction, e, title="Quest Deletion")

          
def setup(bot):
    bot.add_cog(Quest_Data(bot))
    bot.add_cog(Quest(bot))
    bot.add_cog(Quest_Checker(bot))
    bot.add_cog(Quest_Slash(bot))
