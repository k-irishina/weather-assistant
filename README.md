# weather-assistant v0.1

Designed to check the weather forecast so you don't have to.

### Main features
* Provides a short forecast and recommendations based on the weather conditions
* Sends periodic updates on forecast changes (currently, only for sunny and rainy conditions)

### How to use
Message @WhisperWeatherBot on Telegram and use /help to get available commands and set up your experience.

### Upcoming features
* More accurate sun predictions
* Automatic short forecast sent at user-defined time
* A more detailed forecast upon user request
* Better-looking output
* Standalone app for UI and notifications

### Tech

The app's logic is written in Python. User interaction and notifications are currently provided through a Telegram bot, with plans to eventually create a standalone application, but the current focus is accurate data analysis. Database used is Postgres. 

The forecast data is provided by [MET Weather API](https://api.met.no/).

#### Tech TODOs
* Store all forecast data in one INSERT statement
* Better database connection management (pooling)
* Better determining of sunny conditions
* Logging, not printing
