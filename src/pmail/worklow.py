import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Callable, Any


def save_attachment(message: Dict[str, Any], directory: str, pattern: str = "*.pdf"):
    """Save attachments matching pattern to directory"""
    dir_path = Path(os.path.expanduser(directory))
    dir_path.mkdir(parents=True, exist_ok=True)
    # TODO: Implement attachment saving
    print(f"Would save attachments matching {pattern} to {directory}")


def flag_in_mutt(message: Dict[str, Any], flag: str):
    """Flag the message in mutt"""
    # TODO: Implement mutt flagging via message-id
    print(f"Would flag message {message['message_id']} with flag '{flag}'")


def copy_to_folder(message: Dict[str, Any], folder: str):
    """Copy message to another folder"""
    # TODO: Implement folder copying
    print(f"Would copy message to folder {folder}")


def create_todo(message: Dict[str, Any], todo_file: str = "~/todos.txt"):
    """Create a todo item from the email"""
    # TODO: Extract todo and append to file
    print(f"Would create todo from email in {todo_file}")


# Action type mapping - maps action types to functions
Workflows = {
    "flag": flag_in_mutt,
    "save_attachment": save_attachment,
    "copy_to_folder": copy_to_folder,
    "create_todo": create_todo,
}


class Criteria:
    def __init__(
        self,
        from_address=None,
        to_address=None,
        with_pdf_attachment=None,
        subject=None,
    ):
        self.from_address = from_address
        self.to_address = to_address
        self.with_pdf_attachment = with_pdf_attachment
        self.subject = subject

        assert (
            self.from_address
            or self.to_address
            or self.with_pdf_attachment
            or self.subject
        )

    def applies(self, message):
        return (
            (
                self.from_address in message["from_address"]
                if self.from_address
                else True
            )
            and (
                self.from_address in message["to_address"] if self.to_address else True
            )
            and (
                message["with_pdf_attachment"] == self.with_pdf_attachment
                if self.with_pdf_attachment is not None
                else True
            )
            and (self.subject in message["subject"] if self.subject else True)
        )

    def as_dict(self):
        return {
            "from-address": self.from_address,
            "to_address": self.to_address,
            "with_pdf_attachment": self.with_pdf_attachment,
            "subject": self.subject,
        }


class Rules:
    def __init__(self, rules_json_file):
        with open(rules_json_file) as fin:
            self.rules = json.load(fin)

    def add_rule(self, criteria: Criteria, workflow_name: str):
        self.rules.append({"criteria": criteria, "workflow-name": workflow_name})


##  We define a bunch of workflow criteria. For each email this will limit the options. We also need a history, and the ability to find similar ones.
