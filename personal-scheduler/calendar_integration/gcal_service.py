#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import json

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


def get_calendar_service(credentials_file):
    """Get authenticated Google Calendar service."""
    creds = None
    token_file = "calendar_integration/token.pickle"

    # Token file stores the user's access and refresh tokens
    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(token_file, "wb") as token:
            pickle.dump(creds, token)

    return build("calendar", "v3", credentials=creds)


def get_tasks_service(credentials_file):
    """Get authenticated Google Tasks service."""
    creds = None
    token_file = "calendar_integration/token.pickle"

    if os.path.exists(token_file):
        with open(token_file, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "wb") as token:
            pickle.dump(creds, token)

    return build("tasks", "v1", credentials=creds)


def main():
    # Get environment variables
    action = os.environ.get("GCAL_ACTION")
    creds_file = os.environ.get("GCAL_CREDS")
    calendar_id = os.environ.get("GCAL_CALENDAR_ID", "primary")

    if not action or not creds_file:
        print("Error: GCAL_ACTION and GCAL_CREDS must be set", file=sys.stderr)
        sys.exit(1)

    print(f"Action: {action}")
    print(f"Calendar ID: {calendar_id}")

    try:
        # Calendar service is needed for event actions
        cal_service = get_calendar_service(creds_file)
        tasks_service = get_tasks_service(creds_file)

        if action == "add":
            # Get event details from environment
            event = {
                "summary": os.environ.get("GCAL_TITLE", "Untitled Event"),
                "description": os.environ.get("GCAL_DESC", ""),
                "start": {
                    "dateTime": os.environ["GCAL_START"],
                    "timeZone": os.environ.get("GCAL_TZ", "UTC"),
                },
                "end": {
                    "dateTime": os.environ["GCAL_END"],
                    "timeZone": os.environ.get("GCAL_TZ", "UTC"),
                },
            }

            # Add ID if provided (for consistency with C++ model)
            event_id = os.environ.get("GCAL_EVENT_ID")
            if event_id:
                event["id"] = event_id.replace("-", "").lower()[
                    :64
                ]  # Google Calendar ID constraints

            # Add recurrence if provided
            recurrence = os.environ.get("GCAL_RECURRENCE")
            if recurrence:
                event["recurrence"] = [recurrence]

            # Create the event
            created_event = cal_service.events().insert(calendarId=calendar_id, body=event).execute()
            print("GCAL_JSON: " + json.dumps({
                "status": "ok",
                "event_id": created_event.get('id'),
                "link": created_event.get('htmlLink'),
            }))

        elif action == "update":
            event_id = os.environ.get("GCAL_EVENT_ID")
            if not event_id:
                print("Error: GCAL_EVENT_ID required for update", file=sys.stderr)
                sys.exit(1)

            # Google Calendar IDs have specific format
            gcal_event_id = event_id.replace("-", "").lower()[:64]

            # Get the existing event first
            try:
                existing_event = (
                    cal_service.events()
                    .get(calendarId=calendar_id, eventId=gcal_event_id)
                    .execute()
                )
            except Exception as e:
                print(
                    f"Error: Could not find event {gcal_event_id}: {e}", file=sys.stderr
                )
                sys.exit(1)

            # Update fields if provided
            if "GCAL_TITLE" in os.environ:
                existing_event["summary"] = os.environ["GCAL_TITLE"]
            if "GCAL_DESC" in os.environ:
                existing_event["description"] = os.environ["GCAL_DESC"]
            if "GCAL_START" in os.environ:
                existing_event["start"] = {
                    "dateTime": os.environ["GCAL_START"],
                    "timeZone": os.environ.get("GCAL_TZ", "UTC"),
                }
            if "GCAL_END" in os.environ:
                existing_event["end"] = {
                    "dateTime": os.environ["GCAL_END"],
                    "timeZone": os.environ.get("GCAL_TZ", "UTC"),
                }

            # Update the event
            updated_event = cal_service.events().update(calendarId=calendar_id, eventId=gcal_event_id, body=existing_event).execute()
            print("GCAL_JSON: " + json.dumps({
                "status": "ok",
                "event_id": updated_event.get('id'),
                "link": updated_event.get('htmlLink'),
            }))

        elif action == "delete":
            event_id = os.environ.get("GCAL_EVENT_ID")
            if not event_id:
                print("Error: GCAL_EVENT_ID required for delete", file=sys.stderr)
                sys.exit(1)

            # Google Calendar IDs have specific format
            gcal_event_id = event_id.replace("-", "").lower()[:64]

            try:
                # Delete the event by ID first
                cal_service.events().delete(calendarId=calendar_id, eventId=gcal_event_id).execute()
                print("GCAL_JSON: " + json.dumps({
                    "status": "ok",
                    "deleted_event_id": gcal_event_id,
                }))
            except Exception as e:
                # Fallback: try to find the event by title and start time
                title = os.environ.get("GCAL_TITLE")
                start_str = os.environ.get("GCAL_START")
                tz = os.environ.get("GCAL_TZ", "UTC")
                print(f"Primary delete failed for {gcal_event_id}: {e}. Attempting fallback search…")
                if title and start_str:
                    try:
                        # Narrow time window around provided start
                        from datetime import datetime, timedelta, timezone
                        # Parse RFC3339 Zulu time
                        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        time_min = (start_dt - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
                        time_max = (start_dt + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
                        events_result = cal_service.events().list(
                            calendarId=calendar_id,
                            timeMin=time_min,
                            timeMax=time_max,
                            q=title,
                            singleEvents=False
                        ).execute()
                        items = events_result.get('items', [])
                        # Delete first matching event
                        deleted = False
                        for ev in items:
                            if ev.get('summary') == title:
                                cal_service.events().delete(calendarId=calendar_id, eventId=ev['id']).execute()
                                print("GCAL_JSON: " + json.dumps({
                                    "status": "ok",
                                    "deleted_event_id": ev['id'],
                                }))
                                deleted = True
                                break
                        if not deleted:
                            print("Fallback delete: no matching event found", file=sys.stderr)
                            sys.exit(1)
                    except Exception as e2:
                        print(f"Fallback delete failed: {type(e2).__name__}: {e2}", file=sys.stderr)
                        sys.exit(1)
                else:
                    print("Fallback delete unavailable (missing GCAL_TITLE/GCAL_START)", file=sys.stderr)
                    sys.exit(1)

        elif action == "add_task":
            task = {
                "title": os.environ.get("GCAL_TITLE", "Untitled Task"),
                "notes": os.environ.get("GCAL_DESC", ""),
            }
            task_id = os.environ.get("GCAL_TASK_ID")
            if task_id:
                task["id"] = task_id.replace("-", "").lower()[:1024]
            due = os.environ.get("GCAL_DUE")
            if due:
                task["due"] = due
            tasklist = os.environ.get("GCAL_TASKLIST_ID", "@default")
            created = tasks_service.tasks().insert(tasklist=tasklist, body=task).execute()
            print("GCAL_JSON: " + json.dumps({
                "status": "ok",
                "task_id": created.get('id'),
            }))

        elif action == "delete_task":
            task_id = os.environ.get("GCAL_TASK_ID")
            if not task_id:
                print("Error: GCAL_TASK_ID required for delete_task", file=sys.stderr)
                sys.exit(1)
            tasklist = os.environ.get("GCAL_TASKLIST_ID", "@default")
            tasks_service.tasks().delete(tasklist=tasklist, task=task_id).execute()
            print("GCAL_JSON: " + json.dumps({
                "status": "ok",
                "deleted_task_id": task_id,
            }))

        elif action == "update_task":
            task_id = os.environ.get("GCAL_TASK_ID")
            if not task_id:
                print("Error: GCAL_TASK_ID required for update_task", file=sys.stderr)
                sys.exit(1)
            tasklist = os.environ.get("GCAL_TASKLIST_ID", "@default")
            task = tasks_service.tasks().get(tasklist=tasklist, task=task_id).execute()
            if "GCAL_TITLE" in os.environ:
                task["title"] = os.environ["GCAL_TITLE"]
            if "GCAL_DESC" in os.environ:
                task["notes"] = os.environ["GCAL_DESC"]
            if "GCAL_DUE" in os.environ:
                task["due"] = os.environ["GCAL_DUE"]
            updated = tasks_service.tasks().update(tasklist=tasklist, task=task_id, body=task).execute()
            print("GCAL_JSON: " + json.dumps({
                "status": "ok",
                "task_id": updated.get('id'),
            }))

        else:
            print(f"Error: Unknown action: {action}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print("GCAL_JSON: " + json.dumps({
            "status": "error",
            "type": type(e).__name__,
            "message": str(e)
        }))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
