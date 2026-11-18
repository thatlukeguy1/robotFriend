"""
Robot Friend - phase 1: a robot brain you can type to.

Run it with:   python main.py
Type 'bye' to quit.

LESSON: Two things at once
==========================
The robot has to do two jobs at the same time:
  1. wait for you to type something
  2. keep checking whether a reminder is due

Python does this with a THREAD: a second little worker that runs alongside
the main program. Our alarm-clock thread wakes up every 15 seconds, checks
the reminders, and goes back to sleep.
"""

import os
import threading

import anthropic

from robot_friend.brain import Brain
from robot_friend.personality import ROBOT_NAME
from robot_friend.reminders import ReminderStore


def alarm_clock(reminders, stop):
    while not stop.is_set():
        for r in reminders.pop_due():
            print(f"\n🔔 {ROBOT_NAME}: Hey! Reminder: {r['message']}\nyou> ", end="", flush=True)
        stop.wait(15)  # sleep 15 seconds (or stop early if asked)


def main():
    # Inside Docker, REMINDERS_PATH points at the saved /data folder.
    reminders = ReminderStore(os.environ.get("REMINDERS_PATH", "reminders.json"))
    brain = Brain(reminders)

    stop = threading.Event()
    # daemon=True means "stop this worker when the main program ends"
    threading.Thread(target=alarm_clock, args=(reminders, stop), daemon=True).start()

    print(f"{ROBOT_NAME} is awake! Type to chat, 'bye' to quit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in ("bye", "quit", "exit"):
            break
        try:
            print(f"{ROBOT_NAME}> {brain.chat(text)}\n")
        except anthropic.AuthenticationError:
            print("! Your API key isn't working. Check ANTHROPIC_API_KEY (see LEARN.md).")
            break
        except anthropic.APIConnectionError:
            print("! I can't reach the internet right now.\n")
        except anthropic.APIStatusError as e:
            print(f"! Something went wrong talking to Claude ({e.status_code}). Try again.\n")

    stop.set()
    print(f"{ROBOT_NAME}: Bye for now!")


if __name__ == "__main__":
    main()
