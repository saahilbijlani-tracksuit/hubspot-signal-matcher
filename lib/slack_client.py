"""Slack Notification Client

Sends notifications to Slack via incoming webhooks.
Used to notify when signals are matched and assigned.
"""

import os
import json
import requests
from typing import Optional, Dict, Any


class SlackClient:
    """Client for sending Slack notifications via webhook."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """Initialize Slack client."""
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            print("Warning: No Slack webhook URL configured - notifications disabled")
    
    def send_message(self, text: str, blocks: Optional[list] = None) -> bool:
        """Send a message to Slack."""
        if not self.webhook_url:
            print("Slack notification skipped - no webhook configured")
            return False
        
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"Slack notification failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Slack notification error: {e}")
            return False
    
    def notify_signal_matched(
        self,
        signal_id: str,
        signal_name: str,
        signal_description: str,
        company_name: str,
        company_id: str,
        company_stage: str,
        confidence: float,
        owner_name: Optional[str] = None,
        shared_users: Optional[list] = None
    ) -> bool:
        """Send notification when signal is matched."""
        stage_emoji = {"Customer": "\U0001F49A", "Prospect": "\U0001F535", "Agency": "\U0001F7E3"}.get(company_stage, "\u26AA")
        
        if confidence >= 1.0:
            conf_indicator = "\U0001F3AF Exact match"
        elif confidence >= 0.9:
            conf_indicator = "\u2705 High confidence"
        else:
            conf_indicator = f"\U0001F4CA {int(confidence * 100)}% match"
        
        desc_preview = signal_description[:150] + "..." if len(signal_description) > 150 else signal_description
        
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"\U0001F514 Signal Matched: {signal_name}", "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Company:*\n<https://app.hubspot.com/contacts/19622650/company/{company_id}|{company_name}>"},
                {"type": "mrkdwn", "text": f"*Stage:*\n{stage_emoji} {company_stage}"}
            ]},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Confidence:*\n{conf_indicator}"},
                {"type": "mrkdwn", "text": f"*Signal ID:*\n<https://app.hubspot.com/contacts/19622650/record/2-54609655/{signal_id}|{signal_id}>"}
            ]},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Description:*\n>{desc_preview}"}}
        ]
        
        if owner_name:
            assignment_text = f"*Owner:* {owner_name}"
            if shared_users:
                assignment_text += f"\n*Shared with:* {', '.join(shared_users)}"
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": assignment_text}})
        
        blocks.append({"type": "divider"})
        
        return self.send_message(f"Signal '{signal_name}' matched to {company_name} ({company_stage})", blocks)
    
    def notify_signal_no_match(
        self,
        signal_id: str,
        signal_name: str,
        signal_description: str,
        extracted_companies: list
    ) -> bool:
        """Send notification when signal couldn't be matched."""
        desc_preview = signal_description[:150] + "..." if len(signal_description) > 150 else signal_description
        
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"\u26A0\uFE0F Signal Not Matched: {signal_name}", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Signal ID:* <https://app.hubspot.com/contacts/19622650/record/2-54609655/{signal_id}|{signal_id}>"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Description:*\n>{desc_preview}"}}
        ]
        
        if extracted_companies:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Companies searched (not found):*\n\u2022 " + "\n\u2022 ".join(extracted_companies[:5])}})
        
        blocks.append({"type": "divider"})
        
        return self.send_message(f"Signal '{signal_name}' could not be matched", blocks)
