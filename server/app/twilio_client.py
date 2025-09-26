import os
from typing import Optional

try:
    from twilio.rest import Client  # type: ignore
except ImportError:  # pragma: no cover
    Client = None  # type: ignore

class TwilioWrapper:
    def __init__(self):
        self.account_sid = os.getenv("ACCOUNT_SID")
        self.auth_token = os.getenv("AUTH_TOKEN")
        self.from_number = os.getenv("US_PHONENUMBER")
        self.enabled = all([self.account_sid, self.auth_token, self.from_number, Client])
        if self.enabled:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None

    def start_call(self, to_number: str, url: str) -> dict:
        if not self.enabled:
            return {"sid": "SIMULATED", "status": "simulated"}
        call = self.client.calls.create(to=to_number, from_=self.from_number, url=url)
        return {"sid": call.sid, "status": call.status}

_twilio_singleton: Optional[TwilioWrapper] = None

def get_twilio() -> TwilioWrapper:
    global _twilio_singleton
    if _twilio_singleton is None:
        _twilio_singleton = TwilioWrapper()
    return _twilio_singleton
