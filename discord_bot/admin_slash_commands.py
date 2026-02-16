import discord
from discord import app_commands
from discord.ext import commands
from channel_admin_slash_commands import ChannelAdminCommands
from tutor_slash_commands import is_admin
from src.functions import tutor_functions
from src.models.tutor_model import TutorStatus


class AdminCommands(ChannelAdminCommands):
    """Commands for admins. Inherits all channel admin and tutor commands."""

    # Admin specific commands
    ADMIN_COMMANDS = {
        "manual_sync": "Trigger a calendar sync",
        "active_tutors": "List all active tutors",
    }

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

    @app_commands.command(name="manual_sync", description="[Admin] Trigger a calendar + event sync manually")
    async def manual_sync(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        from src.functions.sync_functions import sync_calendar_list, sync_events_list

        try:
            cal_result = sync_calendar_list()
            events_result = sync_events_list("ALL")

            await interaction.followup.send(
                f"**Sync completed!**\n"
                f"Calendars: {cal_result['created']} created, {cal_result['updated']} updated, {cal_result['deactivated']} deactivated\n"
                f"Events: {events_result['created']} created, {events_result['updated']} updated, {events_result['deleted']} deleted, {events_result['docs_created']} docs created",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Sync failed: {str(e)}", ephemeral=True)

    @app_commands.command(name="active_tutors", description="[Admin] List all active tutors")
    async def active_tutors(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)

        if not tutors:
            await interaction.followup.send("No active tutors found.", ephemeral=True)
            return

        lines = ["**Active Tutors:**\n"]
        for t in tutors:
            channel_status = "linked" if t.discord_channel_id else "no channel"
            lines.append(f"• **{t.display_name}** ({channel_status})")

        await interaction.followup.send("\n".join(lines), ephemeral=True)
