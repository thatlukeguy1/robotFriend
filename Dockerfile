# LESSON: A Dockerfile is a recipe for building a "container image":
# a sealed box with Python, our code and its libraries all inside.
# Every line is one step of the recipe.

# Start from a small, ready-made Linux with Python installed.
FROM python:3.13-slim

# tzdata lets the container know about time zones (needed for reminders!).
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Work inside a folder called /app in the box.
WORKDIR /app

# Install the libraries first. Docker remembers this step, so rebuilding
# after a code change is quick.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy in our code.
COPY . .

# Reminders are saved here. compose.yaml connects this folder to a
# "volume", so they survive the container being rebuilt.
ENV REMINDERS_PATH=/data/reminders.json
# Print output immediately instead of saving it up.
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
