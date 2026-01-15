"""Slack Notification Client

Sends notifications to Slack via incoming webhooks.
Used to notify when signals are matched and assigned.
"""

import os
import requests
from typing import Optional, Dict, Any


class SlackClient:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            print("Warning: No Slack webhook URL configured - notifications disabled")

    def send_message(self, text: str, blocks: Optional[list] = None) -> bool:
        if not self.webhook_url:
            print("Slack notification skipped - no webhook configured")
            return False
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        try:
            response = requests.post(self.webhook_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if response.status_code == 200:
                return True
            print(f"Slack notification failed: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            print(f"Slack notification error: {e}")
            return False

    def notify_signal_matched(
        self, signal_id: str, signal_name: str, signal_description: str,
        company_name: str, company_id: str, company_stage: str, confidence: float,
        owner_name: Optional[str] = None, shared_users: Optional[list] = None,
        owner_email: Optional[str] = None, shared_user_emails: Optional[list] = None
    ) -> bool:
        stage_emoji = {"Customer": "💚", "Prospect": "🔵", "Agency": "🟣"}.get(company_stage, "⚪")
        desc_preview = signal_description[:150] + "..." if len(signal_description) > 150 else signal_description

        # Build user tags - mention by email if available
        user_tags = []
        if owner_email:
            user_tags.append(f"<@{owner_email}>")
        elif owner_name:
            user_tags.append(owner_name)
        if shared_user_emails:
            for email in shared_user_emails:
                if email:
                    user_tags.append(f"<@{email}>")
        elif shared_users:
            user_tags.extend([u for u in shared_users if u])

        blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"🔔 New Signal: {signal_name}", "emoji": True}}]

        if user_tags:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"👋 *cc:* {' '.join(user_tags)}"}})

        blocks.extend([
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Company:*\n<https://app.hubspot.com/contacts/19622650/company/{company_id}|{company_name}>"},
                {"type": "mrkdwn", "text": f"*Stage:*\n{stage_emoji} {company_stage}"}
            ]},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Signal:*\n<https://app.hubspot.com/contacts/19622650/record/2-54609655/{signal_id}|View in HubSpot>"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Description:*\n>{desc_preview}"}}
        ])

        if owner_name:
            assignment_text = f"*Owner:* {owner_name}"
            if shared_users:
                shared_names = [u for u in shared_users if u]
                if shared_names:
                    assignment_text += f"\n*Shared with:* {', '.join(shared_names)}"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": assignment_text}})

        blocks.append({"type": "divider"})
        return self.send_message(f"New Signal: {signal_name} for {company_name} ({company_stage})", blocks)

    def notify_signal_no_match(self, signal_id: str, signal_name: str, signal_description: str, extracted_companies: list) -> bool:
        desc_preview = signal_description[:150] + "..." if len(signal_description) > 150 else signal_description
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"⚠️ Signal Not Matched: {signal_name}", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Signal ID:* <https://app.hubspot.com/contacts/19622650/record/2-54609655/{signal_id}|{signal_id}>"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Description:*\n>{desc_preview}"}}
        ]
        if extracted_companies:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Companies searched (not found):*\n• " + "\n• ".join(extracted_companies[:5])}})
        blocks.append({"type": "divider"})
        return self.send_message(f"Signal '{signal_name}' could not be matched", blocks)
