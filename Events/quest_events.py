import re
from Cogs.quest import  Quest_Data
from datetime import datetime, timedelta
from Imports.discord_imports import *
from Imports.log_imports import *
from Data.const import Quest_Progress, error_custom_embed, primary_color, QuestEmbed, Quest_Prompt, Quest_Completed_Embed


class Quest_Checker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quest_data = Quest_Data(bot)
        logger.debug("Quest_Checker initialized")

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
                if quest['channel_id'] == message.channel.id:
                    quest_content = quest['content']  # Quest content with {member}
                    
                    member_id_pattern = r'<@!?(\d+)>'
                    message_content = message.content
                    member_ids = re.findall(member_id_pattern, message_content)
                    if member_ids:
                        # Filter out the message author's ID and bot IDs
                        member_ids = [m_id for m_id in member_ids if m_id != str(message.author.id) and not message.guild.get_member(int(m_id)).bot]
                        if member_ids:
                            message_content = re.sub(member_id_pattern, f'<@{member_ids[0]}>', message_content)
                        else:
                            # If no valid member IDs left, continue to the next quest
                            continue
                    
                    quest_content_replaced = quest_content.replace('{member}', f'<@{member_ids[0]}>')  # Replace {member} with a placeholder for mention
                    quest_content_re_pattern = re.escape(quest_content_replaced)

                    if re.search(quest_content_re_pattern, message_content, re.IGNORECASE):
                        quest['progress'] += 1
                        print(f"Quest logic matched for user {message.author} in guild {message.guild} with content: {quest_content_replaced}")

                        await self.update_quest_progress(guild_id, user_id, quest['quest_id'], quest['progress'])

                    if quest['progress'] >= quest['times']:
                        times = quest['times']
                        user_mention = message.author.mention
                        quest_id = quest['quest_id']
                        await self.complete_quest(guild_id, user_id, quest, times, user_mention, quest_id, message)
                        for _ in range(3):
                            await self.quest_data.add_new_quest(guild_id, message.author)
     except Exception:
        logger.exception("Error occurred in on_message")    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            logger.debug("Reaction from bot detected. Ignoring.")
            return
        
        try:
            guild_id = str(reaction.message.guild.id)
            user_id = str(user.id)
            logger.debug(f"Reaction added by user_id: {user_id} in guild_id: {guild_id}")

            quests = await self.quest_data.find_quests_by_user_and_server(user_id, guild_id)
            logger.debug(f"Found quests: {quests}")

            if not quests:
                logger.debug("No quests found for user.")
                return

            for quest in quests:
                logger.debug(f"Processing quest: {quest}")
                if quest['action'] == 'react' and quest['method'] == 'reaction':
                    if quest['channel_id'] == reaction.message.channel.id and quest['content'] in str(reaction.emoji):
                        logger.debug("Quest reaction match found.")
                        quest['progress'] += 1
                        if quest['progress'] >= quest['times']:
                            logger.debug(f"Quest completed: {quest}")
                            await self.complete_quest(guild_id, user_id, quest, reaction.message)
                        else:
                            logger.debug(f"Updating quest progress: {quest['progress']}")
                            await self.update_quest_progress(guild_id, user_id, quest['quest_id'], quest['progress'])
        except Exception as e:
            logger.error(f"Error occurred in on_reaction_add event: {e}")
            traceback.print_exc()

    async def complete_quest(self, guild_id, user_id, quest, times, user_mention, quest_id, message):
        try:
            logger.debug(f"Completing quest: {quest_id} for user_id: {user_id} in guild_id: {guild_id}")
            channel = self.bot.get_channel(quest['channel_id'])
            if channel:
                embed = await Quest_Completed_Embed.create_embed(
                    self.bot, quest['content'], channel.mention, times, user_mention, quest_id
                )
                await channel.send(embed=embed, reference=message)

            await self.quest_data.delete_quest_for_user(guild_id, user_id, quest['quest_id'])
            logger.debug(f"Quest {quest['quest_id']} deleted for user {user_id} in guild {guild_id}.")

        except Exception as e:
            logger.error(f"Error occurred while completing quest: {e}")
            traceback.print_exc()

    async def update_quest_progress(self, guild_id, user_id, quest_id, progress):
        try:
            logger.debug(f"Updating progress for quest_id: {quest_id} for user_id: {user_id} in guild_id: {guild_id} to progress: {progress}")
            await self.quest_data.update_quest_progress(guild_id, user_id, quest_id, progress)
            logger.debug(f"Quest {quest_id} progress updated for user {user_id} in guild {guild_id}.")
        except Exception as e:
            logger.error(f"Error occurred while updating quest progress: {e}")
            traceback.print_exc()

def setup(bot):
    bot.add_cog(Quest_Checker(bot))
