#!/usr/bin/env python3
from calendar_integration.google_calendar_service import GoogleCalendarService
from calendar_integration.calendar_service import Event


def prompt(text, default=None):
    """Prompt the user; return default if they enter nothing."""
    if default:
        resp = input(f"{text} [{default}]: ").strip()
        return resp if resp else default
    else:
        return input(f"{text}: ").strip()


def main():
    print("🔌 Google Calendar Interactive CLI\n")

    # 1) Where are your creds and which calendar?
    creds_file = prompt(
        "Path to client_secrets JSON file", "calendar_integration/credentials.json"
    )
    cal_id = prompt("Calendar ID (use 'primary' for your main calendar)", "primary")

    svc = GoogleCalendarService(credentials_file=creds_file, calendar_id=cal_id)

    while True:
        action = prompt("Action? (add, update, delete, quit)").lower()
        if action == "quit":
            print("Bye!")
            break

        if action == "add":
            title = prompt("Title of the event")
            start = prompt(
                "Start time (format: YYYY-MM-DDThh:mm:ss, e.g. 2025-06-20T14:00:00)"
            )
            end = prompt(
                "End time (format: YYYY-MM-DDThh:mm:ss, e.g. 2025-06-20T15:00:00)"
            )
            desc = prompt("Description (optional)", "")
            tz = prompt("Time zone (e.g. UTC, America/New_York, Europe/London)", "UTC")

            ev = Event(
                summary=title, start=start, end=end, description=desc, timezone=tz
            )
            eid = svc.add_event(ev)
            print(f"✔ Created event ID: {eid}\n")

        elif action == "update":
            eid = prompt("Event ID to update (get this from a previous add operation)")
            # fetch existing if you want defaults: skipped for brevity
            title = prompt("New title (leave empty to keep current)", "")
            start = prompt(
                "New start time (format: YYYY-MM-DDThh:mm:ss, leave empty to keep current)",
                "",
            )
            end = prompt(
                "New end time (format: YYYY-MM-DDThh:mm:ss, leave empty to keep current)",
                "",
            )
            desc = prompt("New description (leave empty to keep current)", "")
            tz = prompt(
                "New time zone (e.g. UTC, America/New_York, leave empty to keep current)",
                "",
            )

            # Build only the fields you want to change
            body = {}
            if title:
                body["summary"] = title
            if desc:
                body["description"] = desc
            if start or end:
                times = {}
                if start:
                    times["dateTime"] = start
                if tz:
                    times["timeZone"] = tz
                body["start"] = times
                times = {}
                if end:
                    times["dateTime"] = end
                if tz:
                    times["timeZone"] = tz
                body["end"] = times

            svc.service.events().update(
                calendarId=cal_id, eventId=eid, body=body
            ).execute()
            print(f"✔ Updated event {eid}\n")

        elif action == "delete":
            eid = prompt("Event ID to delete (get this from a previous add operation)")
            svc.delete_event(eid)
            print(f"✔ Deleted event {eid}\n")

        else:
            print("Unknown action—please choose add, update, delete, or quit.\n")


if __name__ == "__main__":
    main()
