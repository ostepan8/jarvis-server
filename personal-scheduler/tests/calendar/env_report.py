import os, json, sys
out = os.environ.get("OUT_FILE") or os.environ.get("GCAL_DESC")
vars_to_capture = {"tag": os.environ.get("TAG"),
                   "creds": os.environ.get("GCAL_CREDS"),
                   "calendar": os.environ.get("GCAL_CALENDAR_ID")}
text = json.dumps(vars_to_capture)
if out:
    with open(out, 'w') as f:
        f.write(text)
else:
    print(text)
