import os
import logging
from datetime import datetime
from git import Repo
from difflib import get_close_matches

import Data.const as const
from Data.const import error_custom_embed
from Imports.log_imports import logger
from Imports.discord_imports import *
import traceback


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Permission(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logger  # Assumes bot has a logger configured
        self.error_custom_embed = error_custom_embed

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        try:
            if isinstance(error, commands.MissingPermissions):
                await self.notify_missing_permissions(ctx, error)
            elif isinstance(error, commands.BotMissingPermissions):
                await self.notify_bot_missing_permissions(ctx, error)
            elif isinstance(error, commands.CommandNotFound):
                await self.suggest_command(ctx, error)
            else:
                raise error  # Propagate other errors to log them
        except Exception as e:
            await self.notify_error(ctx, e)
            self.logger.error(f"Error in command {ctx.command}: {e}")
            traceback.print_exc()

    async def notify_missing_permissions(self, ctx, error):
        missing_perms = ', '.join(error.missing_perms)
        error_message = f"{ctx.author.mention}, you don't have the necessary permissions to execute this command: {missing_perms}"
        await ctx.send(error_message)
        self.logger.info(f"User {ctx.author} missing permissions: {missing_perms} in {ctx.guild.name}")

        # List current channel permissions for the user
        user_perms = ctx.channel.permissions_for(ctx.author)
        perms_list = [perm for perm, value in user_perms if value]
        await ctx.send(f"Your current permissions in this channel: {', '.join(perms_list)}")

    async def notify_bot_missing_permissions(self, ctx, error):
        missing_perms = ', '.join(error.missing_perms)
        invite_link = self.generate_invite_link(error.missing_perms)
        error_message = f"I don't have the necessary permissions to execute this command: {missing_perms}. " \
                        f"Please [invite me with the correct permissions]({invite_link})."
        await ctx.send(error_message)
        self.logger.info(f"Bot missing permissions: {missing_perms} in {ctx.guild.name}")

        # List current channel permissions for the bot
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        perms_list = [perm for perm, value in bot_perms if value]
        await ctx.send(f"My current permissions in this channel: {', '.join(perms_list)}")

    async def notify_forbidden_error(self, ctx, error):
        await ctx.send(f"Operation forbidden: The bot or user lacks the permission to perform an action. "
                       f"Please check the channel and role settings to ensure proper permissions.")
        self.logger.warning(f"Forbidden error in command {ctx.command}: {error}")

        # List current role and channel-specific permissions for the bot
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        perms_list = [perm for perm, value in bot_perms if value]
        await ctx.send(f"My current permissions in this channel: {', '.join(perms_list)}")

    async def notify_error(self, ctx, error):
        await self.error_custom_embed(self.bot, ctx, error)
        self.logger.error(f"Unexpected error in command {ctx.command}: {error}")

    def generate_invite_link(self, missing_perms):
        permissions = discord.Permissions()
        for perm in missing_perms:
            setattr(permissions, perm, True)
        return discord.utils.oauth_url(self.bot.user.id, permissions=permissions)

    async def suggest_command(self, ctx, error):
        all_commands = [command.name for command in self.bot.commands]
        closest_matches = get_close_matches(ctx.invoked_with, all_commands, n=3, cutoff=0.5)
        if closest_matches:
            suggestion = f"Did you mean: `{', '.join(closest_matches)}`?"
        else:
            suggestion = "No similar commands found."
        
        error_message = f"Command `{ctx.invoked_with}` not found. {suggestion}"
        
        embed = discord.Embed(description=error_message)
        await ctx.reply(embed=embed)

# Define the Logs cog
class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Method to send a log embed message
    async def send_log_embed(self, message):
        try:
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.channels, name="anya-log")
                if not channel:
                    continue  # Skip to the next guild if the logging channel does not exist

                # Get updated commands
                updated_commands = await self.get_updated_commands()
                if updated_commands:
                    commands_str = "\n".join(updated_commands)
                    if len(commands_str) <= 2000:  # Check if content fits in embed
                        await self.send_embed(channel, "Updated Files", commands_str)
                    else:
                        await self.send_file(channel, "Data/uncommitted_changes.py", "Updated Files", commands_str)

        except Exception as e:
            logger.exception("An error occurred while sending log embed:")
            await const.error_custom_embed(self.bot, None, e, title="Log Embed Error")

    # Method to send an embed message
    async def send_embed(self, channel, title, description):
        embed = discord.Embed(
            title=title,
            description=description,
            color=const.LogConstants.embed_color
        )
        embed.set_thumbnail(url=const.LogConstants.start_log_thumbnail)
        embed.set_footer(text=const.LogConstants.footer_text, icon_url=const.LogConstants.footer_icon)
        embed.set_author(name=const.LogConstants.author_name, icon_url=const.LogConstants.author_icon)
        embed.timestamp = datetime.now()  # Set current timestamp
        await channel.send(embed=embed)

    # Method to send a file
    async def send_file(self, channel, file_path, title, description):
        with open(file_path, "w") as file:
            file.write(description)
        await channel.send(file=discord.File(file_path), content=f"**{title}**")

    # Method to get updated commands
    async def get_updated_commands(self):
        root_dir = os.getcwd()
        repo = Repo(root_dir)
        diff = repo.head.commit.diff(None)
        updated_commands = []

        for d in diff:
            if d.a_path.endswith('.py') and '__pycache__' not in d.a_path:
                content = d.a_blob.data_stream.read().decode('utf-8')
                x = '----------------------------------------------------------------------------'
                entry = f"\n\n{x}\nFile: {d.a_path}\nLocation: {os.path.abspath(d.a_path)}\n{x}\n\n{content}"
                updated_commands.append(entry)

        return updated_commands

    # Listener for when the bot is ready
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Log cog is ready. This cog tells the server what updates are in the code.")
        # await self.send_log_embed("Bot is online")

# Setup function to add the Logs cog to the bot
def setup(bot):
    bot.add_cog(Permission(bot))
    bot.add_cog(Logs(bot))