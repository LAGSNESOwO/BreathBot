# Grok for Telegram

A Telegram bot that connects to BreathAI's API to provide responses powered by Grok AI.

## Features

- User messages are sent to the BreathAI API using the Grok-3-mini-beta model
- Streaming responses - see the AI's response as it's being generated
- Supports `/start` command to initialize conversation
- Supports `/clear` command to clear conversation history
- Customizable system prompt to control AI behavior
- Maintains conversation history for each user

## Setup and Running

1. **Clone or download this project.**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the bot:**
   ```bash
   python main.py
   ```

## Configuration

The bot is configured with the following parameters in `main.py`:

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `AI_API_URL`: The BreathAI API endpoint
- `AI_API_KEY`: Your BreathAI API key
- `AI_MODEL`: The AI model to use (grok-3-mini-beta)
- `SYSTEM_PROMPT`: The system prompt that guides the AI's behavior

## Implementation Details

This bot uses a simple polling approach to connect to the Telegram API:

- Direct HTTP requests are used instead of a bot framework to avoid compatibility issues with Python 3.13
- The long polling method is used to receive updates from Telegram
- Streaming responses from the BreathAI API are shown to users in real-time by updating messages
- When a user sends a message, their entire conversation history is sent to the API for context

## Note

- The bot is configured to use the Grok-3-mini-beta model from BreathAI
- For optimal performance, ensure a stable internet connection
- The bot maintains conversation history until explicitly cleared with `/clear` command 