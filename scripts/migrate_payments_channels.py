"""
One-time script to create payments Discord channels for existing tutors
that don't already have one.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.functions import discord_utils, tutor_functions
from src.models.tutor_v2_model import TutorStatus


def main():
    tutors = tutor_functions.get_all_tutors(status_filter=TutorStatus.ACTIVE)
    print(f"Found {len(tutors)} active tutors")

    created = 0
    skipped = 0
    failed = 0

    for tutor in tutors:
        if tutor.payments_discord_channel_id:
            print(f"  [{tutor.tutor_name}] already has payments channel — skipping")
            skipped += 1
            continue

        print(f"  [{tutor.tutor_name}] creating payments channel...")
        channel_id = discord_utils.create_payments_channel(tutor.tutor_name)
        if channel_id:
            tutor_functions.set_tutor_payments_channel(tutor.tutor_id, channel_id)
            print(f"  [{tutor.tutor_name}] created (ID: {channel_id})")
            created += 1
        else:
            print(f"  [{tutor.tutor_name}] FAILED to create channel")
            failed += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
