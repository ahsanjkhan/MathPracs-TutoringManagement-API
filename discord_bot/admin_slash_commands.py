import json
import discord
from discord import app_commands, ui
from discord.ext import commands
from channel_admin_slash_commands import ChannelAdminCommands
from tutor_slash_commands import is_admin
from src.functions import tutor_functions, student_functions
from src.models.tutor_model import TutorStatus, TutorUpdate
from src.models.student_model import StudentUpdate, PaymentCollector


class TutorUpdateModal(ui.Modal, title="Update Tutor"):
    """Modal for updating tutor fields via JSON."""

    json_input = ui.TextInput(
        label="Tutor Data (JSON)",
        style=discord.TextStyle.paragraph,
        placeholder='{"hourly_rate": 15.0, "tutor_email": "email@example.com"}',
        required=True,
        max_length=2000,
    )

    def __init__(self, tutor_id: str, tutor_name: str, current_data: dict):
        super().__init__()
        self.tutor_id = tutor_id
        self.tutor_name = tutor_name
        self.json_input.default = json.dumps(current_data, indent=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.json_input.value)

            # Handle status enum conversion
            if "status" in data and data["status"]:
                data["status"] = TutorStatus(data["status"])

            update = TutorUpdate(**data)
            result = tutor_functions.update_tutor(self.tutor_id, update)

            if result:
                await interaction.response.send_message(
                    f"Successfully updated **{self.tutor_name}**!", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Failed to update tutor.", ephemeral=True
                )
        except json.JSONDecodeError as e:
            await interaction.response.send_message(f"Invalid JSON: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class StudentUpdateModal(ui.Modal, title="Update Student"):
    """Modal for updating student fields via JSON."""

    json_input = ui.TextInput(
        label="Student Data (JSON)",
        style=discord.TextStyle.paragraph,
        placeholder='{"hourly_price_standard": 25.0, "payment_collected_by": "muaz"}',
        required=True,
        max_length=2000,
    )

    def __init__(self, student_name: str, current_data: dict):
        super().__init__()
        self.student_name = student_name
        self.json_input.default = json.dumps(current_data, indent=2)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = json.loads(self.json_input.value)

            # Handle payment_collected_by enum conversion
            if "payment_collected_by" in data and data["payment_collected_by"]:
                data["payment_collected_by"] = PaymentCollector(data["payment_collected_by"])

            update = StudentUpdate(**data)
            result = student_functions.update_student(self.student_name, update)

            if result:
                await interaction.response.send_message(
                    f"Successfully updated **{self.student_name}**!", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Failed to update student.", ephemeral=True
                )
        except json.JSONDecodeError as e:
            await interaction.response.send_message(f"Invalid JSON: {e}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)


class AdminCommands(ChannelAdminCommands):
    """Commands for admins. Inherits all channel admin and tutor commands."""

    ADMIN_COMMANDS = {
        "manual_sync": "Trigger a calendar sync",
        "active_tutors": "List all active tutors",
        "get_tutor": "View tutor details",
        "get_student": "View student details",
        "update_tutor": "Update tutor fields via modal",
        "update_student": "Update student fields via modal",
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

    @app_commands.command(name="get_tutor", description="[Admin] View tutor details")
    @app_commands.describe(tutor_name="Tutor name (e.g., 'mustafa')")
    async def get_tutor(self, interaction: discord.Interaction, tutor_name: str):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return

        tutor = tutor_functions.resolve_tutor(tutor_name)
        if not tutor:
            await interaction.response.send_message(f"Tutor '{tutor_name}' not found.", ephemeral=True)
            return

        info = f"""**Tutor: {tutor.display_name}**
```
ID:           {tutor.tutor_id}
Calendar ID:  {tutor.calendar_id}
Status:       {tutor.status.value}
Hourly Rate:  ${tutor.hourly_rate}
Timezone:     {tutor.tutor_timezone}
Email:        {tutor.tutor_email or 'Not set'}
Phone:        {tutor.tutor_phone or 'Not set'}
Discord Ch:   {tutor.discord_channel_id or 'Not set'}
Created:      {tutor.created_at.strftime('%Y-%m-%d %H:%M')}
Updated:      {tutor.updated_at.strftime('%Y-%m-%d %H:%M')}
```"""
        await interaction.response.send_message(info, ephemeral=True)

    @app_commands.command(name="get_student", description="[Admin] View student details")
    @app_commands.describe(student_name="Student name (e.g., 'John Doe')")
    async def get_student(self, interaction: discord.Interaction, student_name: str):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return

        student = student_functions.get_student(student_name)
        if not student:
            await interaction.response.send_message(f"Student '{student_name}' not found.", ephemeral=True)
            return

        payment = student.payment_collected_by.value if student.payment_collected_by else "Not set"

        info = f"""**Student: {student.student_name}**
```
Tutor ID:     {student.tutor_id}
Email:        {student.student_email or 'Not set'}
Timezone:     {student.student_timezone or 'Not set'}
Doc ID:       {student.doc_id}
Meet Link:    {student.google_meets_link or 'Not set'}
Payment By:   {payment}

Hourly Prices:
  Standard:   {student.hourly_price_standard or 'Not set'}
  Price 1:    {student.hourly_price_1 or 'Not set'}
  Price 2:    {student.hourly_price_2 or 'Not set'}
  Price 3:    {student.hourly_price_3 or 'Not set'}
  Price 4:    {student.hourly_price_4 or 'Not set'}
  Price 5:    {student.hourly_price_5 or 'Not set'}
  No Show:    {student.hourly_price_no_show or 'Not set'}

Created:      {student.created_at.strftime('%Y-%m-%d %H:%M')}
```"""
        await interaction.response.send_message(info, ephemeral=True)

    @app_commands.command(name="update_tutor", description="[Admin] Update tutor fields via modal")
    @app_commands.describe(tutor_name="Tutor name (e.g., 'mustafa')")
    async def update_tutor(self, interaction: discord.Interaction, tutor_name: str):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return

        tutor = tutor_functions.resolve_tutor(tutor_name)
        if not tutor:
            await interaction.response.send_message(f"Tutor '{tutor_name}' not found.", ephemeral=True)
            return

        # Build current data dict for pre-population (only updatable fields)
        current_data = {
            "display_name": tutor.display_name,
            "status": tutor.status.value,
            "hourly_rate": tutor.hourly_rate,
            "tutor_email": tutor.tutor_email,
            "tutor_phone": tutor.tutor_phone,
            "tutor_timezone": tutor.tutor_timezone,
        }

        modal = TutorUpdateModal(tutor.tutor_id, tutor.display_name, current_data)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="update_student", description="[Admin] Update student fields via modal")
    @app_commands.describe(student_name="Student name (e.g., 'John Doe')")
    async def update_student(self, interaction: discord.Interaction, student_name: str):
        if not is_admin(interaction):
            await interaction.response.send_message("You need the Admin role to use this command.", ephemeral=True)
            return

        student = student_functions.get_student(student_name)
        if not student:
            await interaction.response.send_message(f"Student '{student_name}' not found.", ephemeral=True)
            return

        # Build current data dict for pre-population (only commonly edited fields)
        current_data = {
            "student_email": student.student_email,
            "student_timezone": student.student_timezone,
            "hourly_price_standard": student.hourly_price_standard,
            "hourly_price_1": student.hourly_price_1,
            "hourly_price_2": student.hourly_price_2,
            "hourly_price_3": student.hourly_price_3,
            "hourly_price_4": student.hourly_price_4,
            "hourly_price_5": student.hourly_price_5,
            "hourly_price_no_show": student.hourly_price_no_show,
            "payment_collected_by": student.payment_collected_by.value if student.payment_collected_by else None,
        }

        modal = StudentUpdateModal(student.student_name, current_data)
        await interaction.response.send_modal(modal)
